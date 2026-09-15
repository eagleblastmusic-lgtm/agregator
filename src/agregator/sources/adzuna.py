from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ..models import JobPosting
from .base import SourceBatch

ADZUNA_API_BASE = "https://api.adzuna.com/v1/api/jobs"


class AdzunaApiSource:
    name = "adzuna"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        *,
        country: str = "pl",
        what: str | None = None,
        where: str | None = None,
        results_per_page: int = 20,
        api_base: str = ADZUNA_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not app_id.strip():
            raise ValueError("Adzuna app_id cannot be empty")
        if not app_key.strip():
            raise ValueError("Adzuna app_key cannot be empty")
        if not country.strip():
            raise ValueError("Adzuna country cannot be empty")

        self.app_id = app_id.strip()
        self.app_key = app_key.strip()
        self.country = country.strip().lower()
        self.what = what.strip() if what else None
        self.where = where.strip() if where else None
        self.results_per_page = max(1, min(results_per_page, 50))
        self.api_base = api_base.rstrip("/")
        self._client = client

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_cursor(cursor)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

        params: dict[str, object] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": self.results_per_page,
            "content-type": "application/json",
        }
        if self.what:
            params["what"] = self.what
        if self.where:
            params["where"] = self.where

        try:
            response = await client.get(
                f"{self.api_base}/{self.country}/search/{page}",
                params=params,
            )
            response.raise_for_status()
            raw_payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(raw_payload, Mapping):
            return SourceBatch(jobs=[], next_cursor=None)

        jobs = parse_adzuna_payload(raw_payload)
        next_cursor = _next_cursor(
            raw_payload,
            page,
            self.results_per_page,
            len(jobs),
        )
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None or cursor == "":
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid Adzuna cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("Adzuna cursor must be a page number >= 1")
        return page


def parse_adzuna_payload(payload: Mapping[str, Any]) -> list[JobPosting]:
    raw_jobs = payload.get("results")
    if not isinstance(raw_jobs, list):
        return []

    jobs: list[JobPosting] = []
    for raw in raw_jobs:
        if not isinstance(raw, Mapping):
            continue
        job = _parse_job(raw)
        if job is not None:
            jobs.append(job)
    return jobs


def _parse_job(raw: Mapping[str, Any]) -> JobPosting | None:
    source_id = _string(raw.get("id"))
    title = _string(raw.get("title"))
    url = _string(raw.get("redirect_url"))

    company = raw.get("company")
    company_name = None
    if isinstance(company, Mapping):
        company_name = _string(company.get("display_name"))

    if not source_id or not title or not url or not company_name:
        return None

    city = None
    location = raw.get("location")
    if isinstance(location, Mapping):
        city = _string(location.get("display_name"))

    return JobPosting(
        source="adzuna",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="api.company.display_name",
        company_name_confidence=0.97,
        city=city,
        description=_string(raw.get("description")),
        published_at=_string(raw.get("created")),
    )


def _next_cursor(
    payload: Mapping[str, Any],
    page: int,
    results_per_page: int,
    returned: int,
) -> str | None:
    count = payload.get("count")
    if isinstance(count, int) and page * results_per_page >= count:
        return None
    if returned == 0 or returned < results_per_page:
        return None
    return str(page + 1)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
