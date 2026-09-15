from __future__ import annotations

import asyncio
from dataclasses import dataclass
from heapq import heappop, heappush
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .signals import contains_discovery_signal, normalize_text

PRIORITY_PATH_HINTS = (
    "kontakt",
    "contact",
    "wspolpraca",
    "partner",
    "b2b",
    "dla-firm",
    "biznes",
    "dostawc",
    "franczy",
    "o-nas",
    "about",
)


@dataclass(slots=True)
class CrawlPage:
    url: str
    html: str
    status_code: int


class WebsiteCrawler:
    def __init__(
        self,
        *,
        user_agent: str = "FaroEmployerDiscovery/0.1",
        max_pages: int = 12,
        request_delay: float = 0.8,
        timeout: float = 12.0,
    ) -> None:
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.timeout = timeout
        self._robots: dict[str, RobotFileParser] = {}

    async def _robots_for(self, client: httpx.AsyncClient, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]

        rp = RobotFileParser()
        robots_url = f"{origin}/robots.txt"
        try:
            response = await client.get(robots_url)
            if response.status_code < 400:
                rp.set_url(robots_url)
                rp.parse(response.text.splitlines())
            else:
                rp.parse([])
        except httpx.HTTPError:
            rp.parse([])
        self._robots[origin] = rp
        return rp

    @staticmethod
    def _same_site(base_url: str, candidate_url: str) -> bool:
        base = urlparse(base_url).hostname or ""
        candidate = urlparse(candidate_url).hostname or ""
        return base.removeprefix("www.") == candidate.removeprefix("www.")

    @staticmethod
    def _priority(url: str, label: str = "") -> int:
        normalized = normalize_text(f"{url} {label}")
        if any(hint in normalized for hint in PRIORITY_PATH_HINTS):
            return 0
        if contains_discovery_signal(normalized):
            return 0
        return 10

    def _links(self, html: str, page_url: str, base_url: str) -> list[tuple[int, str]]:
        soup = BeautifulSoup(html, "html.parser")
        links: dict[str, int] = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urldefrag(urljoin(page_url, href))[0]
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if not self._same_site(base_url, absolute):
                continue
            label = " ".join(anchor.stripped_strings)
            priority = self._priority(absolute, label)
            links[absolute] = min(priority, links.get(absolute, priority))
        return sorted((priority, url) for url, priority in links.items())

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        if not urlparse(start_url).scheme:
            start_url = f"https://{start_url}"

        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        pages: list[CrawlPage] = []
        visited: set[str] = set()
        queued: set[str] = {start_url}
        queue: list[tuple[int, int, str]] = []
        sequence = 0
        heappush(queue, (0, sequence, start_url))

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            while queue and len(pages) < self.max_pages:
                _, _, url = heappop(queue)
                if url in visited:
                    continue
                visited.add(url)

                robots = await self._robots_for(client, url)
                if not robots.can_fetch(self.user_agent, url):
                    continue

                try:
                    response = await client.get(url)
                except httpx.HTTPError:
                    continue

                content_type = response.headers.get("content-type", "")
                if response.status_code >= 400 or "text/html" not in content_type:
                    continue

                final_url = str(response.url)
                pages.append(
                    CrawlPage(
                        url=final_url,
                        html=response.text,
                        status_code=response.status_code,
                    )
                )

                for priority, link in self._links(response.text, final_url, start_url):
                    if link in visited or link in queued:
                        continue
                    sequence += 1
                    queued.add(link)
                    heappush(queue, (priority, sequence, link))

                delay = robots.crawl_delay(self.user_agent)
                await asyncio.sleep(max(self.request_delay, float(delay or 0)))

        return pages
