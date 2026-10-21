from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Base, Job, ReferralLink, ReferralProgram
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.referrals import NO_PROGRAM, ReferralResolver, WAITING_LINK


async def test_referral_domain_rule_rejects_unexpected_host() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = Job(
            source="test",
            source_job_id="domain-job",
            source_url="https://source.test/job",
            application_url="https://source.test/apply",
            company="Acme",
            title="Role",
            description="Role",
            category="other",
            eligible_countries=[],
            eligibility_status="unknown",
            salary_disclosed=False,
            language_requirements=[],
        )
        session.add(job)
        await session.flush()
        program = ReferralProgram(
            company="Acme",
            name="Official",
            scope_type="GLOBAL",
            allowed_domains=["official.example"],
            public_sharing_allowed=True,
        )
        session.add(program)
        await session.flush()
        session.add(
            ReferralLink(
                program_id=program.id,
                url="https://evil.example/referral",
                source="MANUAL",
                verified_at=datetime.now(timezone.utc),
            )
        )
        resolution = await ReferralResolver().resolve_status(session, job)
    await engine.dispose()

    assert resolution.status == WAITING_LINK
    assert resolution.status != NO_PROGRAM
