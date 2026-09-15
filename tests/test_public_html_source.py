import json

import httpx
import pytest

from agregator.sources.public_html import (
    HtmlJobSourceConfig,
    PublicHtmlJobSource,
    extract_offer_links,
    parse_job_detail_html,
)


@pytest.mark.asyncio
async def test_public_html_source_collects_jsonld_and_preserves_payload() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/jobs?page={page}",
        offer_path_patterns=(r"^/job/",),
        max_offer_links=10,
    )
    detail_payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Backend Developer",
        "identifier": {"value": "job-123"},
        "datePosted": "2026-09-15",
        "description": "<p>Budowa usług backendowych.</p>",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "ACME Sp. z o.o.",
            "sameAs": "https://acme.example",
            "identifier": {"propertyID": "NIP", "value": "1234567890"},
        },
        "jobLocation": {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressLocality": "Warszawa"},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/jobs":
            return httpx.Response(
                200,
                text=(
                    '<a href="/job/backend-123">Backend</a>'
                    '<a href="/job/backend-123#again">Duplicate DOM link</a>'
                    '<a href="https://outside.example/job/1">Outside</a>'
                ),
            )
        if request.url.path == "/job/backend-123":
            return httpx.Response(
                200,
                text=(
                    '<script type="application/ld+json">'
                    + json.dumps(detail_payload)
                    + "</script>"
                ),
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = PublicHtmlJobSource(config, client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "fixture"
    assert job.source_id == "job-123"
    assert job.title == "Backend Developer"
    assert job.company_name == "ACME Sp. z o.o."
    assert job.city == "Warszawa"
    assert job.description == "Budowa usług backendowych."
    assert job.company_identifiers[0].kind == "nip"
    assert job.company_identifiers[0].value == "1234567890"
    assert job.company_website_candidates[0].url == "https://acme.example"
    assert job.source_payload["json_ld_job_posting"]["title"] == "Backend Developer"


@pytest.mark.asyncio
async def test_public_html_source_stops_when_robots_disallows_detail() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/list?page={page}",
        offer_path_patterns=(r"^/job/",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nAllow: /list\nDisallow: /job/\n",
            )
        if request.url.path == "/list":
            return httpx.Response(200, text='<a href="/job/1">Job</a>')
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = PublicHtmlJobSource(config, client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows"):
            await source.collect()


def test_extract_offer_links_filters_host_pattern_and_duplicate() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/list?page={page}",
        offer_path_patterns=(r"^/job/\d+",),
    )
    html = """
    <a href="/job/1">one</a>
    <a href="/job/1#fragment">one again</a>
    <a href="/company/1">company</a>
    <a href="https://elsewhere.example/job/2">external</a>
    """

    links = extract_offer_links("https://jobs.example/list", html, config)

    assert links == ["https://jobs.example/job/1"]


def test_detail_parser_has_html_selector_fallback() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/list?page={page}",
        offer_path_patterns=(r"^/job/",),
        company_selectors=(".company",),
        city_selectors=(".city",),
        description_selectors=(".description",),
    )
    html = """
    <html><head><link rel="canonical" href="https://jobs.example/job/42"></head>
    <body>
      <h1>Analityk</h1>
      <a class="company">Example S.A.</a>
      <span class="city">Gdańsk</span>
      <div class="description">Pełny opis stanowiska.</div>
    </body></html>
    """

    job = parse_job_detail_html(config, "https://jobs.example/job/42?ref=list", html)

    assert job is not None
    assert job.url == "https://jobs.example/job/42"
    assert job.company_name == "Example S.A."
    assert job.city == "Gdańsk"
    assert job.source_payload["html_fallback"]["company_name"] == "Example S.A."


def test_jsonld_location_falls_back_to_country_before_html_guessing() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/list",
        offer_path_patterns=(r"^/job/",),
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Warehouse Worker",
        "hiringOrganization": {"@type": "Organization", "name": "Agency BV"},
        "jobLocation": {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressCountry": "Holandia"},
        },
        "applicantLocationRequirements": {"@type": "Country", "name": "Holandia"},
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps(payload)
        + "</script><h1>Warehouse Worker</h1>"
    )

    job = parse_job_detail_html(config, "https://jobs.example/job/1", html)

    assert job is not None
    assert job.city == "Holandia"
