"""Safe HTML message and inline keyboard formatting."""

from html import escape

from buscadin_bot.db.models import Job, Referral


def format_job_message(
    job: Job,
    referral: Referral | None = None,
    *,
    referral_status: str | None = None,
    referral_reason: str | None = None,
    referral_url: str | None = None,
) -> str:
    salary = format_salary(job)
    eligibility = {
        "confirmed_br": "Brasil confirmado",
        "unknown": "Brasil não confirmado",
        "excluded_br": "Não elegível para Brasil",
    }.get(job.eligibility_status, job.eligibility_status)
    description = escape((job.description or "Não informado")[:600])
    commercial_status = referral_status or getattr(job, "referral_status", None)
    if commercial_status:
        referral_text = f"Indicação: <b>{escape(commercial_status)}</b>"
        if referral_reason:
            referral_text += f" — {escape(referral_reason)}"
        if commercial_status == "LINK_VALIDADO" and referral_url:
            referral_text += (
                f'\nDestino editorial: <a href="{escape(referral_url, quote=True)}">link oficial</a>'
                "\nTransparência: o Buscadin pode receber comissão conforme as regras do programa."
            )
        else:
            referral_text += f'\nCandidatura oficial: <a href="{escape(job.application_url, quote=True)}">abrir vaga</a>'
    else:
        referral_text = "Indicação: não configurada"
    if referral is not None and not commercial_status:
        referral_text = (
            f'Indicação: <a href="{escape(referral.referral_url, quote=True)}">link validado</a> '
            "(pode haver relação remunerada)"
        )
    return (
        f"<b>{escape(job.title)}</b> — {escape(job.company)}\n"
        f"Categoria: {escape(job.category)}\n"
        f"Elegibilidade: {escape(eligibility)}\n"
        f"Remuneração: {escape(salary)}\n"
        f"Fonte: {escape(job.source)}\n"
        f"Descrição: {description}\n\n"
        f"{referral_text}"
    )


def format_salary(job: Job) -> str:
    if not job.salary_disclosed or (job.salary_min is None and job.salary_max is None):
        return "Não informado"
    currency = escape(job.currency or "")
    period = f" / {escape(job.salary_period)}" if job.salary_period else ""
    if job.salary_min is not None and job.salary_max is not None:
        return f"{currency} {job.salary_min:g}–{job.salary_max:g}{period}".strip()
    value = job.salary_min if job.salary_min is not None else job.salary_max
    return f"{currency} {value:g}{period}".strip()


def job_keyboard(
    job: Job,
    *,
    editorial: bool = False,
    destination_url: str | None = None,
) -> dict[str, list[list[dict[str, str]]]]:
    if editorial:
        return {
            "inline_keyboard": [
                [
                    {"text": "Selecionar", "callback_data": f"select:{job.id}"},
                    {"text": "Preparar texto", "callback_data": f"prepare:{job.id}"},
                ],
                [
                    {"text": "Detalhes", "callback_data": f"detail:{job.id}"},
                    {"text": "Descartar", "callback_data": f"discard:{job.id}"},
                ],
                [{"text": "Abrir destino", "url": destination_url or job.application_url}],
            ]
        }
    return {
        "inline_keyboard": [
            [
                {"text": "Aprovar", "callback_data": f"approve:{job.id}"},
                {"text": "Descartar", "callback_data": f"discard:{job.id}"},
            ],
            [{"text": "Ver vaga", "url": job.application_url}],
        ]
    }
