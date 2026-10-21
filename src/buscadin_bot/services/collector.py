"""Collection orchestration from source connector to persistent outbox."""

import logging
from dataclasses import dataclass
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.db.repository import JobRepository
from buscadin_bot.services.classifier import classify_category, classify_eligibility
from buscadin_bot.services.normalizer import normalize_raw_job
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.sources.base import JobSource

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectionResult:
    source: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    notifications_queued: int = 0
    failed: int = 0
    error: str | None = None


class Collector:
    def __init__(
        self,
        repository: JobRepository | None = None,
        referral_resolver: ReferralResolver | None = None,
    ) -> None:
        self.repository = repository or JobRepository()
        self.referral_resolver = referral_resolver or ReferralResolver()

    async def collect_source(self, session: AsyncSession, source: JobSource) -> CollectionResult:
        result = CollectionResult(source=source.name)
        try:
            raw_jobs: Sequence = await source.fetch_jobs()
            result.fetched = len(raw_jobs)
            for raw in raw_jobs:
                classification = classify_eligibility(raw)
                data = normalize_raw_job(
                    raw,
                    category=classify_category(raw),
                    eligibility=classification,
                )
                job, is_new = await self.repository.upsert_job(session, data)
                await self.referral_resolver.apply_resolution(session, job)
                if is_new:
                    result.inserted += 1
                    if data.eligibility_status != "excluded_br":
                        result.notifications_queued += 1
                else:
                    result.updated += 1
            await session.commit()
        except Exception as error:
            await session.rollback()
            result.failed = 1
            result.error = str(error)
            logger.exception("job source collection failed", extra={"source": source.name})
        return result
