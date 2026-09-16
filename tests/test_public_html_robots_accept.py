import httpx
import pytest

from agregator.sources.public_html import HtmlJobSourceConfig, PublicHtmlJobSource


@pytest.mark.asyncio
async def test_public_html_requests_robots_as_text_plain() -> None:
    seen_accept: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            seen_accept.append(request.headers.get("accept", ""))
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/jobs":
            return httpx.Response(200, text="<html><body>No jobs</body></html>")
        return httpx.Response(404)

    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/jobs?page={page}",
        offer_path_patterns=(r"^/job/",),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Accept": "text/html,application/xhtml+xml"},
    ) as client:
        source = PublicHtmlJobSource(config, client=client, request_delay=0)
        batch = await source.collect()

    assert batch.jobs == []
    assert seen_accept == ["text/plain,*/*;q=0.1"]
