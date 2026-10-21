"""Convert source-specific payloads into the persisted job shape."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser

from buscadin_bot.sources.base import RawJob


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


@dataclass(slots=True)
class NormalizedJob:
    source: str
    source_job_id: str
    source_url: str
    application_url: str
    company: str
    title: str
    description: str
    category: str
    employment_type: str | None
    remote_type: str | None
    eligible_countries: list[str] = field(default_factory=list)
    eligibility_status: str = "unknown"
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    salary_period: str | None = None
    salary_disclosed: bool = False
    language_requirements: list[str] = field(default_factory=list)
    evidence: str | None = None
    posted_at: datetime | None = None


def normalize_raw_job(raw: RawJob, *, category: str, eligibility: tuple[str, list[str], str]) -> NormalizedJob:
    eligibility_status, countries, evidence = eligibility
    return NormalizedJob(
        source=raw.source.strip().lower(),
        source_job_id=raw.source_job_id.strip(),
        source_url=raw.source_url.strip(),
        application_url=raw.application_url.strip(),
        company=raw.company.strip(),
        title=raw.title.strip(),
        description=html_to_text(raw.description),
        category=category,
        employment_type=raw.employment_type.strip() if raw.employment_type else None,
        remote_type="remote",
        eligible_countries=countries,
        eligibility_status=eligibility_status,
        salary_min=raw.min_salary,
        salary_max=raw.max_salary,
        currency=raw.currency.upper() if raw.currency else None,
        salary_period=raw.salary_period,
        salary_disclosed=raw.min_salary is not None or raw.max_salary is not None,
        evidence=evidence,
        posted_at=raw.posted_at,
    )
