from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import AuditEvent, EditorialPublication, Job, Notification, ReferralLink, ReferralProgram
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.editorial import prepare_editorial_text, set_editorial_status
from buscadin_bot.services.referrals import LINK_VALIDATED, NO_PROGRAM, WAITING_LINK, ReferralResolver


def make_job() -> Job:
    return Job(
        source="test",
        source_job_id="job-2",
        source_url="https://source.test/job-2",
        application_url="https://source.test/apply-2",
        company="Acme",
        title="Data Annotator",
        description="Remote role",
        category="data_labeling",
        eligible_countries=["BR"],
        eligibility_status="confirmed_br",
        salary_disclosed=False,
        language_requirements=[],
    )


async def test_resolution_prefers_job_link_over_global_link() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        await session.flush()
        global_program = ReferralProgram(
            company="Acme",
            name="Global program",
            scope_type="GLOBAL",
            public_sharing_allowed=True,
        )
        job_program = ReferralProgram(
            company="Acme",
            name="Job program",
            scope_type="POR_VAGA",
            public_sharing_allowed=True,
        )
        session.add_all([global_program, job_program])
        await session.flush()
        session.add_all(
            [
                ReferralLink(
                    program_id=global_program.id,
                    url="https://official.test/global",
                    source="MANUAL",
                    verified_at=datetime.now(timezone.utc),
                ),
                ReferralLink(
                    program_id=job_program.id,
                    job_id=job.id,
                    url="https://official.test/job",
                    source="MANUAL",
                    verified_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.flush()
        resolution = await ReferralResolver().apply_resolution(session, job, actor="admin")
        await session.commit()
    await engine.dispose()

    assert resolution.status == LINK_VALIDATED
    assert resolution.link is not None and resolution.link.url.endswith("/job")


async def test_missing_or_unpermitted_program_never_becomes_validated() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        await session.flush()
        session.add(
            ReferralProgram(
                company="Acme",
                name="Potential program",
                scope_type="POR_VAGA",
                public_sharing_allowed=None,
            )
        )
        await session.flush()
        waiting = await ReferralResolver().resolve_status(session, job)
        session.add(
            ReferralProgram(
                company="Other",
                name="Other program",
                scope_type="GLOBAL",
                public_sharing_allowed=True,
            )
        )
        await session.commit()
    await engine.dispose()

    assert waiting.status == WAITING_LINK
    assert waiting.link is None


async def test_no_program_is_distinct_from_waiting_for_link() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        resolution = await ReferralResolver().resolve_status(session, make_job())
    await engine.dispose()

    assert resolution.status == NO_PROGRAM
    assert "NAO_IDENTIFICADO" in resolution.reason


async def test_expiring_link_reopens_ready_editorial_and_requeues_notice() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        await session.flush()
        program = ReferralProgram(
            company="Acme",
            name="Program",
            scope_type="POR_VAGA",
            public_sharing_allowed=True,
        )
        session.add(program)
        await session.flush()
        link = ReferralLink(
            program_id=program.id,
            job_id=job.id,
            url="https://official.test/job",
            source="MANUAL",
            verified_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(link)
        job.editorial_status = "PRONTA"
        job.referral_status = LINK_VALIDATED
        session.add(Notification(job_id=job.id, status="sent", last_notified_referral_status=LINK_VALIDATED))
        await session.flush()
        resolution = await ReferralResolver().apply_resolution(session, job, actor="system")
        await session.flush()
        events = await session.execute(select(AuditEvent).where(AuditEvent.job_id == job.id))
        notification = await session.scalar(select(Notification).where(Notification.job_id == job.id))
        await session.commit()
    await engine.dispose()

    assert resolution.status == WAITING_LINK
    assert job.editorial_status == "SELECIONADA"
    assert notification is not None and notification.status == "pending"
    assert len(events.scalars().all()) >= 1


async def test_editorial_transition_creates_publication_and_transparent_text() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = make_job()
        session.add(job)
        await session.flush()
        await set_editorial_status(session, job, "SELECIONADA", actor="admin")
        await set_editorial_status(session, job, "PRONTA", actor="admin")
        await set_editorial_status(session, job, "PUBLICADA", actor="admin", channel="instagram")
        await session.flush()
        publications = await session.execute(select(EditorialPublication).where(EditorialPublication.job_id == job.id))
        await session.commit()
    await engine.dispose()

    assert job.editorial_status == "PUBLICADA"
    assert len(publications.scalars().all()) == 1
    assert "SEM_PROGRAMA" in prepare_editorial_text(job)
    assert "candidatura oficial" in prepare_editorial_text(job)
