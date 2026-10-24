"""Private Telegram workflow for the site; legacy editorial commands stay separate."""

import json
import re
from datetime import timedelta
from html import escape
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.config import Settings
from buscadin_bot.db.models import BotState, utcnow
from buscadin_bot.services.publication_gateway import PublicationGateway, SiteApiError, SitePreviewResponse, SiteStatusResponse
from buscadin_bot.services.referrals import _as_utc
from buscadin_bot.services.requirements import JobRequirements, RequirementFact
from buscadin_bot.telegram.api import TelegramClient

SITE_COMMANDS = {"/publicar_site", "/atualizar_site", "/despublicar_site", "/site", "/pendentes_site", "/publicadas_site", "/requisitos_site"}


async def handle_site_update(
    update: dict[str, Any], *, session: AsyncSession, telegram: TelegramClient,
    settings: Settings, gateway: PublicationGateway | None,
) -> bool:
    """Return True only when this update belongs to the site workflow."""
    callback = update.get("callback_query")
    message = update.get("message") or (callback or {}).get("message", {})
    text = str(message.get("text") or "").strip() if callback is None else ""
    parts = text.split()
    command = parts[0].split("@", 1)[0].lower() if parts and text.startswith("/") else ""
    site_callback = isinstance(callback, dict) and str(callback.get("data", "")).startswith("site:")
    chat_id = message.get("chat", {}).get("id")
    actor_id = (callback or message).get("from", {}).get("id")
    key = f"site_flow:{chat_id}:{actor_id}"
    flow = None
    if not callback and not command and text:
        flow = await session.get(BotState, key)
    if command in {"/cancelar", "/vincular"}:
        existing = await session.get(BotState, key)
        if existing is not None:
            await session.delete(existing)
        return False  # Legacy handler also cancels its independent link flow.
    if command not in SITE_COMMANDS and not site_callback and flow is None:
        return False
    # Unlike the legacy fallback, site mutations always require BOTH identities.
    if (
        settings.telegram_admin_chat_id is None or settings.telegram_admin_user_id is None
        or chat_id != settings.telegram_admin_chat_id or actor_id != settings.telegram_admin_user_id
    ):
        if site_callback:
            await telegram.answer_callback_query(str(callback["id"]), "Não autorizado")
        return True
    if gateway is None:
        if site_callback:
            await telegram.answer_callback_query(str(callback["id"]), "Integração do site não configurada")
        else:
            await telegram.send_message(chat_id, "Integração do site ainda não configurada.")
        return True
    actor = str(actor_id)
    # Acknowledge receipt, never claim publication before the backend commit.
    if site_callback:
        await telegram.answer_callback_query(str(callback["id"]), "Processando confirmação")
    try:
        if site_callback:
            data = str(callback["data"])
            if match := re.fullmatch(r"site:confirm:([a-f0-9]{24})", data):
                result = await gateway.confirm(match[1], actor=actor)
                # Current status may differ if this is an old callback replay.
                current = await gateway.status(result.job_id, actor=actor)
                await _send_status(telegram, chat_id, current, prefix="Confirmação registrada.")
            elif match := re.fullmatch(r"site:remove:(\d+):(\d+)", data):
                result = await gateway.unpublish(
                    int(match[1]), actor=actor, expected_version=int(match[2]),
                    event_id=str(callback["id"]), reason="Retirada explícita pelo administrador no Telegram",
                )
                await _send_status(telegram, chat_id, result, prefix="Retirada registrada.")
            else:
                await telegram.send_message(chat_id, "Ação do site inválida. Gere uma nova prévia.")
            return True

        if flow is not None:
            if _as_utc(flow.updated_at) + timedelta(minutes=15) <= utcnow():
                await session.delete(flow)
                await telegram.send_message(chat_id, "Solicitação expirada. Inicie novamente o comando do site.")
                return True
            try:
                state = json.loads(flow.value)
                job_id = int(state["job_id"])
                flow_kind = state.get("kind", "publication")
            except (ValueError, KeyError, TypeError):
                await session.delete(flow)
                await telegram.send_message(chat_id, "Solicitação inválida. Gere uma nova solicitação.")
                return True
            if flow_kind == "requirements":
                try:
                    requirements = _parse_requirements(text)
                except (ValueError, ValidationError):
                    await telegram.send_message(
                        chat_id,
                        "Formato inválido. Envie as quatro linhas solicitadas e evidência para estados diferentes de desconhecido.",
                    )
                    return True
                result = await gateway.set_requirements(
                    job_id, actor=actor, requirements=requirements.model_dump(),
                )
                await telegram.send_message(
                    chat_id,
                    f"Requisitos da vaga {result.job_id} atualizados. "
                    "Uma publicação existente só muda após nova prévia e confirmação.",
                )
                await session.delete(flow)
                return True
            destination_type = state["destination_type"]
            if len(text) > 12000:
                await telegram.send_message(chat_id, "O resumo deve ter até 12000 caracteres.")
                return True
            prepared = await gateway.preview(job_id, actor=actor, destination_type=destination_type, summary=text)
            await _send_preview(telegram, chat_id, prepared)
            await session.delete(flow)
            return True

        if command in {"/publicadas_site", "/pendentes_site"}:
            page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            if page < 1:
                await telegram.send_message(chat_id, "A página deve ser maior que zero.")
                return True
            status = "PUBLICADA" if command == "/publicadas_site" else "NAO_PUBLICADA"
            rows = await gateway.listing(actor=actor, status=status, page=page)
            listing = "\n".join(f"{row.job_id} — {row.title} ({row.status})" for row in rows)
            await _send_text(telegram, chat_id, listing or "Nenhuma vaga encontrada nesta página.")
            await telegram.send_message(chat_id, f"Página {page}. Para continuar: {command} {page + 1}")
            return True

        if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) < 1:
            await telegram.send_message(chat_id, _usage(command))
            return True
        job_id = int(parts[1])
        if command == "/requisitos_site":
            await gateway.status(job_id, actor=actor)
            value = json.dumps({"kind": "requirements", "job_id": job_id})
            existing = await session.get(BotState, key)
            if existing is None:
                session.add(BotState(key=key, value=value))
            else:
                existing.value, existing.updated_at = value, utcnow()
            await telegram.send_message(
                chat_id,
                "Envie quatro linhas no formato:\n"
                "educacao: exigida|nao_exigida|desconhecida\n"
                "evidencia_educacao: trecho da fonte\n"
                "experiencia: exigida|nao_exigida|desconhecida\n"
                "evidencia_experiencia: trecho da fonte\n\n"
                "Use /cancelar para sair. Requisito diferente de desconhecido precisa de evidência.",
            )
        elif command in {"/publicar_site", "/atualizar_site"}:
            if len(parts) != 3 or parts[2].lower() not in {"oficial", "indicacao"}:
                await telegram.send_message(chat_id, _usage(command))
                return True
            # Verify the platform knows this stable ID before collecting a summary.
            await gateway.status(job_id, actor=actor)
            legacy_flow = await session.get(BotState, f"link_flow:{chat_id}:{actor}")
            if legacy_flow is not None:
                await session.delete(legacy_flow)
            destination_type = "OFFICIAL" if parts[2].lower() == "oficial" else "REFERRAL"
            existing = await session.get(BotState, key)
            value = json.dumps({"job_id": job_id, "destination_type": destination_type})
            if existing is None:
                session.add(BotState(key=key, value=value))
            else:
                existing.value, existing.updated_at = value, utcnow()
            await telegram.send_message(chat_id,
                "Envie o resumo editorial que aparecerá no site, sem inventar requisitos. "
                "Use conteúdo cuja publicação é permitida. Depois mostrarei a prévia e o destino "
                "para sua confirmação. Use /cancelar para sair.")
        elif command == "/site":
            await _send_status(telegram, chat_id, await gateway.status(job_id, actor=actor))
        elif command == "/despublicar_site":
            result = await gateway.status(job_id, actor=actor)
            if result.status != "PUBLICADA":
                await _send_status(telegram, chat_id, result)
            else:
                await telegram.send_message(chat_id,
                    f"Retirar a vaga {job_id} do site?\n{escape(result.title)}",
                    reply_markup={"inline_keyboard": [[{
                        "text": "Confirmar retirada", "callback_data": f"site:remove:{job_id}:{result.version}",
                    }]]})
    except SiteApiError as error:
        await telegram.send_message(chat_id, escape(str(error)))
    return True


def _usage(command: str) -> str:
    suffix = " &lt;id&gt; &lt;oficial|indicacao&gt;" if command in {"/publicar_site", "/atualizar_site"} else " &lt;id&gt;"
    return "Uso: " + command + suffix


def _parse_requirements(text: str) -> JobRequirements:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip().lower().replace("ç", "c").replace("ã", "a").replace("ê", "e")
        values[key] = value.strip()
    status_map = {
        "exigida": "required", "exigido": "required", "required": "required",
        "nao_exigida": "not_required", "não_exigida": "not_required",
        "nao exigida": "not_required", "não exigida": "not_required", "not_required": "not_required",
        "desconhecida": "unknown", "desconhecido": "unknown", "unknown": "unknown",
    }
    education_status = status_map.get(values.get("educacao", "desconhecida"))
    experience_status = status_map.get(values.get("experiencia", "desconhecida"))
    if education_status is None or experience_status is None:
        raise ValueError("Status de requisito inválido")
    return JobRequirements(
        education=RequirementFact(status=education_status, evidence=values.get("evidencia_educacao") or None),
        experience=RequirementFact(status=experience_status, evidence=values.get("evidencia_experiencia") or None),
    )


async def _send_status(telegram: TelegramClient, chat_id: int, result: SiteStatusResponse, prefix: str = "") -> None:
    lines = [prefix, f"Vaga {result.job_id}: {result.title}", f"Site: {result.status} · versão {result.version}"]
    if result.application_suspended:
        lines.append("Candidatura suspensa. Revise o destino antes de atualizar.")
    if result.status == "PUBLICADA" and result.public_url:
        lines.append(result.public_url)
    await _send_text(telegram, chat_id, "\n".join(line for line in lines if line))


async def _send_preview(telegram: TelegramClient, chat_id: int, preview: SitePreviewResponse) -> None:
    public = preview.public
    lines = [f"Prévia da vaga {preview.job_id} — ainda não publicada", f"{public.get('title', '')} · {public.get('company', '')}"]
    labels = {
        "category": "Categoria", "employment_type": "Vínculo", "remote_type": "Modalidade",
        "eligible_countries": "Países", "language_requirements": "Idiomas",
        "salary_min": "Remuneração mínima", "salary_max": "Remuneração máxima",
        "currency": "Moeda", "salary_period": "Período", "posted_at": "Data na fonte",
        "source": "Fonte", "source_url": "URL da fonte",
    }
    for key, label in labels.items():
        value = public.get(key)
        if value is not None and value != [] and value != "":
            lines.append(f"{label}: {', '.join(str(item) for item in value) if isinstance(value, list) else value}")
    lines.append("Brasil: confirmado na fonte" if public.get("eligibility_status") == "confirmed_br" else "Brasil: elegibilidade não confirmada")
    requirements = public.get("requirements") or {}
    statuses = {"required": "exigida", "not_required": "não exigida", "unknown": "não informada"}
    for key, label in (("education", "Graduação"), ("experience", "Experiência")):
        lines.append(f"{label}: {statuses.get(requirements.get(key), 'não informada')}")
    if public.get("commercial_disclosure"):
        lines.append("Aviso público: " + public["commercial_disclosure"])
    lines.extend(["", str(public.get("summary", "")), "", "Destino: " + preview.destination_url])
    lines.append("Com indicação validada." if preview.destination_type == "REFERRAL" else "Candidatura oficial, sem comissão identificada.")
    lines.append("Prévia válida até: " + preview.expires_at)
    await _send_text(telegram, chat_id, "\n".join(lines))
    await telegram.send_message(chat_id,
        "Confirme somente se o conteúdo e o destino acima estiverem corretos. "
        "Se o Brasil não estiver confirmado, essa incerteza aparecerá no site.",
        reply_markup={"inline_keyboard": [[{
            "text": "Confirmar publicação" if preview.destination_type == "REFERRAL" else "Confirmar com link oficial",
            "callback_data": f"site:confirm:{preview.token}",
        }]]})


async def _send_text(telegram: TelegramClient, chat_id: int, text: str) -> None:
    """Escape before sizing chunks; never split an HTML entity or omit the summary."""
    chunk = ""
    for character in text:
        encoded = escape(character)
        if len(chunk) + len(encoded) > 3500:
            await telegram.send_message(chat_id, chunk)
            chunk = ""
        chunk += encoded
    if chunk:
        await telegram.send_message(chat_id, chunk)
