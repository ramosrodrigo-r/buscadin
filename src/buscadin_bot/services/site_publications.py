"""Transactional publication core, independent of web and Telegram transports.

Each command owns a dedicated session and returns only after commit. Callers
must authenticate the transport as well; actor checks here are defense in depth.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from buscadin_bot.db.models import (
    AuditEvent, Job, ReferralLink, ReferralProgram, SiteAlert, SitePreview,
    SitePublication, SitePublicationEvent, utcnow,
)
from buscadin_bot.services.publication_policy import (
    PublicationRejected, preview_fingerprint, require_publishable_job, validate_destination,
)
from buscadin_bot.services.referrals import LINK_VALIDATED, ReferralResolver, _as_utc
from buscadin_bot.services.requirements import JobRequirements, job_slug, language_codes, normalize_search


class PublicationConflict(PublicationRejected):
    """State changed after preview; require a new explicit approval."""


@dataclass(frozen=True)
class PublicationResult:
    job_id: int
    version: int
    status: str


class SitePublicationService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        admin_actor: str,
        official_domains: list[str],
    ) -> None:
        if not admin_actor.strip():
            raise ValueError("Administrador obrigatório")
        self.sessions = sessions
        self.admin_actor = admin_actor
        self.official_domains = tuple(official_domains)
        self.resolver = ReferralResolver()

    def _authorize(self, actor: str) -> None:
        if actor != self.admin_actor:
            raise PublicationRejected("Administrador não autorizado")

    async def preview(
        self, job_id: int, *, actor: str, destination_type: str, summary: str,
    ) -> SitePreview:
        self._authorize(actor)
        if not summary.strip() or len(summary) > 12000:
            raise PublicationRejected("Informe resumo editorial entre 1 e 12000 caracteres")
        async with self.sessions.begin() as session:
            job = await self._job(session, job_id)
            publication = await session.get(SitePublication, job_id, with_for_update=True)
            if publication is None:
                publication = SitePublication(job_id=job_id, version=0)
                session.add(publication)
                await session.flush()
            snapshot = await self._candidate(session, job, destination_type, summary)
            snapshot["version"] = publication.version
            preview = SitePreview(
                token=secrets.token_hex(12), job_id=job_id, actor=actor,
                expected_version=publication.version,
                fingerprint=preview_fingerprint(snapshot), snapshot=snapshot,
                expires_at=utcnow() + timedelta(minutes=15),
            )
            session.add(preview)
        return preview

    async def confirm(self, token: str, *, actor: str) -> PublicationResult:
        try:
            return await self._confirm_once(token, actor=actor)
        except PublicationConflict:
            # A concurrent delivery of the same confirmation may have committed
            # while this transaction was waiting for the version comparison.
            async with self.sessions() as session:
                event = await session.scalar(select(SitePublicationEvent).where(
                    SitePublicationEvent.event_key == f"publish:{token}",
                    SitePublicationEvent.actor == actor,
                ))
                if event is not None:
                    return PublicationResult(event.job_id, event.version, "PUBLICADA")
            raise

    async def _confirm_once(self, token: str, *, actor: str) -> PublicationResult:
        self._authorize(actor)
        async with self.sessions.begin() as session:
            preview = await session.get(SitePreview, token)
            if preview is None or preview.actor != actor:
                raise PublicationRejected("Prévia inexistente ou não autorizada")
            # Lock the stable job first, consistently with all other commands.
            job = await self._job(session, preview.job_id)
            existing = await session.scalar(select(SitePublicationEvent).where(
                SitePublicationEvent.event_key == f"publish:{token}"
            ))
            if existing is not None:
                return PublicationResult(existing.job_id, existing.version, "PUBLICADA")
            if _as_utc(preview.expires_at) <= utcnow():
                raise PublicationConflict("Prévia expirada; gere uma nova")
            publication = await session.get(SitePublication, job.id, with_for_update=True)
            if publication is None or publication.version != preview.expected_version:
                raise PublicationConflict("Publicação alterada; gere uma nova prévia")
            current = await self._candidate(
                session, job, preview.snapshot["destination"]["type"],
                preview.snapshot["public"]["summary"],
            )
            current["version"] = publication.version
            if preview_fingerprint(current) != preview.fingerprint:
                raise PublicationConflict("Conteúdo ou destino alterado; confirme uma nova prévia")
            version = publication.version + 1
            await self._cas(session, job.id, publication.version, {
                "status": "PUBLICADA", "version": version,
                "public_snapshot": current["public"],
                "search_text": normalize_search(" ".join(str(current["public"].get(key) or "") for key in ("title", "company", "summary"))),
                "destination_snapshot": current["destination"],
                "approved_by": actor, "published_at": utcnow(),
                "unpublished_at": None, "application_suspended": False,
            })
            session.add(SitePublicationEvent(
                event_key=f"publish:{token}", job_id=job.id, version=version,
                action="publish", actor=actor, snapshot=current,
            ))
        return PublicationResult(job.id, version, "PUBLICADA")

    async def unpublish(
        self, job_id: int, *, actor: str, expected_version: int, event_id: str, reason: str,
    ) -> PublicationResult:
        self._authorize(actor)
        if not reason.strip() or not event_id or len(event_id) > 80:
            raise PublicationRejected("Motivo e identificador da ação são obrigatórios")
        key = f"unpublish:{event_id}"
        async with self.sessions.begin() as session:
            await self._job(session, job_id)
            existing = await session.scalar(select(SitePublicationEvent).where(
                SitePublicationEvent.event_key == key
            ))
            if existing is not None:
                if existing.job_id != job_id or existing.actor != actor or existing.reason != reason:
                    raise PublicationConflict("Identificador já utilizado em outra decisão")
                return PublicationResult(job_id, existing.version, "DESPUBLICADA")
            publication = await session.get(SitePublication, job_id, with_for_update=True)
            if publication is None or publication.version != expected_version:
                raise PublicationConflict("Publicação alterada ou inexistente")
            version = publication.version + 1
            snapshot = {"public": publication.public_snapshot, "destination": publication.destination_snapshot}
            await self._cas(session, job_id, publication.version, {
                "status": "DESPUBLICADA", "version": version,
                "unpublished_at": utcnow(), "application_suspended": True,
            })
            session.add(SitePublicationEvent(
                event_key=key, job_id=job_id, version=version, action="unpublish",
                actor=actor, reason=reason, snapshot=snapshot,
            ))
        return PublicationResult(job_id, version, "DESPUBLICADA")

    async def status(self, job_id: int, *, actor: str | None = None) -> dict[str, Any]:
        """Return the private publication state for an authenticated transport."""
        if actor is not None:
            self._authorize(actor)
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise PublicationRejected("Vaga não encontrada")
            publication = await session.get(SitePublication, job_id)
            if publication is None:
                return {
                    "job_id": job_id, "version": 0, "status": "NAO_PUBLICADA",
                    "title": job.title, "application_suspended": False, "public_url": None,
                }
            return self._status_payload(publication, job.title)

    async def set_requirements(
        self, job_id: int, *, actor: str, requirements: JobRequirements,
    ) -> dict[str, Any]:
        """Store editorial requirement facts without rewriting an approved snapshot."""
        self._authorize(actor)
        async with self.sessions.begin() as session:
            job = await self._job(session, job_id)
            before = {"requirements": job.requirements or {}}
            job.requirements = requirements.model_dump()
            session.add(AuditEvent(
                job_id=job_id,
                event_type="requirements_updated",
                before_json=before,
                after_json={"requirements": job.requirements},
                actor=actor,
            ))
            return {"job_id": job_id, "title": job.title, "requirements": requirements.public_statuses()}

    async def listing(
        self, *, status: str, page: int = 1, page_size: int = 20, actor: str | None = None,
    ) -> list[dict[str, Any]]:
        """List publication states without exposing snapshots or destinations."""
        if actor is not None:
            self._authorize(actor)
        if status not in {"NAO_PUBLICADA", "PUBLICADA", "DESPUBLICADA"}:
            raise PublicationRejected("Status de publicação inválido")
        if not 1 <= page <= 10000 or not 1 <= page_size <= 20:
            raise PublicationRejected("Página inválida")
        async with self.sessions() as session:
            query = select(SitePublication, Job.title).join(Job).where(
                SitePublication.status == status,
            ).order_by(
                SitePublication.published_at.desc().nullslast(),
                SitePublication.unpublished_at.desc().nullslast(),
                SitePublication.job_id.desc(),
            )
            rows = (await session.execute(query.offset((page - 1) * page_size).limit(page_size))).all()
            return [self._status_payload(publication, title) for publication, title in rows]

    @staticmethod
    def _status_payload(publication: SitePublication, title: str) -> dict[str, Any]:
        snapshot = publication.public_snapshot or {}
        path = f"/vagas/{snapshot.get('slug')}-{publication.job_id}" if snapshot.get("slug") else None
        return {
            "job_id": publication.job_id,
            "version": publication.version,
            "status": publication.status,
            "title": title,
            "application_suspended": publication.application_suspended,
            "public_url": path if publication.status == "PUBLICADA" else None,
        }

    async def destination(self, job_id: int) -> str | None:
        """Revalidate the approved URL at click time; never resolve a replacement.

        Returning None means no redirect. Invalid destinations are suspended in
        the same transaction as their audit event and administrator alert.
        """
        async with self.sessions.begin() as session:
            job = await self._job(session, job_id)
            publication = await session.get(SitePublication, job_id, with_for_update=True)
            if publication is None or publication.status != "PUBLICADA":
                return None
            if job.status != "active" or job.eligibility_status not in {"confirmed_br", "unknown"}:
                await self._retire(session, publication, "Vaga inativa ou incompatível com residentes no Brasil")
                return None
            if publication.public_snapshot.get("eligibility_status") == "confirmed_br" and job.eligibility_status == "unknown":
                await self._retire(session, publication, "Confirmação de elegibilidade Brasil deixou de existir na fonte")
                return None
            if publication.application_suspended:
                return None
            try:
                require_publishable_job(status=job.status, eligibility=job.eligibility_status)
                destination = publication.destination_snapshot
                if destination["type"] == "REFERRAL":
                    link = await session.get(ReferralLink, destination["link_id"], with_for_update=True)
                    program = await session.get(ReferralProgram, destination["program_id"], with_for_update=True)
                    if not self._valid_referral(job, link, program):
                        raise PublicationRejected("Indicação deixou de ser válida")
                    if link.url != destination["url"]:
                        raise PublicationRejected("Destino alterado; nova aprovação necessária")
                    validate_destination(destination["url"], program.allowed_domains)
                elif destination["type"] == "OFFICIAL":
                    if job.application_url != destination["url"]:
                        raise PublicationRejected("Candidatura oficial alterada; revisão necessária")
                    validate_destination(destination["url"], self.official_domains)
                else:
                    raise PublicationRejected("Tipo de destino inválido")
            except (PublicationRejected, KeyError) as error:
                await self._suspend(session, publication, str(error))
                return None
            return destination["url"]

    async def reconcile(self, *, batch_size: int = 100) -> int:
        """Recheck published records in bounded batches without waiting for clicks.

        The runtime scheduler must call this regularly. Merely missing a job in
        a collection batch must never set its operational status to inactive.
        """
        if not 1 <= batch_size <= 500:
            raise ValueError("Lote deve ter entre 1 e 500 vagas")
        checked = 0
        after = 0
        while True:
            async with self.sessions() as session:
                ids = list((await session.scalars(select(SitePublication.job_id).where(
                    SitePublication.status == "PUBLICADA", SitePublication.job_id > after,
                ).order_by(SitePublication.job_id).limit(batch_size))).all())
            if not ids:
                return checked
            for job_id in ids:
                await self.destination(job_id)
                checked += 1
            after = ids[-1]

    async def _retire(self, session: AsyncSession, publication: SitePublication, reason: str) -> None:
        version = publication.version + 1
        key = f"retire:{publication.job_id}:{version}"
        await self._cas(session, publication.job_id, publication.version, {
            "status": "DESPUBLICADA", "application_suspended": True,
            "unpublished_at": utcnow(), "version": version,
        })
        session.add(SitePublicationEvent(
            event_key=key, job_id=publication.job_id, version=version, action="unpublish",
            actor="system", reason=reason,
            snapshot={"public": publication.public_snapshot, "destination": publication.destination_snapshot},
        ))
        session.add(SiteAlert(event_key=key, job_id=publication.job_id, message=f"Vaga {publication.job_id} retirada: {reason}"))

    async def _suspend(self, session: AsyncSession, publication: SitePublication, reason: str) -> None:
        version = publication.version + 1
        key = f"suspend:{publication.job_id}:{version}"
        await self._cas(session, publication.job_id, publication.version, {
            "application_suspended": True, "version": version,
        })
        session.add(SitePublicationEvent(
            event_key=key, job_id=publication.job_id, version=version, action="suspend",
            actor="system", reason=reason,
            snapshot={"public": publication.public_snapshot, "destination": publication.destination_snapshot},
        ))
        session.add(SiteAlert(
            event_key=key, job_id=publication.job_id,
            message=f"Candidatura da vaga {publication.job_id} suspensa: {reason}",
        ))

    async def _candidate(
        self, session: AsyncSession, job: Job, destination_type: str, summary: str,
    ) -> dict[str, Any]:
        require_publishable_job(status=job.status, eligibility=job.eligibility_status)
        if destination_type == "OFFICIAL":
            destination = {"type": "OFFICIAL", "url": validate_destination(job.application_url, self.official_domains)}
        elif destination_type == "REFERRAL":
            resolved = await self.resolver.resolve_status(session, job)
            if resolved.status != LINK_VALIDATED or resolved.link is None or resolved.program is None:
                raise PublicationRejected("Não há indicação válida para esta vaga")
            link = await session.get(ReferralLink, resolved.link.id, with_for_update=True, populate_existing=True)
            program = await session.get(ReferralProgram, resolved.program.id, with_for_update=True, populate_existing=True)
            if not self._valid_referral(job, link, program):
                raise PublicationRejected("Indicação deixou de ser válida")
            destination = {
                "type": "REFERRAL", "url": validate_destination(link.url, program.allowed_domains),
                "link_id": link.id, "program_id": program.id,
                "expires_at": _iso(link.expires_at), "verified_at": _iso(link.verified_at),
                "program_valid_from": _iso(program.valid_from),
                "program_valid_until": _iso(program.valid_until),
                "scope": program.scope_type, "campaign": link.campaign_key,
                "public_sharing_allowed": program.public_sharing_allowed,
                "allowed_domains": sorted(program.allowed_domains),
            }
        else:
            raise PublicationRejected("Escolha candidatura oficial ou indicação")
        requirements = JobRequirements.model_validate(job.requirements or {})
        previous = await session.get(SitePublication, job.id)
        slug = (previous.public_snapshot.get("slug") if previous else None) or job_slug(job.title)
        return {"public": {
            "id": job.id, "title": job.title, "company": job.company,
            "slug": slug,
            "summary": summary, "category": job.category,
            "employment_type": job.employment_type, "remote_type": job.remote_type,
            "eligible_countries": job.eligible_countries, "eligibility_status": job.eligibility_status,
            "language_requirements": job.language_requirements,
            "language_codes": language_codes(job.language_requirements),
            "requirements": requirements.public_statuses(),
            "salary_disclosed": job.salary_disclosed,
            "commercial_disclosure": "Este link pode gerar remuneração para o Buscadin." if destination_type == "REFERRAL" else None,
            "salary_min": job.salary_min if job.salary_disclosed else None,
            "salary_max": job.salary_max if job.salary_disclosed else None,
            "currency": job.currency if job.salary_disclosed else None,
            "salary_period": job.salary_period if job.salary_disclosed else None,
            "source": job.source, "source_url": job.source_url, "posted_at": _iso(job.posted_at),
        }, "destination": destination, "requirement_evidence": requirements.model_dump()}

    def _valid_referral(self, job: Job, link: ReferralLink | None, program: ReferralProgram | None) -> bool:
        now = utcnow()
        return bool(
            link and program and link.program_id == program.id
            and program.company == job.company and program.is_active
            and program.public_sharing_allowed is True and link.is_active
            and self.resolver._program_current(program, now)
            and self.resolver._link_current(link, now, program)
            and self.resolver._link_applies(link, program, job)
        )

    @staticmethod
    async def _job(session: AsyncSession, job_id: int) -> Job:
        job = await session.get(Job, job_id, with_for_update=True)
        if job is None:
            raise PublicationRejected("Vaga não encontrada")
        return job

    @staticmethod
    async def _cas(session: AsyncSession, job_id: int, version: int, values: dict[str, Any]) -> None:
        result = await session.execute(update(SitePublication).where(
            SitePublication.job_id == job_id, SitePublication.version == version,
        ).values(**values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise PublicationConflict("Outra decisão alterou a publicação")


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None
