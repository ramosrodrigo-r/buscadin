from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Base, Job, Notification
from buscadin_bot.db.repository import JobRepository
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.collector import Collector
from buscadin_bot.sources.base import RawJob


class FakeSource:
    name = "fake"

    async def fetch_jobs(self) -> list[RawJob]:
        return [
            RawJob(
                source="fake",
                source_job_id="same-id",
                title="Brazil Data Annotator",
                company="Example",
                description="Brazil accepted",
                source_url="https://source.test/job",
                application_url="https://source.test/apply",
                location_restrictions=["Brazil"],
                min_salary=None,
                max_salary=None,
                posted_at=datetime.now(timezone.utc),
            )
        ]


async def test_collection_is_idempotent_for_jobs_and_notifications() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    collector = Collector(JobRepository())

    async with factory() as session:
        first = await collector.collect_source(session, FakeSource())
        second = await collector.collect_source(session, FakeSource())
        jobs = await session.execute(select(Job))
        notifications = await session.execute(select(Notification))

    assert first.inserted == 1
    assert first.notifications_queued == 1
    assert second.inserted == 0
    assert second.updated == 1
    assert len(jobs.scalars().all()) == 1
    assert len(notifications.scalars().all()) == 1
    await engine.dispose()
