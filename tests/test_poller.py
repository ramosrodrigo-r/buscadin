from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.config import Settings
from buscadin_bot.db.models import Base, BotState, Job
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.telegram.poller import TelegramPoller


class FakeTelegram:
    def __init__(self, updates: list[dict]) -> None:
        self.updates = updates
        self.answers: list[tuple[str, str | None]] = []
        self.edits: list[tuple[int, int]] = []

    async def get_updates(self, *, offset: int | None, timeout: int = 25, limit: int = 100) -> list[dict]:
        assert offset is None
        return self.updates

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        self.answers.append((callback_query_id, text))
        return True

    async def edit_message_reply_markup(self, *, chat_id: int, message_id: int, reply_markup: dict | None = None) -> bool:
        self.edits.append((chat_id, message_id))
        return True


async def test_poller_authorizes_callback_updates_and_persists_offset() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        session.add(
            Job(
                id=1,
                source="test",
                source_job_id="1",
                source_url="https://source.test/job",
                application_url="https://source.test/apply",
                company="Example",
                title="Role",
                description="Description",
                category="other",
                eligible_countries=[],
                eligibility_status="unknown",
                salary_disclosed=False,
                language_requirements=[],
                review_status="pending",
            )
        )
        await session.commit()

    telegram = FakeTelegram(
        [
            {
                "update_id": 41,
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 77},
                    "data": "approve:1",
                    "message": {"message_id": 5, "chat": {"id": 55}},
                },
            }
        ]
    )
    settings = Settings(telegram_admin_chat_id=55, telegram_admin_user_id=77)
    poller = TelegramPoller(telegram, sessions, settings)  # type: ignore[arg-type]

    processed = await poller.poll_once()

    async with sessions() as session:
        job = await session.scalar(select(Job).where(Job.id == 1))
        state = await session.scalar(select(BotState).where(BotState.key == "telegram_update_offset"))
    await engine.dispose()

    assert processed == 1
    assert job is not None and job.review_status == "approved"
    assert state is not None and state.value == "42"
    assert telegram.answers == [("callback-1", "Vaga atualizada")]
    assert telegram.edits == [(55, 5)]
