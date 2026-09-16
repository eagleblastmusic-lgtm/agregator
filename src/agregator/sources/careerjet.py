from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import httpx

from ..models import JobPosting
from .base import SourceBatch

CAREERJET_API_ENDPOINT = "https://search.api.careerjet.net/v4/query"


class CareerjetApiSource:
    """Careerjet Publisher API adapter.

    Careerjet requires a publisher API key, a Referer and the IP/User-Agent of the
    user whose action triggered the query. The adapter therefore does not invent
    these values; callers must provide them explicitly.
    """

    name = "careerjet"

    def __init__(
        self,
        api_key: str,
        *,
        referer: str,
        user_ip: str,
        user_agent: str,
        locale_code: str = "pl_PL",
        keywords: str | None = None,
        location: str | None = None,
        page_size: int = 20,
        sort: str = "date",
        endpoint: str = CAREERJET_API_ENDPOINT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Careerjet api_key cannot be empty")
        if not referer.strip():
            raise ValueError("Careerjet referer cannot be empty")
        if not user_ip.strip():
            raise ValueError("Careerjet user_ip cannot be empty")
        if not user_agent.strip():
            raise ValueError("Careerjet user_agent cannot be empty")
        if not locale_code.strip():
            raise ValueError("Careerjet locale_code cannot be empty")
        if sort not in {"relevance", "date", "salary"}:
            raise ValueError("Careerjet sort must be relevance, date or salary")

        self.api_key = api_key.strip()
        self.referer = referer.strip()
        self.user_ip = user_ip.strip()
        self.user_agent = user_agent.strip()
        self.locale_code = locale_code.strip()
        self.keywords = keywords.strip() if keywords else None
        self.location = location.strip() if location else None
        self.page_size = max(1, min(page_size, 100))
        self.sort = sort
        self.endpoint = endpoint
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
            "locale_code": self.locale_code,
            "page": page,
            "page_size": self.page_size,
            "sort": self.sort,
            "user_ip": self.user_ip,
            "user_agent": self.user_agent,
        }
        if self.keywords:
            params["keywords"] = self.keywords
        if self.location:
            params["location"] = self.location

        try:
            response = await client.get(
                self.endpoint,
                params=params,
                auth=(self.api_key, ""),
                headers={"Referer": self.referer},
            )
            response.raise_for_status()
            raw_payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(raw_payload, Mapping):
            return SourceBatch(jobs=[], next_cursor=None)

        jobs = parse_careerjet_payload(raw_payload)
        next_cursor = _next_cursor(raw_payload, page, len(jobs))
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None or cursor == "":
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid Careerjet cursor: {cursor}") from exc
        if page < 1 or page > 10:
            raise ValueError("Careerjet cursor must be a page number from 1 to 10")
        return page


def parse_careerjet_payload(payload: Mapping[str, Any]) -> list[JobPosting]:
    if _string(payload.get("type")) != "JOBS":
        return []

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
    title = _string(raw.get("title"))
    company_name = _string(raw.get("company"))
    url = _string(raw.get("url"))
    if not title or not company_name or not url:
        return None

    return JobPosting(
        source="careerjet",
        source_id=_stable_source_id(url),
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="api.company",
        company_name_confidence=0.96,
        city=_string(raw.get("locations")),
        description=_string(raw.get("description")),
        published_at=_string(raw.get("date")),
    )


def _next_cursor(
    payload: Mapping[str, Any],
    page: int,
    returned: int,
) -> str | None:
    if returned == 0 or page >= 10:
        return None

    pages = payload.get("pages")
    if isinstance(pages, int) and page >= pages:
        return None

    return str(page + 1)


def _stable_source_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
