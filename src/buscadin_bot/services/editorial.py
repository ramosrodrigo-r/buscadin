"""Editorial queue state, audit events and copyable manual-post text."""

from datetime import datetime, timezone
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from buscadin_bot.db.models import AuditEvent, EditorialPublication, Job, utcnow
from buscadin_bot.services.referrals import LINK_VALIDATED, ReferralResolution

EDITORIAL_STATUSES = {"NOVA", "SELECIONADA", "PRONTA", "PUBLICADA", "DESCARTADA"}
PUBLICATION_CHANNELS = {"instagram", "tiktok", "kwai", "outro"}


async def set_editorial_status(
    session: AsyncSession,
    job: Job,
    status: str,
    *,
    actor: str,
    channel: str | None = None,
    post_url: str | None = None,
    notes: str | None = None,
) -> None:
    if status not in EDITORIAL_STATUSES:
        raise ValueError(f"status editorial inválido: {status}")
    current = getattr(job, "editorial_status", None) or "NOVA"
    if status == "PUBLICADA" and current not in {"PRONTA", "PUBLICADA"}:
        raise ValueError("uma vaga precisa estar PRONTA antes de ser marcada como PUBLICADA")
    if status in {"PRONTA", "PUBLICADA"} and job.status != "active":
        raise ValueError("vaga inativa não pode ser preparada ou publicada")
    if status == "PUBLICADA" and channel not in PUBLICATION_CHANNELS:
        raise ValueError("canal de publicação inválido")

    if current != status:
        job.editorial_status = status
        job.editorial_updated_at = utcnow()
        session.add(
            AuditEvent(
                job_id=job.id,
                event_type="editorial_status_changed",
                before_json={"editorial_status": current},
                after_json={"editorial_status": status},
                actor=actor,
            )
        )
    if status == "PUBLICADA" and current != "PUBLICADA":
        session.add(
            EditorialPublication(
                job_id=job.id,
                channel=channel or "outro",
                published_at=datetime.now(timezone.utc),
                post_url=post_url,
                notes=notes,
            )
        )


def prepare_editorial_text(job: Job, resolution: ReferralResolution | None = None) -> str:
    status = resolution.status if resolution else (getattr(job, "referral_status", None) or "SEM_PROGRAMA")
    reason = resolution.reason if resolution else (job.referral_status_reason or "revisão necessária")
    referral_url = resolution.link.url if resolution and resolution.link else None
    destination = referral_url if status == LINK_VALIDATED and referral_url else job.application_url
    destination_label = "link de indicação oficial" if status == LINK_VALIDATED and referral_url else "candidatura oficial — sem indicação validada"
    salary = _salary(job)
    lines = [
        f"{job.title} — {job.company}",
        f"Remoto/elegibilidade: {_eligibility(job)}",
        f"Remuneração: {salary}",
        f"Indicação: {status} — {reason}",
        f"{destination_label}: {destination}",
    ]
    if status == LINK_VALIDATED:
        lines.append(
            "Transparência: o Buscadin pode receber uma comissão se você se candidatar por este link e cumprir os critérios do programa."
        )
    lines.extend(["", "Fonte: " + job.source, "#vagas #trabalhoremoto"])
    return "\n".join(lines)


def _salary(job: Job) -> str:
    if not job.salary_disclosed or (job.salary_min is None and job.salary_max is None):
        return "não informada"
    currency = job.currency or ""
    period = f" / {job.salary_period}" if job.salary_period else ""
    if job.salary_min is not None and job.salary_max is not None:
        return f"{currency} {job.salary_min:g}–{job.salary_max:g}{period}".strip()
    value = job.salary_min if job.salary_min is not None else job.salary_max
    return f"{currency} {value:g}{period}".strip()


def _eligibility(job: Job) -> str:
    if job.eligibility_status == "confirmed_br":
        return "Brasil confirmado"
    if job.eligibility_status == "excluded_br":
        return "Brasil excluído"
    return "Brasil não confirmado"
