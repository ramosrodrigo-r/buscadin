from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

import buscadin_bot.cli as cli
from buscadin_bot.config import Settings
from buscadin_bot.db.models import AuditEvent, Job
from buscadin_bot.db.session import create_session_factory, init_db


@pytest.mark.asyncio
async def test_cli_requirement_update_preserves_evidence_and_audits(tmp_path, monkeypatch, capsys):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'requirements.db'}"
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, database_url=database_url))
    engine = create_async_engine(database_url)
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions.begin() as session:
        session.add(Job(
            id=4, source="test", source_job_id="4", title="Video annotator",
            company="Example", source_url="https://source.example/4",
            application_url="https://jobs.example/4",
        ))
    await engine.dispose()

    await cli._set_requirements(SimpleNamespace(
        job_id=4, actor="admin", education_status="not_required",
        education_evidence="A fonte diz: não exige graduação.",
        experience_status="unknown", experience_evidence=None,
    ))
    captured = capsys.readouterr().out
    assert "nova publicação exige nova prévia" in captured
    engine = create_async_engine(database_url)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        job = await session.get(Job, 4)
        event = await session.scalar(select(AuditEvent))
        assert job.requirements["education"]["status"] == "not_required"
        assert event.event_type == "requirements_updated"
        assert event.actor == "admin"
    await engine.dispose()
