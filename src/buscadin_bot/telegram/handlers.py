"""Authorization, indication workflows and editorial Telegram actions."""

import json
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.config import Settings
from buscadin_bot.db.models import (
    BotState,
    EditorialPublication,
    Job,
    Notification,
    ReferralLink,
    ReferralProgram,
    utcnow,
)
from buscadin_bot.services.editorial import prepare_editorial_text, set_editorial_status
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.services.publication_gateway import PublicationGateway
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.formatters import format_job_message, job_keyboard
from buscadin_bot.telegram.site_handlers import handle_site_update

LINK_FLOW_PREFIX = "link_flow:"
LINK_FLOW_TTL = timedelta(minutes=10)


def is_authorized_update(update: dict[str, Any], settings: Settings) -> bool:
    message = update.get("message") or update.get("callback_query", {}).get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat", {})
    if chat.get("id") != settings.telegram_admin_chat_id:
        return False
    if settings.telegram_admin_user_id is None:
        return True
    actor = update.get("message", {}).get("from") or update.get("callback_query", {}).get("from", {})
    return actor.get("id") == settings.telegram_admin_user_id


async def handle_update(
    update: dict[str, Any],
    *,
    session: AsyncSession,
    telegram: TelegramClient,
    settings: Settings,
    site_gateway: PublicationGateway | None = None,
) -> None:
    if not is_authorized_update(update, settings):
        callback = update.get("callback_query")
        if isinstance(callback, dict) and callback.get("id"):
            await telegram.answer_callback_query(str(callback["id"]), "Não autorizado")
        return

    if await handle_site_update(update, session=session, telegram=telegram, settings=settings, gateway=site_gateway):
        return

    callback = update.get("callback_query")
    if isinstance(callback, dict):
        await _handle_callback(callback, session=session, telegram=telegram, settings=settings)
        return

    message = update.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
        return
    text = message["text"].strip()
    chat_id = int(message["chat"]["id"])
    actor = str(message.get("from", {}).get("id", chat_id))
    flow = await _get_link_flow(session, chat_id, actor)
    if not text.startswith("/"):
        if flow and flow.get("stage") == "awaiting_url":
            await _receive_link_url(session, telegram, chat_id, actor, text, flow)
        return

    parts = text.split()
    command = parts[0].split("@", 1)[0].lower()
    if command == "/start":
        await telegram.send_message(chat_id, "Buscadin ativo. Use /ajuda para ver os comandos.")
    elif command in {"/ajuda", "/help"}:
        await telegram.send_message(chat_id, _help_text())
    elif command in {"/novas", "/pendentes", "/selecionadas"}:
        await _send_listing(command, parts[1:], session, telegram, chat_id)
    elif command == "/publicadas":
        await _send_published(session, telegram, chat_id)
    elif command == "/indicacoes":
        await _send_indications(session, telegram, chat_id)
    elif command == "/resumo":
        await telegram.send_message(chat_id, await _summary_text(session))
    elif command == "/vaga":
        await _send_job_detail(session, telegram, chat_id, parts[1:])
    elif command == "/vincular":
        await _start_link_flow(session, telegram, chat_id, actor, parts[1:])
    elif command == "/confirmar_link":
        await _confirm_link(session, telegram, chat_id, actor, parts[1:], flow)
    elif command == "/cancelar":
        await _clear_link_flow(session, chat_id, actor)
        await telegram.send_message(chat_id, "Fluxo cancelado.")
    elif command == "/publicar":
        await _publish_command(session, telegram, chat_id, actor, parts[1:])
    elif command == "/programas":
        await _send_programs(session, telegram, chat_id)
    else:
        await telegram.send_message(chat_id, "Comando desconhecido. Use /ajuda.")


async def _handle_callback(
    callback: dict[str, Any],
    *,
    session: AsyncSession,
    telegram: TelegramClient,
    settings: Settings,
) -> None:
    callback_id = str(callback["id"])
    data = str(callback.get("data") or "")
    action, separator, raw_job_id = data.partition(":")
    if not separator or not raw_job_id.isdigit():
        await telegram.answer_callback_query(callback_id, "Ação inválida")
        return
    result = await session.execute(select(Job).where(Job.id == int(raw_job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        await telegram.answer_callback_query(callback_id, "Vaga não encontrada")
        return
    actor = str(callback.get("from", {}).get("id", settings.telegram_admin_user_id or "admin"))

    if action == "approve":
        if job.review_status == "pending":
            job.review_status = "approved"
        await telegram.answer_callback_query(callback_id, "Vaga atualizada")
    elif action == "select":
        await set_editorial_status(session, job, "SELECIONADA", actor=actor)
        await telegram.answer_callback_query(callback_id, "Vaga selecionada")
    elif action == "prepare":
        resolution = await ReferralResolver().resolve_status(session, job)
        await telegram.answer_callback_query(callback_id, "Texto preparado")
        await telegram.send_message(
            int(callback["message"]["chat"]["id"]),
            escape(prepare_editorial_text(job, resolution)),
        )
    elif action == "ready":
        await set_editorial_status(session, job, "PRONTA", actor=actor)
        await telegram.answer_callback_query(callback_id, "Vaga marcada como pronta")
    elif action == "discard":
        if job.review_status == "pending":
            job.review_status = "discarded"
        await set_editorial_status(session, job, "DESCARTADA", actor=actor)
        await telegram.answer_callback_query(callback_id, "Vaga descartada")
    elif action == "detail":
        resolution = await ReferralResolver().resolve_status(session, job)
        await telegram.answer_callback_query(callback_id, "Detalhes enviados")
        await telegram.send_message(
            int(callback["message"]["chat"]["id"]),
            format_job_message(
                job,
                referral_status=resolution.status,
                referral_reason=resolution.reason,
                referral_url=resolution.link.url if resolution.link else None,
            ),
            reply_markup=job_keyboard(
                job,
                editorial=True,
                destination_url=resolution.link.url if resolution.link else job.application_url,
            ),
        )
    elif action == "link":
        await telegram.answer_callback_query(callback_id, "Abrindo vinculação")
        await _start_link_flow(
            session,
            telegram,
            int(callback["message"]["chat"]["id"]),
            actor,
            [str(job.id)],
        )
        return
    else:
        await telegram.answer_callback_query(callback_id, "Ação inválida")
        return

    message = callback.get("message")
    if action not in {"prepare", "detail", "link"} and isinstance(message, dict):
        chat = message.get("chat", {})
        if chat.get("id") and message.get("message_id"):
            await telegram.edit_message_reply_markup(
                chat_id=int(chat["id"]),
                message_id=int(message["message_id"]),
                reply_markup={"inline_keyboard": []},
            )


async def _send_listing(
    command: str,
    args: list[str],
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
) -> None:
    query = select(Job).order_by(Job.first_seen_at.desc()).limit(10)
    if command == "/novas":
        query = query.where(Job.editorial_status == "NOVA")
    elif command == "/pendentes":
        query = query.where(Job.referral_status == "AGUARDANDO_LINK")
    else:
        query = query.where(Job.editorial_status.in_(["SELECIONADA", "PRONTA"]))
    if args:
        query = query.where(Job.company == args[0])
    result = await session.execute(query)
    jobs = list(result.scalars().all())
    if not jobs:
        await telegram.send_message(chat_id, "Nenhuma vaga encontrada para esse filtro.")
        return
    resolver = ReferralResolver()
    for job in jobs:
        resolution = await resolver.resolve_status(session, job)
        await telegram.send_message(
            chat_id,
            format_job_message(
                job,
                referral_status=resolution.status,
                referral_reason=resolution.reason,
                referral_url=resolution.link.url if resolution.link else None,
            ),
            reply_markup=job_keyboard(
                job,
                editorial=True,
                destination_url=resolution.link.url if resolution.link else job.application_url,
            ),
        )


async def _send_job_detail(
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
    args: list[str],
) -> None:
    if not args or not args[0].isdigit():
        await telegram.send_message(chat_id, "Uso: /vaga <id>")
        return
    job = await session.scalar(select(Job).where(Job.id == int(args[0])))
    if job is None:
        await telegram.send_message(chat_id, "Vaga não encontrada.")
        return
    resolution = await ReferralResolver().resolve_status(session, job)
    await telegram.send_message(
        chat_id,
        format_job_message(
            job,
            referral_status=resolution.status,
            referral_reason=resolution.reason,
            referral_url=resolution.link.url if resolution.link else None,
        ),
        reply_markup=job_keyboard(
            job,
            editorial=True,
            destination_url=resolution.link.url if resolution.link else job.application_url,
        ),
    )


async def _send_indications(session: AsyncSession, telegram: TelegramClient, chat_id: int) -> None:
    counts = {}
    for status in ("LINK_VALIDADO", "AGUARDANDO_LINK", "SEM_PROGRAMA"):
        counts[status] = await session.scalar(select(func.count(Job.id)).where(Job.referral_status == status))
    await telegram.send_message(
        chat_id,
        "Estados de indicação:\n"
        f"LINK_VALIDADO: {counts['LINK_VALIDADO']}\n"
        f"AGUARDANDO_LINK: {counts['AGUARDANDO_LINK']}\n"
        f"SEM_PROGRAMA: {counts['SEM_PROGRAMA']}",
    )


async def _send_programs(session: AsyncSession, telegram: TelegramClient, chat_id: int) -> None:
    result = await session.execute(
        select(ReferralProgram).where(ReferralProgram.is_active.is_(True)).order_by(ReferralProgram.company)
    )
    programs = list(result.scalars().all())
    text = "\n".join(
        f"{program.id}: {program.company} — {program.name} ({program.scope_type})"
        for program in programs
    ) or "Nenhum programa ativo cadastrado."
    await telegram.send_message(chat_id, "Programas ativos:\n" + text)


async def _send_published(session: AsyncSession, telegram: TelegramClient, chat_id: int) -> None:
    result = await session.execute(
        select(EditorialPublication, Job)
        .join(Job, EditorialPublication.job_id == Job.id)
        .order_by(EditorialPublication.published_at.desc())
        .limit(20)
    )
    rows = list(result.all())
    text = "\n".join(
        f"{publication.published_at:%Y-%m-%d} — {job.id} {job.title} ({publication.channel})"
        for publication, job in rows
    ) or "Nenhuma publicação registrada."
    await telegram.send_message(chat_id, "Publicações registradas:\n" + text)


async def _publish_command(
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
    actor: str,
    args: list[str],
) -> None:
    if len(args) < 1 or not args[0].isdigit():
        await telegram.send_message(chat_id, "Uso: /publicar <id> [instagram|tiktok|kwai|outro] [post_url]")
        return
    job = await session.scalar(select(Job).where(Job.id == int(args[0])))
    if job is None:
        await telegram.send_message(chat_id, "Vaga não encontrada.")
        return
    channel = args[1].lower() if len(args) > 1 else "outro"
    post_url = args[2] if len(args) > 2 else None
    try:
        await set_editorial_status(session, job, "PUBLICADA", actor=actor, channel=channel, post_url=post_url)
    except ValueError as error:
        await telegram.send_message(chat_id, str(error))
        return
    await telegram.send_message(chat_id, f"Vaga {job.id} registrada como publicada em {channel}.")


async def _start_link_flow(
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
    actor: str,
    args: list[str],
) -> None:
    if not args or not args[0].isdigit():
        await telegram.send_message(chat_id, "Uso: /vincular <id_vaga> [id_programa]")
        return
    job = await session.scalar(select(Job).where(Job.id == int(args[0])))
    if job is None:
        await telegram.send_message(chat_id, "Vaga não encontrada.")
        return
    programs_query = select(ReferralProgram).where(
        ReferralProgram.company == job.company,
        ReferralProgram.is_active.is_(True),
    )
    programs = list((await session.execute(programs_query)).scalars().all())
    selected_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if selected_id is None and len(programs) != 1:
        choices = "\n".join(f"{program.id}: {program.name} ({program.scope_type})" for program in programs)
        await telegram.send_message(
            chat_id,
            "Informe o programa: /vincular <id_vaga> <id_programa>\n" + (choices or "Nenhum programa cadastrado para a empresa."),
        )
        return
    program_id = selected_id or programs[0].id
    program = await session.scalar(select(ReferralProgram).where(ReferralProgram.id == program_id))
    if program is None or program.company != job.company or not program.is_active:
        await telegram.send_message(chat_id, "Programa inválido para esta empresa.")
        return
    await _set_link_flow(
        session,
        chat_id,
        actor,
        {"stage": "awaiting_url", "job_id": job.id, "program_id": program.id},
    )
    await telegram.send_message(
        chat_id,
        f"Envie a URL oficial para a vaga {job.id} ({job.title}). Use /cancelar para sair.",
    )


async def _receive_link_url(
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
    actor: str,
    text: str,
    flow: dict[str, Any],
) -> None:
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        await telegram.send_message(chat_id, "URL inválida. Envie uma URL absoluta http(s) ou use /cancelar.")
        return
    flow.update({"stage": "awaiting_confirmation", "url": text})
    await _set_link_flow(session, chat_id, actor, flow)
    await telegram.send_message(
        chat_id,
        "URL recebida. Confirme origem oficial e permissão de divulgação com "
        "/confirmar_link [data_expiracao_iso], ou use /cancelar.",
    )


async def _confirm_link(
    session: AsyncSession,
    telegram: TelegramClient,
    chat_id: int,
    actor: str,
    args: list[str],
    flow: dict[str, Any] | None,
) -> None:
    if not flow or flow.get("stage") != "awaiting_confirmation":
        await telegram.send_message(chat_id, "Nenhum link aguardando confirmação.")
        return
    program = await session.scalar(select(ReferralProgram).where(ReferralProgram.id == flow["program_id"]))
    job = await session.scalar(select(Job).where(Job.id == flow["job_id"]))
    if program is None or job is None or program.company != job.company:
        await telegram.send_message(chat_id, "Programa ou vaga não encontrados.")
        return
    if program.public_sharing_allowed is not True:
        await telegram.send_message(
            chat_id,
            "O programa não está explicitamente autorizado para divulgação pública; atualize-o antes de confirmar.",
        )
        return
    expires_at = _parse_optional_datetime(args[0]) if args else None
    if args and expires_at is None:
        await telegram.send_message(chat_id, "Data inválida; use ISO-8601, por exemplo 2026-12-31T23:59:59Z.")
        return
    session.add(
        ReferralLink(
            program_id=program.id,
            job_id=job.id,
            url=flow["url"],
            source="MANUAL",
            verified_at=utcnow(),
            expires_at=expires_at,
            is_active=True,
            verified_by=actor,
            notes="Confirmado manualmente pelo administrador no Telegram.",
        )
    )
    await session.flush()
    resolution = await ReferralResolver().apply_resolution(session, job, actor=actor)
    await _clear_link_flow(session, chat_id, actor)
    await telegram.send_message(chat_id, f"Link cadastrado. Estado da vaga: {resolution.status}. {resolution.reason}")


async def _get_link_flow(session: AsyncSession, chat_id: int, actor: str) -> dict[str, Any] | None:
    state = await session.scalar(select(BotState).where(BotState.key == _flow_key(chat_id, actor)))
    if state is None:
        return None
    try:
        flow = json.loads(state.value)
    except json.JSONDecodeError:
        return None
    expires = flow.get("expires_at")
    if not isinstance(expires, str) or _parse_optional_datetime(expires) is None:
        return None
    if _parse_optional_datetime(expires) <= datetime.now(timezone.utc):
        await _clear_link_flow(session, chat_id, actor)
        return None
    return flow


async def _set_link_flow(session: AsyncSession, chat_id: int, actor: str, flow: dict[str, Any]) -> None:
    flow["expires_at"] = (datetime.now(timezone.utc) + LINK_FLOW_TTL).isoformat()
    key = _flow_key(chat_id, actor)
    state = await session.scalar(select(BotState).where(BotState.key == key))
    if state is None:
        session.add(BotState(key=key, value=json.dumps(flow)))
    else:
        state.value = json.dumps(flow)
        state.updated_at = utcnow()
    await session.flush()


async def _clear_link_flow(session: AsyncSession, chat_id: int, actor: str) -> None:
    state = await session.scalar(select(BotState).where(BotState.key == _flow_key(chat_id, actor)))
    if state is not None:
        await session.delete(state)
        await session.flush()


def _flow_key(chat_id: int, actor: str) -> str:
    return f"{LINK_FLOW_PREFIX}{chat_id}:{actor}"


def _parse_optional_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _help_text() -> str:
    return (
        "Comandos:\n"
        "/novas [empresa] — vagas novas\n"
        "/pendentes [empresa] — aguardando link\n"
        "/indicacoes — estados comerciais\n"
        "/selecionadas [empresa] — fila editorial\n"
        "/publicadas — registros manuais\n"
        "/vaga <id> — detalhes\n"
        "/vincular <vaga> [programa] — cadastrar link oficial\n"
        "/publicar <id> [canal] [url] — registrar publicação\n"
        "/programas — programas ativos\n"
        "/site <id> — estado da publicação no site\n"
        "/publicar_site <id> <oficial|indicacao> — preparar publicação\n"
        "/atualizar_site <id> <oficial|indicacao> — preparar atualização\n"
        "/despublicar_site <id> — retirar do site\n"
        "/pendentes_site [página] — ainda não publicadas\n"
        "/publicadas_site [página] — catálogo publicado\n"
        "/cancelar — cancelar fluxo atual"
    )


async def _summary_text(session: AsyncSession) -> str:
    jobs = await session.scalar(select(func.count(Job.id)))
    pending = await session.scalar(select(func.count(Job.id)).where(Job.referral_status == "AGUARDANDO_LINK"))
    selected = await session.scalar(
        select(func.count(Job.id)).where(Job.editorial_status.in_(["SELECIONADA", "PRONTA"]))
    )
    sent = await session.scalar(select(func.count(Notification.id)).where(Notification.status == "sent"))
    return (
        "Resumo atual:\n"
        f"Vagas: {jobs}\n"
        f"Aguardando link: {pending}\n"
        f"Na fila editorial: {selected}\n"
        f"Notificações enviadas: {sent}"
    )


async def get_update_offset(session: AsyncSession) -> int | None:
    result = await session.execute(select(BotState).where(BotState.key == "telegram_update_offset"))
    state = result.scalar_one_or_none()
    return int(state.value) if state else None


async def set_update_offset(session: AsyncSession, offset: int) -> None:
    result = await session.execute(select(BotState).where(BotState.key == "telegram_update_offset"))
    state = result.scalar_one_or_none()
    if state is None:
        session.add(BotState(key="telegram_update_offset", value=str(offset)))
    else:
        state.value = str(offset)
        state.updated_at = utcnow()
