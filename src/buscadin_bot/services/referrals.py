"""Resolve commercial referral state without manufacturing URLs."""

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.db.models import (
    AuditEvent,
    Job,
    Notification,
    Referral,
    ReferralLink,
    ReferralProgram,
    utcnow,
)

LINK_VALIDATED = "LINK_VALIDADO"
WAITING_LINK = "AGUARDANDO_LINK"
NO_PROGRAM = "SEM_PROGRAMA"
PROGRAM_SCOPES = {"GLOBAL", "POR_VAGA", "POR_PROJETO"}


@dataclass(slots=True)
class ReferralResolution:
    status: str
    reason: str
    link: ReferralLink | None = None
    program: ReferralProgram | None = None


class ReferralResolver:
    """Apply program/link precedence and return an explainable resolution."""

    async def resolve_status(self, session: AsyncSession, job: Job) -> ReferralResolution:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(ReferralProgram)
            .where(ReferralProgram.company == job.company, ReferralProgram.is_active.is_(True))
            .order_by(ReferralProgram.id)
        )
        programs = [program for program in result.scalars().all() if self._program_current(program, now)]
        if not programs:
            return ReferralResolution(NO_PROGRAM, "NAO_IDENTIFICADO: nenhum programa ativo identificado")

        public_programs = [program for program in programs if program.public_sharing_allowed is True]
        uncertain_programs = [program for program in programs if program.public_sharing_allowed is None]
        if not public_programs:
            if uncertain_programs:
                return ReferralResolution(
                    WAITING_LINK,
                    "PROGRAMA_IDENTIFICADO: permissão de divulgação pública não confirmada",
                    program=uncertain_programs[0],
                )
            return ReferralResolution(NO_PROGRAM, "PROGRAMA_SEM_PERMISSAO_PUBLICA")

        result = await session.execute(
            select(ReferralLink).where(
                ReferralLink.program_id.in_([program.id for program in public_programs]),
                ReferralLink.is_active.is_(True),
            )
        )
        program_by_id = {program.id: program for program in public_programs}
        links = [
            link
            for link in result.scalars().all()
            if self._link_current(link, now, program_by_id[link.program_id])
        ]
        ranked = sorted(
            links,
            key=lambda link: self._link_rank(link, job, program_by_id[link.program_id]),
        )
        for link in ranked:
            program = program_by_id[link.program_id]
            if self._link_applies(link, program, job):
                return ReferralResolution(LINK_VALIDATED, self._validated_reason(link, program), link, program)

        if any(self._could_apply(program, job) for program in public_programs + uncertain_programs):
            reason = "PROGRAMA_IDENTIFICADO: link compatível ainda não cadastrado ou vigente"
            return ReferralResolution(WAITING_LINK, reason, program=(public_programs or uncertain_programs)[0])
        return ReferralResolution(NO_PROGRAM, "PROGRAMAS_INAPLICAVEIS_A_VAGA")

    async def apply_resolution(
        self,
        session: AsyncSession,
        job: Job,
        *,
        actor: str = "system",
    ) -> ReferralResolution:
        resolution = await self.resolve_status(session, job)
        previous_status = getattr(job, "referral_status", None) or NO_PROGRAM
        previous_link_id = getattr(job, "resolved_referral_link_id", None)
        job.referral_status = resolution.status
        job.referral_status_reason = resolution.reason
        job.resolved_referral_link_id = resolution.link.id if resolution.link else None

        if previous_status != resolution.status or previous_link_id != job.resolved_referral_link_id:
            session.add(
                AuditEvent(
                    job_id=job.id,
                    event_type="referral_resolution_changed",
                    before_json={"status": previous_status, "link_id": previous_link_id},
                    after_json={"status": resolution.status, "link_id": job.resolved_referral_link_id},
                    actor=actor,
                )
            )
            await self._requeue_state_change(session, job, resolution.status)
            if (
                getattr(job, "editorial_status", None) == "PRONTA"
                and previous_status == LINK_VALIDATED
                and resolution.status != LINK_VALIDATED
            ):
                job.editorial_status = "SELECIONADA"
                job.editorial_updated_at = utcnow()
                session.add(
                    AuditEvent(
                        job_id=job.id,
                        event_type="editorial_reopened_link_changed",
                        before_json={"editorial_status": "PRONTA"},
                        after_json={"editorial_status": "SELECIONADA"},
                        actor="system",
                    )
                )
        if getattr(job, "editorial_status", None) == "PRONTA" and job.status != "active":
            job.editorial_status = "SELECIONADA"
            job.editorial_updated_at = utcnow()
            session.add(
                AuditEvent(
                    job_id=job.id,
                    event_type="editorial_reopened_job_inactive",
                    before_json={"editorial_status": "PRONTA", "job_status": job.status},
                    after_json={"editorial_status": "SELECIONADA"},
                    actor="system",
                )
            )
        return resolution

    async def resolve(self, session: AsyncSession, job: Job) -> Referral | None:
        """Resolve the legacy referral table for backward compatibility."""

        result = await session.execute(
            select(Referral).where(
                Referral.company == job.company,
                Referral.enabled.is_(True),
                Referral.approved_for_public_sharing.is_(True),
                Referral.verified_at.is_not(None),
            )
        )
        candidates = [referral for referral in result.scalars().all() if self._legacy_valid(referral)]
        exact = [
            referral
            for referral in candidates
            if referral.scope == "job" and referral.source_job_id == job.source_job_id
        ]
        if exact:
            return exact[0]
        company = [
            referral
            for referral in candidates
            if referral.scope == "company" and referral.source_job_id is None
        ]
        return company[0] if company else None

    async def _requeue_state_change(self, session: AsyncSession, job: Job, status: str) -> None:
        result = await session.execute(select(Notification).where(Notification.job_id == job.id))
        notification = result.scalar_one_or_none()
        if notification is not None and notification.status in {"sent", "failed", "dead"}:
            if notification.last_notified_referral_status != status:
                notification.status = "pending"
                notification.attempts = 0
                notification.next_attempt_at = None
                notification.last_error = None

    @staticmethod
    def _program_current(program: ReferralProgram, now: datetime) -> bool:
        return _within_window(program.valid_from, program.valid_until, now)

    @staticmethod
    def _link_current(link: ReferralLink, now: datetime, program: ReferralProgram) -> bool:
        if not link.verified_at or not _valid_url(link.url, program.allowed_domains):
            return False
        return _within_window(None, link.expires_at, now)

    @staticmethod
    def _link_rank(link: ReferralLink, job: Job, program: ReferralProgram) -> tuple[int, int]:
        if link.job_id == job.id:
            return (0, link.id)
        if program.scope_type == "POR_PROJETO" and link.campaign_key == getattr(job, "referral_campaign_key", None):
            return (1, link.id)
        if program.scope_type == "GLOBAL":
            return (2, link.id)
        return (3, link.id)

    @staticmethod
    def _could_apply(program: ReferralProgram, job: Job) -> bool:
        if program.scope_type in {"GLOBAL", "POR_VAGA"}:
            return True
        return bool(program.campaign_key and program.campaign_key == getattr(job, "referral_campaign_key", None))

    @staticmethod
    def _link_applies(link: ReferralLink, program: ReferralProgram, job: Job) -> bool:
        if link.job_id is not None:
            return link.job_id == job.id
        if program.scope_type == "GLOBAL":
            return link.campaign_key is None
        if program.scope_type == "POR_PROJETO":
            return bool(
                link.campaign_key
                and link.campaign_key == program.campaign_key
                and link.campaign_key == getattr(job, "referral_campaign_key", None)
            )
        return False

    @staticmethod
    def _validated_reason(link: ReferralLink, program: ReferralProgram) -> str:
        scope = "vaga" if link.job_id is not None else program.scope_type
        return f"LINK_VALIDADO: link {scope} verificado e autorizado para divulgação pública"

    @staticmethod
    def _legacy_valid(referral: Referral) -> bool:
        return _valid_url(referral.referral_url) and _within_window(
            None, referral.expires_at, datetime.now(timezone.utc)
        )


def _valid_url(value: str, allowed_domains: list[str] | None = None) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    domains = [domain.lower().lstrip(".") for domain in (allowed_domains or []) if domain]
    return not domains or any(
        parsed.hostname.lower() == domain or parsed.hostname.lower().endswith(f".{domain}")
        for domain in domains
    )


def _within_window(start: datetime | None, end: datetime | None, now: datetime) -> bool:
    if start is not None and _as_utc(start) > now:
        return False
    if end is not None and _as_utc(end) <= now:
        return False
    return True


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
