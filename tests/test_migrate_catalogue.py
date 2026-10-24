import importlib.util
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Job, ReferralLink, ReferralProgram, SitePublication
from buscadin_bot.db.session import create_session_factory, init_db


def _migration_module():
    spec = importlib.util.spec_from_file_location("migrate_catalogue", "scripts/migrate_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_migration_preserves_ids_is_idempotent_and_skips_site_tables(tmp_path):
    source = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source.db'}")
    destination = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'destination.db'}")
    await init_db(source)
    await init_db(destination)
    source_sessions = create_session_factory(source)
    async with source_sessions.begin() as session:
        session.add(Job(
            id=42, source="test", source_job_id="42", title="Video annotator",
            company="Example", source_url="https://source.example/42",
            application_url="https://jobs.example/42", eligibility_status="unknown",
        ))
        program = ReferralProgram(
            id=7, company="Example", name="Program", scope_type="POR_VAGA",
            public_sharing_allowed=True, allowed_domains=["ref.example"],
        )
        session.add(program)
        await session.flush()
        session.add(ReferralLink(
            id=9, program_id=program.id, job_id=42, url="https://ref.example/42",
            source="MANUAL", verified_by="admin",
        ))
    module = _migration_module()
    source_url = f"sqlite+aiosqlite:///{tmp_path / 'source.db'}"
    destination_url = f"sqlite+aiosqlite:///{tmp_path / 'destination.db'}"
    first = await module.migrate(source_url, destination_url)
    second = await module.migrate(source_url, destination_url)
    assert first["jobs:inserted"] == 1
    assert second["jobs:updated"] == 1
    async with create_session_factory(destination)() as session:
        job = await session.get(Job, 42)
        assert job.title == "Video annotator"
        assert (await session.get(ReferralLink, 9)).job_id == 42
        assert await session.scalar(select(SitePublication)) is None
    await source.dispose()
    await destination.dispose()


@pytest.mark.asyncio
async def test_postgresql_import_advances_sequences(tmp_path):
    destination_url = os.environ.get("BUSCADIN_TEST_POSTGRES_URL")
    if not destination_url:
        pytest.skip("requires a fresh disposable PostgreSQL database")
    source_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_source.db'}"
    source = create_async_engine(source_url)
    destination = create_async_engine(destination_url)
    try:
        await init_db(source)
        await init_db(destination)
        async with create_session_factory(source).begin() as session:
            for job_id in (1, 42):
                session.add(Job(id=job_id, source="migration-test", source_job_id=str(job_id),
                                source_url="https://example.com/job", application_url="https://example.com/apply",
                                title="Synthetic job", company="Example"))
        module = _migration_module()
        await module.migrate(source_url, destination_url, dry_run=True)
        async with create_session_factory(destination)() as session:
            assert await session.get(Job, 1) is None
        await module.migrate(source_url, destination_url)
        await module.migrate(source_url, destination_url)
        async with create_session_factory(destination).begin() as session:
            job = Job(source="migration-test", source_job_id="new", title="New job", company="Example",
                      source_url="https://example.com/new", application_url="https://example.com/apply")
            session.add(job)
            await session.flush()
            assert job.id > 42
            assert (await session.get(Job, 1)).title == "Synthetic job"
    finally:
        await source.dispose()
        await destination.dispose()
