from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from datetime import datetime, timezone

from buscadin_bot.db.models import Base, Job, Notification, ReferralLink, ReferralProgram
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.notifications import NotificationWorker
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.telegram.api import SentMessage, TelegramApiError


class FakeTelegram:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.texts: list[str] = []
        self.markups: list[dict] = []

    async def send_message(self, chat_id: int, text: str, *, reply_markup: dict) -> SentMessage:
        self.calls += 1
        self.texts.append(text)
        self.markups.append(reply_markup)
        if self.fail:
            raise TelegramApiError("temporary", retry_after=3)
        return SentMessage(message_id=321, raw={"message_id": 321})


async def make_notification_db() -> tuple[object, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = Job(
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
        )
        session.add(job)
        await session.flush()
        session.add(Notification(job_id=job.id))
        await session.commit()
    return engine, sessions


async def test_outbox_marks_successful_message_sent() -> None:
    engine, sessions = await make_notification_db()
    telegram = FakeTelegram()
    async with sessions() as session:
        sent, failed = await NotificationWorker().send_pending(session, telegram, chat_id=1)
    async with sessions() as session:
        notification = await session.scalar(select(Notification))
    await engine.dispose()

    assert (sent, failed) == (1, 0)
    assert notification is not None and notification.status == "sent" and notification.telegram_message_id == 321


async def test_outbox_records_retryable_failure() -> None:
    engine, sessions = await make_notification_db()
    telegram = FakeTelegram(fail=True)
    async with sessions() as session:
        sent, failed = await NotificationWorker().send_pending(session, telegram, chat_id=1)
    async with sessions() as session:
        notification = await session.scalar(select(Notification))
    await engine.dispose()

    assert (sent, failed) == (0, 1)
    assert notification is not None and notification.status == "failed"
    assert notification.attempts == 1 and notification.next_attempt_at is not None


async def test_outbox_uses_validated_link_and_editorial_keyboard() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = Job(
            source="test",
            source_job_id="editorial-job",
            source_url="https://source.test/job",
            application_url="https://source.test/apply",
            company="Example",
            title="Role",
            description="Description",
            category="other",
            eligible_countries=["BR"],
            eligibility_status="confirmed_br",
            salary_disclosed=False,
            language_requirements=[],
        )
        session.add(job)
        await session.flush()
        program = ReferralProgram(
            company="Example",
            name="Official",
            scope_type="POR_VAGA",
            public_sharing_allowed=True,
        )
        session.add(program)
        await session.flush()
        session.add(
            ReferralLink(
                program_id=program.id,
                job_id=job.id,
                url="https://official.test/referral",
                source="MANUAL",
                verified_at=datetime.now(timezone.utc),
            )
        )
        session.add(Notification(job_id=job.id))
        await session.flush()
        telegram = FakeTelegram()
        sent, failed = await NotificationWorker(referral_resolver=ReferralResolver()).send_pending(
            session,
            telegram,  # type: ignore[arg-type]
            chat_id=1,
        )
    await engine.dispose()

    assert (sent, failed) == (1, 0)
    assert "LINK_VALIDADO" in telegram.texts[0]
    assert "official.test/referral" in telegram.texts[0]
    assert telegram.markups[0]["inline_keyboard"][0][0]["callback_data"] == "select:1"
