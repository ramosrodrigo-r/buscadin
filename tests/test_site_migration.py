"""Exercise the real Alembic chain and restoration against isolated SQLite files."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Job
from buscadin_bot.db.session import create_session_factory
from buscadin_bot.services.site_publications import SitePublicationService


async def test_site_upgrade_preserves_legacy_jobs_and_backup_restores_publications(tmp_path):
    database = tmp_path / "migration.db"
    backup = tmp_path / "backup.db"
    url = f"sqlite+aiosqlite:///{database}"
    env = os.environ | {"DATABASE_URL": url}
    root = Path(__file__).resolve().parents[1]

    def alembic(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments], cwd=root,
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    alembic("upgrade", "0003_referral_domains")
    # Seed the historical schema without using today's ORM columns/defaults.
    with sqlite3.connect(database) as connection:
        connection.execute("""INSERT INTO jobs
            (id, source, source_job_id, title, company, source_url, application_url,
             description, category, eligible_countries, eligibility_status, salary_disclosed,
             language_requirements, first_seen_at, last_seen_at, last_checked_at, status,
             review_status, editorial_status)
            VALUES (77, 'legacy', 'preserve-me', 'Existing job', 'Example',
                    'https://jobs.example/77', 'https://jobs.example/77', '', 'other', '[]',
                    'unknown', 0, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    'active', 'pending', 'PUBLICADA')""")
    alembic("upgrade", "head")
    alembic("check")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM site_publications").fetchone()[0] == 0
        assert connection.execute("SELECT source_job_id FROM jobs WHERE id=77").fetchone()[0] == "preserve-me"

    engine = create_async_engine(url)
    sessions = create_session_factory(engine)
    service = SitePublicationService(sessions, admin_actor="123", official_domains=["jobs.example"])
    preview = await service.preview(77, actor="123", destination_type="OFFICIAL", summary="Resumo aprovado")
    await service.confirm(preview.token, actor="123")
    await engine.dispose()
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    alembic("downgrade", "0003_referral_domains")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM jobs WHERE id=77").fetchone()[0] == 1
    # Restore a copy, not the live source: all new history must survive rollback.
    restored = tmp_path / "restored.db"
    with sqlite3.connect(backup) as source, sqlite3.connect(restored) as target:
        source.backup(target)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT status FROM site_publications WHERE job_id=77").fetchone()[0] == "PUBLICADA"
        assert connection.execute("SELECT count(*) FROM site_publication_events").fetchone()[0] == 1
