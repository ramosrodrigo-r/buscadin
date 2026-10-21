from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Base, Job, Notification
from buscadin_bot.db.session import create_session_factory, init_db


async def test_database_schema_persists_job_and_notification() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)

    async with factory() as session:
        job = Job(
            source="test",
            source_job_id="job-1",
            source_url="https://example.test/jobs/job-1",
            application_url="https://example.test/apply/job-1",
            company="Example",
            title="Remote Analyst",
            description="Remote role",
            category="data",
            eligible_countries=["BR"],
            eligibility_status="confirmed_br",
            salary_disclosed=False,
            language_requirements=[],
            posted_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.flush()
        session.add(Notification(job_id=job.id))
        await session.commit()

        result = await session.execute(select(Job).where(Job.source_job_id == "job-1"))
        persisted = result.scalar_one()
        assert persisted.eligibility_status == "confirmed_br"

        notification = await session.execute(select(Notification).where(Notification.job_id == persisted.id))
        assert notification.scalar_one().status == "pending"

    await engine.dispose()
