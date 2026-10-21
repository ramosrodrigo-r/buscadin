"""Himalayas public JSON API connector."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

import httpx

from buscadin_bot.config import Settings
from buscadin_bot.sources.base import RawJob

logger = logging.getLogger(__name__)
Sleep = Callable[[float], Awaitable[None]]


class SourceRequestError(RuntimeError):
    """Raised when a source cannot provide a valid response."""


class HimalayasSource:
    name = "himalayas"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        backoff_base_seconds: float = 0.5,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        self._owns_client = client is None
        self._sleep = sleep
        self._backoff_base_seconds = backoff_base_seconds

    async def __aenter__(self) -> "HimalayasSource":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_jobs(self) -> Sequence[RawJob]:
        params: dict[str, str | int] = {"limit": 20}
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.settings.himalayas_api_key:
            headers["Authorization"] = f"Bearer {self.settings.himalayas_api_key.get_secret_value()}"

        payload = await self._get_json(self.settings.himalayas_api_url, params=params, headers=headers)
        jobs = payload.get("jobs", [])
        if not isinstance(jobs, list):
            raise SourceRequestError("Himalayas response field 'jobs' is not a list")
        return [self._parse_job(item) for item in jobs if isinstance(item, dict)]

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        max_retries = max(0, self.settings.http_max_retries)
        for attempt in range(max_retries + 1):
            response = await self._client.get(url, params=params, headers=headers)
            if response.is_success:
                try:
                    payload = response.json()
                except ValueError as error:
                    raise SourceRequestError("Himalayas returned invalid JSON") from error
                if not isinstance(payload, dict):
                    raise SourceRequestError("Himalayas JSON payload must be an object")
                return payload

            retryable = response.status_code == 429 or 500 <= response.status_code <= 599
            if not retryable or attempt >= max_retries:
                raise SourceRequestError(
                    f"Himalayas request failed with HTTP {response.status_code}"
                )
            delay = self._retry_delay(response, attempt)
            logger.warning("Himalayas request retrying", extra={"attempt": attempt + 1, "delay": delay})
            await self._sleep(delay)
        raise AssertionError("retry loop must return or raise")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return min(30.0, self._backoff_base_seconds * (2**attempt))

    def _parse_job(self, item: dict[str, Any]) -> RawJob:
        guid = str(item.get("guid") or "").strip()
        if not guid:
            raise SourceRequestError("Himalayas job is missing guid")
        company_slug = str(item.get("companySlug") or "company").strip()
        title = str(item.get("title") or "Untitled role").strip()
        source_url = self._source_url(item, company_slug, title, guid)
        application_url = str(item.get("applicationLink") or source_url).strip()
        return RawJob(
            source=self.name,
            source_job_id=guid,
            title=title,
            company=str(item.get("companyName") or "Unknown company").strip(),
            description=str(item.get("description") or item.get("excerpt") or ""),
            source_url=source_url,
            application_url=application_url,
            location_restrictions=self._string_list(item.get("locationRestrictions")),
            timezone_restrictions=self._string_list(item.get("timezoneRestrictions")),
            categories=self._string_list(item.get("categories"))
            + self._string_list(item.get("parentCategories")),
            employment_type=self._optional_string(item.get("employmentType")),
            min_salary=self._number(item.get("minSalary")),
            max_salary=self._number(item.get("maxSalary")),
            currency=self._optional_string(item.get("currency")),
            salary_period=self._optional_string(item.get("salaryPeriod")),
            posted_at=self._parse_datetime(item.get("pubDate")),
            raw=item,
        )

    @staticmethod
    def _source_url(item: dict[str, Any], company_slug: str, title: str, guid: str) -> str:
        for key in ("url", "jobUrl"):
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.startswith("http"):
                return candidate
        if guid.startswith("http"):
            return guid
        if guid.startswith("/") or guid.startswith("companies/"):
            return f"https://himalayas.app/{guid.lstrip('/')}"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "job"
        return f"https://himalayas.app/companies/{company_slug}/jobs/{slug}"

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
