"""Administrative CLI for explicitly supplied referral URLs."""

import argparse
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select

from buscadin_bot.config import get_settings
from buscadin_bot.db.models import Job, Referral, ReferralLink, ReferralProgram, utcnow
from buscadin_bot.db.session import close_engine, create_engine, create_session_factory, init_db
from buscadin_bot.services.referrals import ReferralResolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buscadin", description="Buscadin Jobs Bot administration")
    parser.add_argument("--version", action="version", version="0.1.0")
    commands = parser.add_subparsers(dest="command")
    referral = commands.add_parser("referral", help="manage administrator-provided referral URLs")
    referral_commands = referral.add_subparsers(dest="referral_command", required=True)
    add = referral_commands.add_parser("add", help="store an official referral URL exactly as supplied")
    add.add_argument("--company", required=True)
    add.add_argument("--url", required=True, dest="referral_url")
    add.add_argument("--scope", choices=["job", "company", "campaign"], default="company")
    add.add_argument("--source-job-id")
    add.add_argument("--expires-at", type=_parse_datetime)
    add.add_argument("--notes")
    add.add_argument(
        "--approved-for-public-sharing",
        action="store_true",
        help="confirm that the official program permits public sharing",
    )
    referral_commands.add_parser("list", help="list stored referrals without printing secrets")
    program = commands.add_parser("program", help="manage referral programs")
    program_commands = program.add_subparsers(dest="program_command", required=True)
    program_add = program_commands.add_parser("add")
    program_add.add_argument("--company", required=True)
    program_add.add_argument("--name", required=True)
    program_add.add_argument("--scope", choices=["GLOBAL", "POR_VAGA", "POR_PROJETO"], required=True)
    program_add.add_argument("--campaign-key")
    program_add.add_argument(
        "--allowed-domain",
        action="append",
        dest="allowed_domains",
        help="restrict valid referral URLs to this domain; repeat for more domains",
    )
    public = program_add.add_mutually_exclusive_group()
    public.add_argument("--public-sharing-allowed", action="store_true")
    public.add_argument("--public-sharing-disallowed", action="store_true")
    program_add.add_argument("--evidence-url")
    program_add.add_argument("--rules-notes")
    program_add.add_argument("--valid-from", type=_parse_datetime)
    program_add.add_argument("--valid-until", type=_parse_datetime)
    program_commands.add_parser("list")
    link = commands.add_parser("link", help="manage validated referral links")
    link_commands = link.add_subparsers(dest="link_command", required=True)
    link_add = link_commands.add_parser("add")
    link_add.add_argument("--program-id", required=True, type=int)
    link_add.add_argument("--url", required=True, dest="link_url")
    link_add.add_argument("--job-id", type=int)
    link_add.add_argument("--campaign-key")
    link_add.add_argument("--source", choices=["MANUAL", "OFICIAL_API"], default="MANUAL")
    link_add.add_argument("--expires-at", type=_parse_datetime)
    link_add.add_argument("--verified-by", required=True)
    link_add.add_argument("--notes")
    link_commands.add_parser("list")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "referral" and args.referral_command == "add":
        asyncio.run(_add_referral(args))
    elif args.command == "referral" and args.referral_command == "list":
        asyncio.run(_list_referrals())
    elif args.command == "program" and args.program_command == "add":
        asyncio.run(_add_program(args))
    elif args.command == "program" and args.program_command == "list":
        asyncio.run(_list_programs())
    elif args.command == "link" and args.link_command == "add":
        asyncio.run(_add_link(args))
    elif args.command == "link" and args.link_command == "list":
        asyncio.run(_list_links())


async def _add_referral(args: argparse.Namespace) -> None:
    parsed = urlparse(args.referral_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("--url must be an absolute http(s) URL")
    if args.scope == "job" and not args.source_job_id:
        raise SystemExit("--source-job-id is required for --scope job")
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            session.add(
                Referral(
                    company=args.company,
                    source_job_id=args.source_job_id,
                    referral_url=args.referral_url,
                    scope=args.scope,
                    approved_for_public_sharing=args.approved_for_public_sharing,
                    verified_at=datetime.now(timezone.utc),
                    expires_at=args.expires_at,
                    notes=args.notes,
                )
            )
            await session.commit()
    finally:
        await close_engine(engine)
    print("Referral armazenado; a URL não foi alterada.")


async def _list_referrals() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            result = await session.execute(select(Referral).order_by(Referral.company, Referral.id))
            for referral in result.scalars().all():
                print(
                    f"{referral.id}\t{referral.company}\t{referral.scope}\t"
                    f"enabled={referral.enabled}\tapproved={referral.approved_for_public_sharing}\t"
                    f"url={referral.referral_url}"
                )
    finally:
        await close_engine(engine)


async def _add_program(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    public: bool | None
    if args.public_sharing_allowed:
        public = True
    elif args.public_sharing_disallowed:
        public = False
    else:
        public = None
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            session.add(
                ReferralProgram(
                    company=args.company,
                    name=args.name,
                    scope_type=args.scope,
                    campaign_key=args.campaign_key,
                    allowed_domains=args.allowed_domains or [],
                    public_sharing_allowed=public,
                    evidence_url=args.evidence_url,
                    rules_notes=args.rules_notes,
                    valid_from=args.valid_from,
                    valid_until=args.valid_until,
                )
            )
            await session.commit()
    finally:
        await close_engine(engine)
    print("Programa armazenado; a permissão pública deve ter evidência explícita.")


async def _list_programs() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            result = await session.execute(select(ReferralProgram).order_by(ReferralProgram.company, ReferralProgram.id))
            for program in result.scalars().all():
                print(
                    f"{program.id}\t{program.company}\t{program.name}\t{program.scope_type}\t"
                    f"active={program.is_active}\tpublic={program.public_sharing_allowed}"
                )
    finally:
        await close_engine(engine)


async def _add_link(args: argparse.Namespace) -> None:
    parsed = urlparse(args.link_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("--url must be an absolute http(s) URL")
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            program = await session.scalar(select(ReferralProgram).where(ReferralProgram.id == args.program_id))
            if program is None:
                raise SystemExit("program not found")
            job = await session.scalar(select(Job).where(Job.id == args.job_id)) if args.job_id else None
            if args.job_id and job is None:
                raise SystemExit("job not found")
            link = ReferralLink(
                program_id=program.id,
                job_id=args.job_id,
                campaign_key=args.campaign_key,
                url=args.link_url,
                source=args.source,
                verified_at=utcnow(),
                expires_at=args.expires_at,
                is_active=True,
                verified_by=args.verified_by,
                notes=args.notes,
            )
            session.add(link)
            await session.flush()
            if job is not None:
                await ReferralResolver().apply_resolution(session, job, actor=args.verified_by)
            await session.commit()
    finally:
        await close_engine(engine)
    print("Link armazenado sem alterar a URL fornecida.")


async def _list_links() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    await init_db(engine)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            result = await session.execute(
                select(ReferralLink, ReferralProgram)
                .join(ReferralProgram, ReferralLink.program_id == ReferralProgram.id)
                .order_by(ReferralProgram.company, ReferralLink.id)
            )
            for link, program in result.all():
                print(
                    f"{link.id}\tprogram={program.id}\t{program.company}\tjob={link.job_id}\t"
                    f"active={link.is_active}\texpires={link.expires_at}\turl={link.url}"
                )
    finally:
        await close_engine(engine)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("use ISO-8601, e.g. 2026-12-31T23:59:59Z") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    main()
