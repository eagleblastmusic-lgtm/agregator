from __future__ import annotations

from typing import Protocol

import httpx

from .models import SearchCandidate


class SearchProvider(Protocol):
    async def search_company(
        self,
        company_name: str,
        city: str | None = None,
    ) -> list[SearchCandidate]: ...


class BraveSearchProvider:
    """Search-provider adapter. Requires a Brave Search API key.

    Keeping web search behind an interface lets us replace the provider without
    changing company resolution or crawling logic.
    """

    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, *, timeout: float = 12.0, count: int = 8) -> None:
        if not api_key:
            raise ValueError("Brave Search API key is required")
        self.api_key = api_key
        self.timeout = timeout
        self.count = count

    async def search_company(
        self,
        company_name: str,
        city: str | None = None,
    ) -> list[SearchCandidate]:
        query = f'"{company_name}"'
        if city:
            query += f" {city}"
        query += " firma kontakt"

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": self.count,
            "country": "PL",
            "search_lang": "pl",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.endpoint, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        results = payload.get("web", {}).get("results", [])
        return [
            SearchCandidate(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
            )
            for item in results
            if item.get("url")
        ]


class StaticSearchProvider:
    """Useful for tests and offline benchmarking."""

    def __init__(self, candidates: list[SearchCandidate]) -> None:
        self.candidates = candidates

    async def search_company(
        self,
        company_name: str,
        city: str | None = None,
    ) -> list[SearchCandidate]:
        return list(self.candidates)
