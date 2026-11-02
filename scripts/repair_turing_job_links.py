"""Repair saved Turing navigation hints without changing job identities or curation.

Defaults to a dry run. Pass --apply to persist changes and their audit events.
Uses DATABASE_URL or the admin service's mounted database_url secret.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from buscadin_bot.config import get_settings
from buscadin_bot.db.models import AuditEvent, Job, utcnow
from buscadin_bot.db.session import create_engine, create_session_factory
from buscadin_bot.sources.company_crawler import job_identity, turing_job_url


async def main(apply: bool):
    settings = get_settings()
    if not os.environ.get("DATABASE_URL"):
        secret = Path("/run/secrets/database_url")
        if not secret.is_file():
            raise SystemExit("Configure DATABASE_URL or run inside the admin service")
        settings.database_url = secret.read_text().strip()
    engine = create_engine(settings)
    count = 0
    try:
        async with create_session_factory(engine).begin() as session:
            query = select(Job).where(Job.source == "turing").order_by(Job.id)
            if apply:
                query = query.with_for_update()
            for job in (await session.scalars(query)).all():
                source = job_identity("turing", job.source_url)
                if not source or source[0] != job.source_job_id:
                    continue
                target = turing_job_url(job.source_job_id, job.title)
                before, after = {}, {}
                for field in ("source_url", "application_url"):
                    previous = getattr(job, field)
                    # Preserve operator-entered referral/campaign destinations.
                    if set(parse_qs(urlsplit(previous).query)) - {"jobId", "search"}:
                        continue
                    identity = job_identity("turing", previous)
                    if identity and identity[0] == job.source_job_id and previous != target:
                        before[field], after[field] = previous, target
                if not after:
                    continue
                count += 1
                if apply:
                    for field, value in after.items():
                        setattr(job, field, value)
                    job.updated_at = utcnow()
                    session.add(AuditEvent(job_id=job.id, event_type="repair_turing_job_links",
                                           actor="maintenance:turing-links",
                                           before_json=before, after_json=after))
        print(json.dumps({"apply": apply, "jobs": count}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
