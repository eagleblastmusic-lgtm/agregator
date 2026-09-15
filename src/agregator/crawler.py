from __future__ import annotations

import asyncio
from dataclasses import dataclass
from heapq import heappop, heappush
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from .signals import contains_discovery_signal, normalize_text
from .url_utils import canonicalize_http_url

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
        sitemap_max_urls: int = 80,
        sitemap_max_children: int = 3,
    ) -> None:
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.timeout = timeout
        self.sitemap_max_urls = max(0, sitemap_max_urls)
        self.sitemap_max_children = max(0, sitemap_max_children)
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
            absolute = canonicalize_http_url(href, base_url=page_url)
            if absolute is None:
                continue
            if not self._same_site(base_url, absolute):
                continue
            label = " ".join(anchor.stripped_strings)
            priority = self._priority(absolute, label)
            links[absolute] = min(priority, links.get(absolute, priority))
        return sorted((priority, url) for url, priority in links.items())

    @staticmethod
    def _parse_sitemap_locations(xml_text: str) -> list[str]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return []

        locations: list[str] = []
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].lower() != "loc":
                continue
            value = (element.text or "").strip()
            if value:
                locations.append(value)
        return locations

    async def _sitemap_page_urls(
        self,
        client: httpx.AsyncClient,
        start_url: str,
        robots: RobotFileParser,
    ) -> list[str]:
        if self.sitemap_max_urls <= 0:
            return []

        parsed = urlparse(start_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        root_sitemap = f"{origin}/sitemap.xml"
        if not robots.can_fetch(self.user_agent, root_sitemap):
            return []

        locations = await self._fetch_sitemap_locations(client, root_sitemap)
        if not locations:
            return []

        pages: list[str] = []
        child_sitemaps: list[str] = []
        for raw_location in locations:
            location = canonicalize_http_url(raw_location)
            if location is None or not self._same_site(start_url, location):
                continue
            lower_path = urlparse(location).path.lower()
            if lower_path.endswith((".xml", ".xml.gz")):
                child_sitemaps.append(location)
            else:
                pages.append(location)

        for sitemap_url in child_sitemaps[: self.sitemap_max_children]:
            if len(pages) >= self.sitemap_max_urls:
                break
            if not robots.can_fetch(self.user_agent, sitemap_url):
                continue
            child_locations = await self._fetch_sitemap_locations(client, sitemap_url)
            for raw_location in child_locations:
                if len(pages) >= self.sitemap_max_urls:
                    break
                location = canonicalize_http_url(raw_location)
                if location is None or not self._same_site(start_url, location):
                    continue
                lower_path = urlparse(location).path.lower()
                if lower_path.endswith((".xml", ".xml.gz")):
                    continue
                pages.append(location)

        deduplicated: list[str] = []
        seen: set[str] = set()
        for value in pages:
            if value in seen:
                continue
            seen.add(value)
            deduplicated.append(value)
            if len(deduplicated) >= self.sitemap_max_urls:
                break
        return deduplicated

    async def _fetch_sitemap_locations(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> list[str]:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return []
        if response.status_code >= 400:
            return []
        await asyncio.sleep(self.request_delay)
        return self._parse_sitemap_locations(response.text)

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        if not urlparse(start_url).scheme:
            start_url = f"https://{start_url}"
        canonical_start = canonicalize_http_url(start_url)
        if canonical_start is None:
            return []
        start_url = canonical_start

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
            start_robots = await self._robots_for(client, start_url)
            sitemap_urls = await self._sitemap_page_urls(client, start_url, start_robots)
            for link in sitemap_urls:
                if link in queued:
                    continue
                sequence += 1
                queued.add(link)
                heappush(queue, (self._priority(link), sequence, link))

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

                raw_final_url = str(response.url)
                final_url = canonicalize_http_url(raw_final_url) or raw_final_url
                pages.append(
                    CrawlPage(
                        url=final_url,
                        html=response.text,
                        status_code=response.status_code,
                    )
                )

                for priority, link in self._links(response.text, raw_final_url, start_url):
                    if link in visited or link in queued:
                        continue
                    sequence += 1
                    queued.add(link)
                    heappush(queue, (priority, sequence, link))

                delay = robots.crawl_delay(self.user_agent)
                await asyncio.sleep(max(self.request_delay, float(delay or 0)))

        return pages
