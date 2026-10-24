#!/usr/bin/env python3
"""Copy the legacy bot domain into a prepared catalogue database.

The destination schema must already be migrated with Alembic. This command
preserves stable IDs, is safe to rerun, and intentionally does not copy site
publication snapshots or confirmation tokens.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from buscadin_bot.db.models import (
    AuditEvent, Base, BotState, EditorialPublication, Job, Notification,
    Referral, ReferralLink, ReferralProgram,
)


LEGACY_MODELS = (
    ReferralProgram, Referral, Job, ReferralLink,
    EditorialPublication, AuditEvent, Notification, BotState,
)


def _columns(instance: Any) -> dict[str, Any]:
    mapper = inspect(instance).mapper
    return {attribute.key: getattr(instance, attribute.key) for attribute in mapper.column_attrs}


async def migrate(source_url: str, destination_url: str, *, dry_run: bool = False) -> Counter[str]:
    source_engine = create_async_engine(source_url, pool_pre_ping=True)
    destination_engine = create_async_engine(destination_url, pool_pre_ping=True)
    source_sessions = async_sessionmaker(source_engine, expire_on_commit=False, autoflush=False)
    destination_sessions = async_sessionmaker(destination_engine, expire_on_commit=False, autoflush=False)
    counts: Counter[str] = Counter()
    pending_referral_ids: dict[int, int | None] = {}
    try:
        async with source_sessions() as source, destination_sessions() as destination:
            transaction = await destination.begin()
            try:
                for model in LEGACY_MODELS:
                    rows = list((await source.scalars(select(model).order_by(*model.__table__.primary_key.columns))).all())
                    for row in rows:
                        values = _columns(row)
                        if model is Job:
                            pending_referral_ids[row.id] = values.get("resolved_referral_link_id")
                            values["resolved_referral_link_id"] = None
                        identity = tuple(values[column.name] for column in model.__table__.primary_key.columns)
                        existing = await destination.get(model, identity[0] if len(identity) == 1 else identity)
                        if existing is None:
                            destination.add(model(**values))
                            counts[f"{model.__tablename__}:inserted"] += 1
                        else:
                            for key, value in values.items():
                                setattr(existing, key, value)
                            counts[f"{model.__tablename__}:updated"] += 1
                await destination.flush()
                for job_id, referral_id in pending_referral_ids.items():
                    if referral_id is not None:
                        job = await destination.get(Job, job_id)
                        if job is not None and await destination.get(ReferralLink, referral_id) is not None:
                            job.resolved_referral_link_id = referral_id
                if dry_run:
                    await transaction.rollback()
                else:
                    await transaction.commit()
            except Exception:
                await transaction.rollback()
                raise
    finally:
        await source_engine.dispose()
        await destination_engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra o domínio legado para o banco do catálogo")
    parser.add_argument("--source-url", required=True, help="DATABASE_URL de origem")
    parser.add_argument("--destination-url", required=True, help="DATABASE_URL já migrado")
    parser.add_argument("--dry-run", action="store_true", help="valida e conta sem gravar")
    args = parser.parse_args()
    counts = asyncio.run(migrate(args.source_url, args.destination_url, dry_run=args.dry_run))
    for key in sorted(counts):
        print(f"{key}\t{counts[key]}")


if __name__ == "__main__":
    main()
