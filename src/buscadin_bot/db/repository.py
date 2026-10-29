"""Persistence operations with idempotent job and notification upserts."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.db.models import Job, Notification, utcnow
from buscadin_bot.services.normalizer import NormalizedJob


class JobRepository:
    async def upsert_job(self, session: AsyncSession, data: NormalizedJob) -> tuple[Job, bool]:
        result = await session.execute(
            select(Job).where(Job.source == data.source, Job.source_job_id == data.source_job_id).with_for_update()
        )
        job = result.scalar_one_or_none()
        is_new = job is None
        if job is None:
            job = Job(source=data.source, source_job_id=data.source_job_id)
            session.add(job)

        # An explicitly edited draft belongs to the curator. Recollection records
        # its presence without silently replacing approved evidence or URLs.
        if not is_new and job.review_status == "admin_curated":
            job.last_seen_at = utcnow()
            job.last_checked_at = utcnow()
            return job, False

        job.source_url = data.source_url
        job.application_url = data.application_url
        job.company = data.company
        job.title = data.title
        job.description = data.description
        job.category = data.category
        job.employment_type = data.employment_type
        job.remote_type = data.remote_type
        job.eligible_countries = data.eligible_countries
        job.eligibility_status = data.eligibility_status
        job.salary_min = data.salary_min
        job.salary_max = data.salary_max
        job.currency = data.currency
        job.salary_period = data.salary_period
        job.salary_disclosed = data.salary_disclosed
        job.language_requirements = data.language_requirements
        job.requirements = data.requirements
        job.evidence = data.evidence
        job.posted_at = data.posted_at
        job.last_seen_at = utcnow()
        job.last_checked_at = utcnow()
        if is_new:
            job.first_seen_at = utcnow()
            job.status = "active"
            job.review_status = "pending"
            await session.flush()
            if data.eligibility_status != "excluded_br":
                session.add(Notification(job_id=job.id))
        return job, is_new

    async def pending_notifications(self, session: AsyncSession, limit: int) -> list[Notification]:
        result = await session.execute(
            select(Notification)
            .where(Notification.status == "pending")
            .order_by(Notification.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_jobs(self, session: AsyncSession) -> int:
        from sqlalchemy import func

        result = await session.execute(select(func.count(Job.id)))
        return int(result.scalar_one())

    async def count_notifications(self, session: AsyncSession) -> int:
        from sqlalchemy import func

        result = await session.execute(select(func.count(Notification.id)))
        return int(result.scalar_one())
