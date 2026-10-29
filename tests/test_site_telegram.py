from html import unescape

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.config import Settings
from buscadin_bot.db.models import BotState, Job, SitePublication, SitePublicationEvent
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.publication_gateway import SiteApiError, SitePreviewResponse, SiteStatusResponse
from buscadin_bot.services.site_publications import SitePublicationService
from buscadin_bot.telegram.handlers import handle_update


class LocalGateway:
    """Test adapter connecting the actual transactional core to Telegram handlers."""

    def __init__(self, service, sessions):
        self.service, self.sessions = service, sessions
        self.fail_confirmation = False

    async def preview(self, job_id, **kwargs):
        result = await self.service.preview(job_id, **kwargs)
        return SitePreviewResponse(
            token=result.token, job_id=job_id, expected_version=result.expected_version,
            public=result.snapshot["public"], destination_type=result.snapshot["destination"]["type"],
            destination_url=result.snapshot["destination"]["url"], expires_at=result.expires_at.isoformat(),
        )

    async def confirm(self, token, *, actor):
        result = await self.service.confirm(token, actor=actor)
        if self.fail_confirmation:
            raise SiteApiError("Resultado não confirmado. Consulte /site.")
        return await self.status(result.job_id, actor=actor)

    async def status(self, job_id, *, actor):
        async with self.sessions() as session:
            row = await session.get(SitePublication, job_id)
            job = await session.get(Job, job_id)
            return SiteStatusResponse(
                job_id=job_id, version=row.version if row else 0,
                status=row.status if row else "NAO_PUBLICADA", title=job.title,
                application_suspended=row.application_suspended if row else False,
            )

    async def unpublish(self, job_id, **kwargs):
        await self.service.unpublish(job_id, **kwargs)
        return await self.status(job_id, actor=kwargs["actor"])


class Telegram:
    def __init__(self):
        self.messages = []
        self.answers = []

    async def send_message(self, chat_id, text, *, reply_markup=None, **kwargs):
        self.messages.append((text, reply_markup))

    async def answer_callback_query(self, callback_query_id, text=None):
        self.answers.append(text)


@pytest.fixture
async def environment(tmp_path):
    # Distinct local stores emulate a separate private backend; bot never writes
    # platform tables through its polling session.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}")
    bot_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot.db'}")
    await init_db(engine)
    await init_db(bot_engine)
    sessions, bot_sessions = create_session_factory(engine), create_session_factory(bot_engine)
    async with sessions.begin() as session:
        session.add(Job(id=1, source="test", source_job_id="1", title="Video <annotator>", company="Example",
                        source_url="https://jobs.example/1", application_url="https://jobs.example/1"))
    gateway = LocalGateway(SitePublicationService(sessions, admin_actor="77", official_domains=["jobs.example"]), sessions)
    settings = Settings(_env_file=None, telegram_admin_chat_id=55, telegram_admin_user_id=77)
    telegram = Telegram()

    async def dispatch(text=None, callback=None, actor=77, chat=55):
        update = {"message": {"text": text, "from": {"id": actor}, "chat": {"id": chat, "type": "private"}}} if text is not None else {
            "callback_query": {"id": "callback-1", "from": {"id": actor}, "data": callback,
                               "message": {"message_id": 5, "chat": {"id": chat, "type": "private"}}},
        }
        async with bot_sessions.begin() as session:
            await handle_update(update, session=session, telegram=telegram, settings=settings, site_gateway=gateway)

    yield dispatch, gateway, telegram, sessions, bot_sessions, settings
    await engine.dispose()
    await bot_engine.dispose()


async def prepare(dispatch, telegram, summary="Resumo editorial revisado."):
    await dispatch("/publicar_site 1 oficial")
    await dispatch(summary)
    return telegram.messages[-1][1]["inline_keyboard"][0][0]["callback_data"]


async def test_telegram_requires_summary_preview_and_explicit_confirmation(environment):
    dispatch, gateway, telegram, sessions, _, _ = environment
    callback = await prepare(dispatch, telegram)
    assert len(callback.encode()) <= 64
    assert (await gateway.status(1, actor="77")).status == "NAO_PUBLICADA"
    assert any("elegibilidade não confirmada" in text for text, _ in telegram.messages)
    assert any("sem comissão identificada" in text for text, _ in telegram.messages)
    assert any("&lt;annotator&gt;" in text for text, _ in telegram.messages)
    await dispatch(callback=callback)
    assert (await gateway.status(1, actor="77")).status == "PUBLICADA"
    assert telegram.answers == ["Processando confirmação"]
    assert "Confirmação registrada" in telegram.messages[-1][0]


@pytest.mark.parametrize("actor,chat", [(88, 55), (77, 56)])
async def test_telegram_blocks_wrong_actor_or_chat(environment, actor, chat):
    dispatch, gateway, telegram, _, _, _ = environment
    callback = await prepare(dispatch, telegram)
    await dispatch(callback=callback, actor=actor, chat=chat)
    assert (await gateway.status(1, actor="77")).status == "NAO_PUBLICADA"
    assert telegram.answers[-1] == "Não autorizado"


async def test_site_requires_user_id_even_if_legacy_chat_only_allowed(environment):
    dispatch, gateway, telegram, _, _, settings = environment
    callback = await prepare(dispatch, telegram)
    settings.telegram_admin_user_id = None
    await dispatch(callback=callback)
    assert (await gateway.status(1, actor="77")).status == "NAO_PUBLICADA"
    assert telegram.answers[-1] == "Não autorizado"


async def test_lost_response_after_commit_can_be_retried_without_duplicate(environment):
    dispatch, gateway, telegram, sessions, _, _ = environment
    callback = await prepare(dispatch, telegram)
    gateway.fail_confirmation = True
    await dispatch(callback=callback)
    assert "Resultado não confirmado" in telegram.messages[-1][0]
    gateway.fail_confirmation = False
    await dispatch(callback=callback)
    async with sessions() as session:
        assert await session.scalar(select(func.count(SitePublicationEvent.id))) == 1
    assert "Confirmação registrada" in telegram.messages[-1][0]


async def test_telegram_unpublish_and_replayed_confirmation_show_current_state(environment):
    dispatch, gateway, telegram, _, _, _ = environment
    callback = await prepare(dispatch, telegram)
    await dispatch(callback=callback)
    await dispatch("/despublicar_site 1")
    removal = telegram.messages[-1][1]["inline_keyboard"][0][0]["callback_data"]
    assert (await gateway.status(1, actor="77")).status == "PUBLICADA"
    await dispatch(callback=removal)
    await dispatch(callback=callback)
    assert "DESPUBLICADA" in telegram.messages[-1][0]


async def test_full_summary_is_escaped_and_sent_without_truncation(environment):
    dispatch, _, telegram, _, _, _ = environment
    summary = "<Experiência & requisitos> " * 300
    await prepare(dispatch, telegram, summary)
    messages = [text for text, _ in telegram.messages]
    assert all(len(text) <= 4096 for text in messages)
    assert summary.strip() in unescape("".join(messages))


async def test_cancel_clears_site_flow_and_does_not_publish(environment):
    dispatch, gateway, _, _, bot_sessions, _ = environment
    await dispatch("/publicar_site 1 oficial")
    await dispatch("/cancelar")
    async with bot_sessions() as session:
        assert await session.get(BotState, "site_flow:55:77") is None
    assert (await gateway.status(1, actor="77")).status == "NAO_PUBLICADA"
