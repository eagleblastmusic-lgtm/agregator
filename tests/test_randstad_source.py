import json

import httpx
import pytest

from agregator.sources.randstad import (
    RandstadPublicSource,
    extract_offer_links,
    parse_randstad_detail,
)


@pytest.mark.asyncio
async def test_randstad_collects_public_listing_and_detail() -> None:
    listing = """
    <html><body>
      <a href="/znajdz-prace/specjalista_warszawa_123456/">Oferta</a>
      <a href="/znajdz-prace/specjalista_warszawa_123456/?x=1">Duplikat</a>
      <a href="/kontakt-ogolny/">Kontakt</a>
    </body></html>
    """
    detail = """
    <html><body>
      <h1>specjalista ds. jakości.</h1>
      <div>Warszawa, mazowieckie</div>
      <div>opublikowano 10 września 2026</div>
      <div>reference number</div><div>46960619</div>
      <main>Dla naszego klienta prowadzimy rekrutację. Zakres obowiązków testowy.</main>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/znajdz-prace/":
            return httpx.Response(200, text=listing)
        if request.url.path == "/znajdz-prace/specjalista_warszawa_123456/":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RandstadPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "randstad"
    assert job.source_id == "123456"
    assert job.title == "specjalista ds. jakości."
    assert job.company_name == "Randstad Polska Sp. z o.o."
    assert job.company_name_confidence == 0.35
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-10"
    assert job.source_payload["agency_fallback"] is True
    assert job.source_payload["client_employer_disclosed"] is False


@pytest.mark.asyncio
async def test_randstad_uses_page_n_cursor() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/znajdz-prace/page-2/":
            return httpx.Response(200, text="<html><body></body></html>")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RandstadPublicSource(client=client, request_delay=0)
        batch = await source.collect("2")

    assert "/znajdz-prace/page-2/" in requested
    assert batch.jobs == []
    assert batch.next_cursor is None


@pytest.mark.asyncio
async def test_randstad_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RandstadPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows Randstad"):
            await source.collect()


def test_extract_randstad_offer_links_filters_and_deduplicates() -> None:
    html = """
    <a href="/znajdz-prace/operator_lodz_100001/">one</a>
    <a href="/znajdz-prace/operator_lodz_100001/?tracking=x">same</a>
    <a href="/znajdz-prace/page-2/">page</a>
    <a href="https://example.com/znajdz-prace/operator_lodz_100002/">external</a>
    """

    assert extract_offer_links("https://www.randstad.pl/znajdz-prace/", html) == [
        "https://www.randstad.pl/znajdz-prace/operator_lodz_100001/"
    ]


def test_parse_randstad_prefers_disclosed_jsonld_employer() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Inżynier procesu",
        "datePosted": "2026-09-12",
        "description": "<p>Opis stanowiska.</p>",
        "identifier": {"value": "ABC-42"},
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Fabryka Testowa S.A.",
            "url": "https://fabryka.example",
        },
        "jobLocation": {
            "address": {
                "addressLocality": "Poznań",
            }
        },
    }
    html = (
        "<html><body>"
        f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        "<h1>Inżynier procesu</h1>"
        "<div>reference number 998877</div>"
        "</body></html>"
    )

    job = parse_randstad_detail(
        "https://www.randstad.pl/znajdz-prace/inzynier-procesu_poznan_200002/",
        html,
    )

    assert job is not None
    assert job.source_id == "200002"
    assert job.company_name == "Fabryka Testowa S.A."
    assert job.company_name_confidence == 0.99
    assert job.source_payload["agency_fallback"] is False
    assert job.source_payload["client_employer_disclosed"] is True
    assert job.source_payload["reference_number"] == "998877"
