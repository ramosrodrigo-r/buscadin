from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.config import Settings
from buscadin_bot.db.models import Base, Job, ReferralLink, ReferralProgram
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.telegram.handlers import handle_update


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> object:
        self.messages.append(text)
        return object()

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        return True

    async def edit_message_reply_markup(self, **kwargs: object) -> bool:
        return True


def update(text: str) -> dict:
    return {
        "message": {
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 77},
            "text": text,
        }
    }


async def test_vincular_flow_records_manual_url_and_resolves_job() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    telegram = FakeTelegram()
    settings = Settings(telegram_admin_chat_id=1, telegram_admin_user_id=77)
    async with sessions() as session:
        job = Job(
            source="test",
            source_job_id="job-1",
            source_url="https://source.test/job",
            application_url="https://source.test/apply",
            company="Acme",
            title="Role",
            description="Remote",
            category="other",
            eligible_countries=["BR"],
            eligibility_status="confirmed_br",
            salary_disclosed=False,
            language_requirements=[],
        )
        session.add(job)
        await session.flush()
        program = ReferralProgram(
            company="Acme",
            name="Official program",
            scope_type="POR_VAGA",
            public_sharing_allowed=True,
        )
        session.add(program)
        await session.flush()
        await handle_update(update("/vincular 1 1"), session=session, telegram=telegram, settings=settings)  # type: ignore[arg-type]
        await handle_update(
            update("https://official.example/acme-job"),
            session=session,
            telegram=telegram,
            settings=settings,
        )  # type: ignore[arg-type]
        await handle_update(update("/confirmar_link"), session=session, telegram=telegram, settings=settings)  # type: ignore[arg-type]
        await session.flush()
        link = await session.scalar(select(ReferralLink))
        await session.commit()
    await engine.dispose()

    assert link is not None and link.url == "https://official.example/acme-job"
    assert telegram.messages[0].startswith("Envie a URL")
    assert "URL recebida" in telegram.messages[1]
    assert "LINK_VALIDADO" in telegram.messages[2]
