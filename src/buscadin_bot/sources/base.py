"""Common contract and raw payload for job source connectors."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class RawJob:
    source: str
    source_job_id: str
    title: str
    company: str
    description: str
    source_url: str
    application_url: str
    location_restrictions: list[str] = field(default_factory=list)
    timezone_restrictions: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    employment_type: str | None = None
    min_salary: float | None = None
    max_salary: float | None = None
    currency: str | None = None
    salary_period: str | None = None
    posted_at: datetime | None = None
    language_requirements: list[str] = field(default_factory=list)
    requirements: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class JobSource(Protocol):
    """Interface implemented by every authorized connector."""

    name: str

    async def fetch_jobs(self) -> Sequence[RawJob]:
        """Fetch a bounded batch of jobs from the source."""
