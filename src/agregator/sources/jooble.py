from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ..models import JobPosting
from .base import SourceBatch

JOOBLE_POLAND_API_BASE = "https://pl.jooble.org/api"


class JoobleApiSource:
    name = "jooble"

    def __init__(
        self,
        api_key: str,
        *,
        keywords: str,
        location: str,
        api_base: str = JOOBLE_POLAND_API_BASE,
        result_on_page: int = 20,
        radius: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Jooble API key cannot be empty")
        if not keywords.strip():
            raise ValueError("Jooble keywords cannot be empty")
        if not location.strip():
            raise ValueError("Jooble location cannot be empty")

        self.api_key = api_key.strip()
        self.keywords = keywords.strip()
        self.location = location.strip()
        self.api_base = api_base.rstrip("/")
        self.result_on_page = max(1, min(result_on_page, 100))
        self.radius = radius
        self._client = client

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_cursor(cursor)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

        payload: dict[str, object] = {
            "keywords": self.keywords,
            "location": self.location,
            "page": page,
            "ResultOnPage": self.result_on_page,
            "companysearch": False,
        }
        if self.radius is not None:
            payload["radius"] = self.radius

        try:
            response = await client.post(
                f"{self.api_base}/{self.api_key}",
                json=payload,
            )
            response.raise_for_status()
            raw_payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(raw_payload, Mapping):
            return SourceBatch(jobs=[], next_cursor=None)

        jobs = parse_jooble_payload(raw_payload)
        next_cursor = _next_cursor(
            raw_payload,
            page,
            self.result_on_page,
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
            raise ValueError(f"invalid Jooble cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("Jooble cursor must be a page number >= 1")
        return page


def parse_jooble_payload(payload: Mapping[str, Any]) -> list[JobPosting]:
    raw_jobs = payload.get("jobs")
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
    url = _string(raw.get("link"))
    company_name = _string(raw.get("company"))
    if not source_id or not title or not url or not company_name:
        return None

    return JobPosting(
        source="jooble",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="api.company",
        company_name_confidence=0.97,
        city=_string(raw.get("location")),
        description=_string(raw.get("snippet")),
        refreshed_at=_string(raw.get("updated")),
    )


def _next_cursor(
    payload: Mapping[str, Any],
    page: int,
    result_on_page: int,
    returned: int,
) -> str | None:
    total = payload.get("totalCount")
    if isinstance(total, int) and page * result_on_page >= total:
        return None
    if returned == 0 or returned < result_on_page:
        return None
    return str(page + 1)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
