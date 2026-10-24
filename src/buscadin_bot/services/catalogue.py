"""Read approved catalogue content with bounded, shareable query parameters."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from buscadin_bot.db.models import Job, SitePublication, utcnow
from buscadin_bot.services.referrals import _as_utc
from buscadin_bot.services.requirements import job_slug, normalize_search
from buscadin_bot.services.site_publications import SitePublicationService


class CatalogueFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(default="", max_length=120)
    category: str | None = Field(default=None, pattern=r"^[a-z_]{1,60}$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    eligibility: Literal["confirmed_br", "unknown"] | None = None
    education: Literal["required", "not_required", "unknown"] | None = None
    experience: Literal["required", "not_required", "unknown"] | None = None
    salary_available: bool = False
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="before")
    @classmethod
    def empty_selects_mean_no_filter(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            for name in ("category", "language", "country", "eligibility", "education", "experience"):
                if values.get(name) == "":
                    values[name] = None
        return values


@dataclass(frozen=True)
class CataloguePage:
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


PUBLIC_FIELDS = {
    "title", "company", "summary", "category", "employment_type", "remote_type",
    "eligible_countries", "eligibility_status", "language_requirements", "language_codes",
    "requirements", "salary_min", "salary_max", "currency", "salary_period", "salary_disclosed",
    "source", "source_url", "posted_at", "commercial_disclosure",
}


class PublicCatalogue:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], publications: SitePublicationService) -> None:
        self.sessions, self.publications = sessions, publications

    async def health(self) -> None:
        """Check database connectivity without reading catalogue content."""
        async with self.sessions() as session:
            await session.execute(text("SELECT 1"))

    @staticmethod
    def _visible():
        approved_eligibility = SitePublication.public_snapshot["eligibility_status"].as_string()
        return (
            SitePublication.status == "PUBLICADA",
            Job.status == "active",
            Job.eligibility_status.in_(["confirmed_br", "unknown"]),
            approved_eligibility.in_(["confirmed_br", "unknown"]),
            # Withdraw a previously confirmed claim if current evidence no
            # longer supports it, even before the reconciliation worker runs.
            or_(Job.eligibility_status == "confirmed_br", approved_eligibility == "unknown"),
        )

    async def search(self, filters: CatalogueFilters | None = None) -> CataloguePage:
        filters = filters or CatalogueFilters()
        snapshot = SitePublication.public_snapshot
        clauses = list(self._visible())
        for term in normalize_search(filters.q).split():
            clauses.append(SitePublication.search_text.contains(term, autoescape=True))
        if filters.category:
            clauses.append(snapshot["category"].as_string() == filters.category)
        if filters.eligibility:
            clauses.append(snapshot["eligibility_status"].as_string() == filters.eligibility)
        if filters.salary_available:
            clauses.extend([
                snapshot["salary_disclosed"].as_boolean().is_(True),
                or_(snapshot["salary_min"].as_float().is_not(None), snapshot["salary_max"].as_float().is_not(None)),
            ])
        for name in ("education", "experience"):
            value = getattr(filters, name)
            if value:
                # Old snapshots without requirements remain unknown, never waived.
                clauses.append(func.coalesce(snapshot["requirements"][name].as_string(), "unknown") == value)
        if filters.language:
            clauses.append(cast(snapshot["language_codes"], String).contains(f'"{filters.language}"', autoescape=True))
        if filters.country:
            clauses.append(cast(snapshot["eligible_countries"], String).contains(f'"{filters.country}"', autoescape=True))
        query = select(SitePublication).join(Job, Job.id == SitePublication.job_id).where(*clauses)
        async with self.sessions() as session:
            total = await session.scalar(select(func.count()).select_from(query.subquery()))
            rows = list((await session.scalars(query.order_by(
                SitePublication.published_at.desc(), SitePublication.job_id.desc(),
            ).offset((filters.page - 1) * filters.page_size).limit(filters.page_size))).all())
        return CataloguePage([self._public(row, detail=False) for row in rows], int(total or 0), filters.page, filters.page_size)

    async def detail(self, job_id: int) -> dict[str, Any] | None:
        # Do not expose whether an unapproved internal ID exists.
        async with self.sessions() as session:
            visible = await session.scalar(select(SitePublication.job_id).join(Job).where(
                SitePublication.job_id == job_id, *self._visible(),
            ))
        if visible is None:
            return None
        await self.publications.destination(job_id)
        async with self.sessions() as session:
            row = await session.scalar(select(SitePublication).join(Job).where(
                SitePublication.job_id == job_id, *self._visible(),
            ))
            return self._public(row, detail=True) if row is not None else None

    async def sitemap_batch(self, *, after_id: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        if after_id < 0 or not 1 <= limit <= 5000:
            raise ValueError("Limites de sitemap inválidos")
        async with self.sessions() as session:
            rows = list((await session.scalars(select(SitePublication).join(Job).where(
                SitePublication.job_id > after_id, *self._visible(),
            ).order_by(SitePublication.job_id).limit(limit))).all())
        return [{"id": row.job_id, "path": self._path(row), "updated_at": _iso(row.published_at)} for row in rows]

    @staticmethod
    def _path(row: SitePublication) -> str:
        slug = row.public_snapshot.get("slug") or job_slug(str(row.public_snapshot.get("title", "")))
        return f"/vagas/{slug}-{row.job_id}"

    @classmethod
    def _public(cls, row: SitePublication, *, detail: bool) -> dict[str, Any]:
        # Explicit projection: never serialize ORM objects or private snapshots.
        public = {key: value for key, value in row.public_snapshot.items() if key in PUBLIC_FIELDS}
        public["requirements"] = {name: (public.get("requirements") or {}).get(name, "unknown") for name in ("education", "experience")}
        public.update({
            "id": row.job_id, "path": cls._path(row), "updated_at": _iso(row.published_at),
            "application_available": not row.application_suspended and _not_expired(row.destination_snapshot),
        })
        if detail:
            # Host informs the user without exposing private query parameters.
            public["destination_host"] = urlsplit(row.destination_snapshot.get("url", "")).hostname
        else:
            public.pop("commercial_disclosure", None)
        return public


def _not_expired(destination: dict[str, Any]) -> bool:
    for name in ("expires_at", "program_valid_until"):
        value = destination.get(name)
        if value:
            try:
                if _as_utc(datetime.fromisoformat(value)) <= utcnow():
                    return False
            except (ValueError, TypeError):
                return False
    return True


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None
