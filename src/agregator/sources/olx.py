from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ..models import JobPosting
from .base import SourceBatch

OLX_OFFERS_ENDPOINT = "https://www.olx.pl/api/v1/offers/"
OLX_JOBS_CATEGORY_ID = 4


class OlxPublicSource:
    name = "olx"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        endpoint: str = OLX_OFFERS_ENDPOINT,
        limit: int = 40,
        category_id: int = OLX_JOBS_CATEGORY_ID,
    ) -> None:
        self._client = client
        self.endpoint = endpoint
        self.limit = max(1, min(limit, 100))
        self.category_id = category_id

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        offset = self._parse_cursor(cursor)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

        try:
            response = await client.get(
                self.endpoint,
                params={
                    "limit": self.limit,
                    "offset": offset,
                    "category_id": self.category_id,
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        jobs = parse_olx_payload(payload)
        next_cursor = _next_cursor(payload, offset, self.limit, len(jobs))
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None or cursor == "":
            return 0
        try:
            value = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid OLX cursor: {cursor}") from exc
        if value < 0:
            raise ValueError("OLX cursor cannot be negative")
        return value


def parse_olx_payload(payload: Mapping[str, Any]) -> list[JobPosting]:
    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        return []

    jobs: list[JobPosting] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        job = _parse_offer(raw)
        if job is not None:
            jobs.append(job)
    return jobs


def _parse_offer(raw: Mapping[str, Any]) -> JobPosting | None:
    source_id = _string(raw.get("id"))
    title = _string(raw.get("title"))
    url = _string(raw.get("url"))
    if not source_id or not title or not url:
        return None

    company_name, company_source, company_confidence = _company_name(raw)
    if not company_name:
        return None

    location = raw.get("location")
    city = None
    if isinstance(location, Mapping):
        raw_city = location.get("city")
        if isinstance(raw_city, Mapping):
            city = _string(raw_city.get("name"))

    return JobPosting(
        source="olx",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source=company_source,
        company_name_confidence=company_confidence,
        city=city,
        description=_string(raw.get("description")),
        published_at=_string(raw.get("created_time")),
        refreshed_at=_string(raw.get("last_refresh_time")),
    )


def _company_name(raw: Mapping[str, Any]) -> tuple[str | None, str | None, float]:
    candidates: list[tuple[str | None, str, float]] = []

    company = raw.get("company")
    if isinstance(company, Mapping):
        candidates.append((_string(company.get("name")), "company.name", 0.98))

    user = raw.get("user")
    if isinstance(user, Mapping):
        candidates.append((_string(user.get("company_name")), "user.company_name", 0.95))

    partner = raw.get("partner")
    if isinstance(partner, Mapping):
        candidates.append((_string(partner.get("name")), "partner.name", 0.90))

    if isinstance(user, Mapping):
        candidates.append((_string(user.get("name")), "user.name", 0.45))

    contact = raw.get("contact")
    if isinstance(contact, Mapping):
        candidates.append((_string(contact.get("name")), "contact.name", 0.30))

    for value, source, confidence in candidates:
        if value:
            return value, source, confidence
    return None, None, 0.0


def _next_cursor(
    payload: Mapping[str, Any],
    offset: int,
    limit: int,
    returned: int,
) -> str | None:
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        total = metadata.get("total_elements", metadata.get("total"))
        if isinstance(total, int) and offset + limit >= total:
            return None

    if returned == 0 or returned < limit:
        return None
    return str(offset + limit)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
