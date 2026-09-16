import json

import httpx
import pytest

from agregator.sources.public_html import HtmlJobSourceConfig
from agregator.sources.sitemap_html import (
    SitemapHtmlJobSource,
    SitemapJobSourceConfig,
    filter_offer_urls,
    parse_sitemap,
)


def _job_html(job_id: str, company: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": f"Developer {job_id}",
        "identifier": {"value": job_id},
        "hiringOrganization": {"@type": "Organization", "name": company},
    }
    return '<script type="application/ld+json">' + json.dumps(payload) + "</script>"


@pytest.mark.asyncio
async def test_sitemap_source_walks_chunks_and_child_maps() -> None:
    detail = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/list",
        offer_path_patterns=(r"^/job/",),
        paginated=False,
    )
    config = SitemapJobSourceConfig(
        detail=detail,
        sitemap_url="https://jobs.example/sitemap-index.xml",
        chunk_size=1,
    )

    root = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://jobs.example/jobs-1.xml</loc></sitemap>
      <sitemap><loc>https://jobs.example/jobs-2.xml</loc></sitemap>
    </sitemapindex>
    """
    first_map = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://jobs.example/job/a</loc></url>
      <url><loc>https://jobs.example/job/b</loc></url>
      <url><loc>https://jobs.example/company/acme</loc></url>
    </urlset>
    """
    second_map = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://jobs.example/job/c</loc></url>
    </urlset>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if path == "/sitemap-index.xml":
            return httpx.Response(200, text=root)
        if path == "/jobs-1.xml":
            return httpx.Response(200, text=first_map)
        if path == "/jobs-2.xml":
            return httpx.Response(200, text=second_map)
        if path == "/job/a":
            return httpx.Response(200, text=_job_html("a", "A S.A."))
        if path == "/job/b":
            return httpx.Response(200, text=_job_html("b", "B S.A."))
        if path == "/job/c":
            return httpx.Response(200, text=_job_html("c", "C S.A."))
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SitemapHtmlJobSource(config, client=client, request_delay=0)
        first = await source.collect()
        second = await source.collect(first.next_cursor)
        third = await source.collect(second.next_cursor)

    assert [job.source_id for job in first.jobs] == ["a"]
    assert first.next_cursor == "0:1"
    assert [job.source_id for job in second.jobs] == ["b"]
    assert second.next_cursor == "1:0"
    assert [job.source_id for job in third.jobs] == ["c"]
    assert third.next_cursor is None


def test_parse_sitemap_accepts_urlset_and_index() -> None:
    urlset = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://jobs.example/job/1</loc></url>
    </urlset>
    """
    sitemap_index = """
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://jobs.example/a.xml</loc></sitemap>
    </sitemapindex>
    """

    assert parse_sitemap(urlset) == ("urlset", ["https://jobs.example/job/1"])
    assert parse_sitemap(sitemap_index) == (
        "sitemapindex",
        ["https://jobs.example/a.xml"],
    )


def test_filter_offer_urls_keeps_source_records_not_unrelated_pages() -> None:
    urls = [
        "https://jobs.example/job/1",
        "https://jobs.example/job/1",
        "https://jobs.example/company/acme",
        "https://jobs.example/job/2",
    ]

    assert filter_offer_urls(urls, (r"^/job/",)) == [
        "https://jobs.example/job/1",
        "https://jobs.example/job/2",
    ]
