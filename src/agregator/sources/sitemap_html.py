from __future__ import annotations

import asyncio
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlunparse

import httpx

from .base import SourceBatch
from .public_html import HtmlJobSourceConfig, parse_job_detail_html


@dataclass(frozen=True, slots=True)
class SitemapJobSourceConfig:
    detail: HtmlJobSourceConfig
    sitemap_url: str
    chunk_size: int = 25


class SitemapHtmlJobSource:
    """Walk a public sitemap and fetch job detail pages in resumable chunks."""

    def __init__(
        self,
        config: SitemapJobSourceConfig,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
    ) -> None:
        self.config = config
        self.name = config.detail.name
        self._client = client
        self.user_agent = user_agent
        self.request_delay = max(0.0, request_delay)
        self._robots: urllib.robotparser.RobotFileParser | None = None

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        sitemap_index, offset = self._parse_cursor(cursor)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml,text/xml",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
                "User-Agent": self.user_agent,
            },
        )
        try:
            await self._assert_allowed(client, self.config.sitemap_url)
            root_xml = await self._get_text(client, self.config.sitemap_url)
            root_kind, root_locations = parse_sitemap(root_xml)

            if root_kind == "sitemapindex":
                if sitemap_index >= len(root_locations):
                    return SourceBatch(jobs=[], next_cursor=None)
                current_map = root_locations[sitemap_index]
                await self._assert_allowed(client, current_map)
                sitemap_xml = await self._get_text(client, current_map)
                _, raw_offer_urls = parse_sitemap(sitemap_xml)
                total_maps = len(root_locations)
            else:
                if sitemap_index > 0:
                    return SourceBatch(jobs=[], next_cursor=None)
                raw_offer_urls = root_locations
                total_maps = 1

            offer_urls = filter_offer_urls(raw_offer_urls, self.config.detail.offer_path_patterns)
            chunk_size = max(1, self.config.chunk_size)
            selected = offer_urls[offset : offset + chunk_size]

            jobs = []
            for position, url in enumerate(selected):
                await self._assert_allowed(client, url)
                if position and self.request_delay:
                    await asyncio.sleep(self.request_delay)
                try:
                    html = await self._get_text(client, url)
                except httpx.HTTPError:
                    continue
                job = parse_job_detail_html(self.config.detail, url, html)
                if job is not None:
                    jobs.append(job)
        finally:
            if owns_client:
                await client.aclose()

        next_offset = offset + len(selected)
        if next_offset < len(offer_urls):
            next_cursor = f"{sitemap_index}:{next_offset}"
        elif sitemap_index + 1 < total_maps:
            next_cursor = f"{sitemap_index + 1}:0"
        else:
            next_cursor = None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[int, int]:
        if not cursor:
            return 0, 0
        parts = cursor.split(":", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid sitemap cursor: {cursor}")
        try:
            sitemap_index = int(parts[0])
            offset = int(parts[1])
        except ValueError as exc:
            raise ValueError(f"invalid sitemap cursor: {cursor}") from exc
        if sitemap_index < 0 or offset < 0:
            raise ValueError("sitemap cursor values cannot be negative")
        return sitemap_index, offset

    async def _assert_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._robots is None:
            parsed = urlparse(self.config.detail.base_url)
            robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
            response = await client.get(robots_url)
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            if response.status_code in {401, 403}:
                parser.parse(["User-agent: *", "Disallow: /"])
            elif response.status_code == 404:
                parser.parse(["User-agent: *", "Allow: /"])
            else:
                response.raise_for_status()
                parser.parse(response.text.splitlines())
            self._robots = parser

        if not self._robots.can_fetch(self.user_agent, url):
            raise PermissionError(f"robots.txt disallows {self.name} URL: {url}")

    @staticmethod
    async def _get_text(client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def parse_sitemap(xml_text: str) -> tuple[str, list[str]]:
    root = ET.fromstring(xml_text)
    root_name = _local_name(root.tag)
    if root_name not in {"sitemapindex", "urlset"}:
        raise ValueError(f"unsupported sitemap root: {root_name}")

    locations: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) != "loc" or node.text is None:
            continue
        value = node.text.strip()
        if value:
            locations.append(value)
    return root_name, locations


def filter_offer_urls(urls: list[str], patterns: tuple[str, ...]) -> list[str]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    output: list[str] = []
    seen: set[str] = set()
    for url in urls:
        decoded_path = unquote(urlparse(url).path)
        if not any(pattern.search(decoded_path) for pattern in compiled):
            continue
        if url in seen:
            continue
        seen.add(url)
        output.append(url)
    return output


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1].lower()
