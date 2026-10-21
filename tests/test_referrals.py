from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Base, Job, Referral
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.referrals import ReferralResolver


def make_job() -> Job:
    return Job(
        source="test",
        source_job_id="job-1",
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


async def test_resolver_prefers_valid_job_referral_over_company_referral() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        await session.flush()
        session.add_all(
            [
                Referral(
                    company="Example",
                    referral_url="https://official.test/company",
                    scope="company",
                    approved_for_public_sharing=True,
                    verified_at=datetime.now(timezone.utc),
                ),
                Referral(
                    company="Example",
                    source_job_id="job-1",
                    referral_url="https://official.test/job",
                    scope="job",
                    approved_for_public_sharing=True,
                    verified_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()
        resolved = await ReferralResolver().resolve(session, job)
    await engine.dispose()

    assert resolved is not None and resolved.referral_url == "https://official.test/job"


async def test_resolver_rejects_unapproved_expired_and_invalid_referrals() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        session.add_all(
            [
                Referral(
                    company="Example",
                    referral_url="https://official.test/unapproved",
                    scope="company",
                    approved_for_public_sharing=False,
                    verified_at=datetime.now(timezone.utc),
                ),
                Referral(
                    company="Example",
                    referral_url="https://official.test/expired",
                    scope="company",
                    approved_for_public_sharing=True,
                    verified_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
                Referral(
                    company="Example",
                    referral_url="javascript:alert(1)",
                    scope="company",
                    approved_for_public_sharing=True,
                    verified_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()
        resolved = await ReferralResolver().resolve(session, job)
    await engine.dispose()

    assert resolved is None
