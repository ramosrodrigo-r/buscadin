from datetime import timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import (
    Job, ReferralLink, ReferralProgram, SiteAlert, SitePreview,
    SitePublication, SitePublicationEvent, utcnow,
)
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.publication_policy import PublicationRejected
from buscadin_bot.services.site_publications import PublicationConflict, SitePublicationService


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.environ.get("BUSCADIN_TEST_POSTGRES_URL") else []))
async def catalogue(tmp_path, request):
    admin_engine = None
    if request.param == "postgresql":
        url = os.environ["BUSCADIN_TEST_POSTGRES_URL"]
        schema = "test_publication_" + uuid4().hex
        admin_engine = create_async_engine(url)
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalogue.db'}")
    async def cleanup():
        await engine.dispose()
        if admin_engine is not None:
            async with admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin_engine.dispose()
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions.begin() as session:
        job = Job(
            source="test", source_job_id="video-1", company="Example",
            title="Video annotator", description="Unapproved source description",
            source_url="https://source.example/1", application_url="https://jobs.example/1",
            eligibility_status="unknown", category="data_labeling",
        )
        session.add(job)
        await session.flush()
        job_id = job.id
    service = SitePublicationService(sessions, admin_actor="123", official_domains=["jobs.example"])
    try:
        yield service, sessions, job_id
    finally:
        await cleanup()


async def preview(service, job_id, destination_type="OFFICIAL"):
    return await service.preview(
        job_id, actor="123", destination_type=destination_type,
        summary="Resumo revisado pelo administrador.",
    )


async def add_referral(sessions, job_id):
    async with sessions.begin() as session:
        program = ReferralProgram(
            company="Example", name="Official program", scope_type="POR_VAGA",
            public_sharing_allowed=True, allowed_domains=["ref.example"],
        )
        session.add(program)
        await session.flush()
        link = ReferralLink(
            program_id=program.id, job_id=job_id, url="https://ref.example/original?ref=secret",
            source="MANUAL", verified_at=utcnow(), expires_at=utcnow() + timedelta(days=1),
        )
        session.add(link)
        await session.flush()
        return link.id


async def test_preview_is_private_until_confirmation_and_preserves_unknown(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    async with sessions() as session:
        row = await session.get(SitePublication, job_id)
        assert row.status == "NAO_PUBLICADA"
        assert row.public_snapshot == {}
    assert await service.destination(job_id) is None
    result = await service.confirm(prepared.token, actor="123")
    assert result.status == "PUBLICADA"
    async with sessions() as session:
        row = await session.get(SitePublication, job_id)
        assert row.public_snapshot["eligibility_status"] == "unknown"
        assert row.public_snapshot["summary"] == "Resumo revisado pelo administrador."
        assert "description" not in row.public_snapshot
        assert "destination" not in row.public_snapshot
        assert (await session.get(Job, job_id)).editorial_status == "NOVA"
    assert await service.destination(job_id) == "https://jobs.example/1"


async def test_confirmation_retry_returns_committed_result_without_duplicate(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    first = await service.confirm(prepared.token, actor="123")
    assert await service.confirm(prepared.token, actor="123") == first
    async with sessions() as session:
        assert await session.scalar(select(func.count(SitePublicationEvent.id))) == 1


async def test_other_actor_cannot_preview_or_confirm(catalogue):
    service, _, job_id = catalogue
    with pytest.raises(PublicationRejected):
        await service.preview(job_id, actor="attacker", destination_type="OFFICIAL", summary="a")
    prepared = await preview(service, job_id)
    with pytest.raises(PublicationRejected):
        await service.confirm(prepared.token, actor="attacker")


async def test_changed_content_requires_new_preview(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    async with sessions.begin() as session:
        (await session.get(Job, job_id)).title = "Different role"
    with pytest.raises(PublicationConflict):
        await service.confirm(prepared.token, actor="123")
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).status == "NAO_PUBLICADA"
        assert await session.scalar(select(func.count(SitePublicationEvent.id))) == 0


async def test_expired_preview_is_rejected(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    async with sessions.begin() as session:
        (await session.get(SitePreview, prepared.token)).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(PublicationConflict):
        await service.confirm(prepared.token, actor="123")


async def test_new_collection_does_not_rewrite_published_snapshot(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    await service.confirm(prepared.token, actor="123")
    async with sessions.begin() as session:
        job = await session.get(Job, job_id)
        job.title = "Updated source title"
        job.description = "New source content"
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).public_snapshot["title"] == "Video annotator"
    updated = await preview(service, job_id)
    await service.confirm(updated.token, actor="123")
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).public_snapshot["title"] == "Updated source title"
        events = list((await session.scalars(select(SitePublicationEvent).order_by(SitePublicationEvent.id))).all())
        assert len(events) == 2
        assert events[0].snapshot["public"]["title"] == "Video annotator"


async def test_two_previews_of_same_version_only_allow_one_decision(catalogue):
    service, _, job_id = catalogue
    first, second = await preview(service, job_id), await preview(service, job_id)
    await service.confirm(first.token, actor="123")
    with pytest.raises(PublicationConflict):
        await service.confirm(second.token, actor="123")


async def test_expired_referral_suspends_and_enqueues_only_one_alert(catalogue):
    service, sessions, job_id = catalogue
    link_id = await add_referral(sessions, job_id)
    prepared = await preview(service, job_id, "REFERRAL")
    await service.confirm(prepared.token, actor="123")
    assert await service.destination(job_id) == "https://ref.example/original?ref=secret"
    async with sessions.begin() as session:
        (await session.get(ReferralLink, link_id)).expires_at = utcnow() - timedelta(seconds=1)
    assert await service.destination(job_id) is None
    assert await service.destination(job_id) is None
    async with sessions() as session:
        publication = await session.get(SitePublication, job_id)
        assert publication.application_suspended
        assert publication.destination_snapshot["type"] == "REFERRAL"
        assert await session.scalar(select(func.count(SiteAlert.id))) == 1
    official = await preview(service, job_id)
    assert await service.destination(job_id) is None
    await service.confirm(official.token, actor="123")
    assert await service.destination(job_id) == "https://jobs.example/1"


async def test_new_referral_does_not_replace_approved_official_url(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    await service.confirm(prepared.token, actor="123")
    await add_referral(sessions, job_id)
    assert await service.destination(job_id) == "https://jobs.example/1"


async def test_changed_referral_after_preview_cannot_be_confirmed(catalogue):
    service, sessions, job_id = catalogue
    link_id = await add_referral(sessions, job_id)
    prepared = await preview(service, job_id, "REFERRAL")
    async with sessions.begin() as session:
        (await session.get(ReferralLink, link_id)).url = "https://ref.example/changed"
    with pytest.raises(PublicationConflict):
        await service.confirm(prepared.token, actor="123")


async def test_unpublish_is_idempotent_and_does_not_allow_old_preview_to_republish(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    published = await service.confirm(prepared.token, actor="123")
    args = dict(actor="123", expected_version=published.version, event_id="callback-1", reason="Revisão")
    removed = await service.unpublish(job_id, **args)
    assert await service.unpublish(job_id, **args) == removed
    assert await service.destination(job_id) is None
    # A retry acknowledges the original operation, but must never republish.
    assert await service.confirm(prepared.token, actor="123") == published
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).status == "DESPUBLICADA"


async def test_excluded_brazil_cannot_publish_even_after_preview(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    async with sessions.begin() as session:
        (await session.get(Job, job_id)).eligibility_status = "excluded_br"
    with pytest.raises(PublicationRejected):
        await service.confirm(prepared.token, actor="123")


async def test_concurrent_confirmations_create_one_version(catalogue):
    import asyncio

    service, sessions, job_id = catalogue
    first, second = await preview(service, job_id), await preview(service, job_id)
    outcomes = await asyncio.gather(
        service.confirm(first.token, actor="123"),
        service.confirm(second.token, actor="123"), return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, PublicationConflict) for item in outcomes) == 1
    async with sessions() as session:
        assert await session.scalar(select(func.count(SitePublicationEvent.id))) == 1


async def test_concurrent_duplicate_callback_returns_same_result(catalogue):
    import asyncio

    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    first, second = await asyncio.gather(
        service.confirm(prepared.token, actor="123"),
        service.confirm(prepared.token, actor="123"),
    )
    assert first == second
    async with sessions() as session:
        assert await session.scalar(select(func.count(SitePublicationEvent.id))) == 1


async def test_reconciliation_retires_confirmed_inactive_job_without_click(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    await service.confirm(prepared.token, actor="123")
    async with sessions.begin() as session:
        (await session.get(Job, job_id)).status = "inactive"
    assert await service.reconcile(batch_size=1) == 1
    assert await service.reconcile(batch_size=1) == 0
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).status == "DESPUBLICADA"
        assert await session.scalar(select(func.count(SiteAlert.id))) == 1


async def test_reconciliation_suspends_revoked_program_without_click(catalogue):
    service, sessions, job_id = catalogue
    link_id = await add_referral(sessions, job_id)
    prepared = await preview(service, job_id, "REFERRAL")
    await service.confirm(prepared.token, actor="123")
    async with sessions.begin() as session:
        link = await session.get(ReferralLink, link_id)
        (await session.get(ReferralProgram, link.program_id)).public_sharing_allowed = False
    await service.reconcile()
    async with sessions() as session:
        assert (await session.get(SitePublication, job_id)).application_suspended
        assert await session.scalar(select(func.count(SiteAlert.id))) == 1


async def test_changed_requirement_evidence_invalidates_preview(catalogue):
    service, sessions, job_id = catalogue
    prepared = await preview(service, job_id)
    async with sessions.begin() as session:
        (await session.get(Job, job_id)).requirements = {
            "education": {"status": "required", "evidence": "A college degree is required."},
        }
    with pytest.raises(PublicationConflict):
        await service.confirm(prepared.token, actor="123")
