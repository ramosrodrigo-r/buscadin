"""Bounded, untrusted data exchanged with the private browser service."""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from buscadin_bot.sources.base import RawJob
from buscadin_bot.sources.company_crawler import SOURCES, job_identity

SourceName = Literal['micro1', 'turing', 'mercor', 'alignerr']
ShortText = Annotated[str, Field(max_length=255)]


class CrawlRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: SourceName
    known_ids: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(default_factory=list, max_length=3000)
    max_new: int = Field(default=30, ge=1, le=30)
    max_pages: int = Field(default=5, ge=1, le=5)


class CrawlJob(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    source: SourceName
    source_job_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=80, max_length=50000)
    source_url: str = Field(max_length=2048)
    application_url: str = Field(max_length=2048)
    location_restrictions: list[ShortText] = Field(default_factory=list, max_length=100)
    timezone_restrictions: list[ShortText] = Field(default_factory=list, max_length=100)
    categories: list[ShortText] = Field(default_factory=list, max_length=100)
    employment_type: ShortText | None = None
    min_salary: float | None = Field(default=None, ge=0)
    max_salary: float | None = Field(default=None, ge=0)
    currency: ShortText | None = None
    salary_period: ShortText | None = None
    posted_at: datetime | None = None
    language_requirements: list[ShortText] = Field(default_factory=list, max_length=100)
    requirements: dict[str, Any] = Field(default_factory=dict, max_length=10)
    raw: dict[str, Any] = Field(default_factory=dict, max_length=10)

    @model_validator(mode='after')
    def validate_identity(self):
        for url in (self.source_url, self.application_url):
            identity = job_identity(self.source, url)
            if not identity or identity[0] != self.source_job_id or identity[1] != url:
                raise ValueError('Job URL and identity differ')
        if self.company != SOURCES[self.source][0]:
            raise ValueError('Unexpected company')
        return self

    def raw_job(self):
        return RawJob(**self.model_dump())


class CrawlReportData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: SourceName
    discovered: int = Field(ge=0, le=10000)
    skipped: int = Field(ge=0, le=10000)
    pages: int = Field(ge=0, le=5)
    failed: int = Field(ge=0, le=1000)
    limited: bool
    errors: list[Annotated[str, Field(max_length=200)]] = Field(max_length=100)


class CrawlResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    jobs: list[CrawlJob] = Field(max_length=30)
    report: CrawlReportData

    @model_validator(mode='after')
    def validate_source(self):
        if any(job.source != self.report.source for job in self.jobs):
            raise ValueError('Mixed sources')
        return self
