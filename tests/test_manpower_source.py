import json

import httpx
import pytest

from agregator.sources.manpower import (
    ManpowerPublicSource,
    extract_offer_links,
    parse_manpower_detail,
)


@pytest.mark.asyncio
async def test_manpower_collects_public_listing_and_detail() -> None:
    listing = """
    <html><body>
      <a href="/pl/job/28977/specjalistatka-ds-kadr">Oferta</a>
      <a href="/pl/job/28977/specjalistatka-ds-kadr?tracking=x">Duplikat</a>
      <a href="/pl/o-nas/kontakt">Kontakt</a>
    </body></html>
    """
    detail = """
    <html><body>
      <h1>Specjalista/tka ds. kadr</h1>
      <div>Numer ref.: 28977</div>
      <div>Oferta opublikowana: 04 września 2026</div>
      <main>Dla naszego klienta poszukujemy kandydata. Zakres obowiązków testowy.</main>
      <h2>Lokalizacja</h2>
      <div>Warszawa, Mazowieckie</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/pl/szukaj-pracy":
            return httpx.Response(200, text=listing)
        if request.url.path == "/pl/job/28977/specjalistatka-ds-kadr":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ManpowerPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "manpower"
    assert job.source_id == "28977"
    assert job.title == "Specjalista/tka ds. kadr"
    assert job.company_name == "ManpowerGroup Sp. z o.o."
    assert job.company_name_confidence == 0.35
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-04"
    assert job.source_payload["reference_number"] == "28977"
    assert job.source_payload["agency_fallback"] is True
    assert job.source_payload["client_employer_disclosed"] is False


@pytest.mark.asyncio
async def test_manpower_uses_pn_cursor() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/pl/szukaj-pracy/p2":
            return httpx.Response(200, text="<html><body></body></html>")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ManpowerPublicSource(client=client, request_delay=0)
        batch = await source.collect("2")

    assert "/pl/szukaj-pracy/p2" in requested
    assert batch.jobs == []
    assert batch.next_cursor is None


@pytest.mark.asyncio
async def test_manpower_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = ManpowerPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows Manpower"):
            await source.collect()


def test_extract_manpower_offer_links_filters_and_deduplicates() -> None:
    html = """
    <a href="/pl/job/15225/pracownik-linii-produkcyjnej">one</a>
    <a href="/pl/job/15225/pracownik-linii-produkcyjnej?x=1">same</a>
    <a href="/pl/szukaj-pracy/p2">page</a>
    <a href="https://example.com/pl/job/99999/external">external</a>
    """

    assert extract_offer_links("https://www.manpower.pl/pl/szukaj-pracy", html) == [
        "https://www.manpower.pl/pl/job/15225/pracownik-linii-produkcyjnej"
    ]


def test_parse_manpower_prefers_disclosed_jsonld_employer() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Kontroler jakości",
        "datePosted": "2026-09-11",
        "description": "<p>Opis stanowiska.</p>",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Klient Jawny S.A.",
            "url": "https://klient.example",
        },
        "jobLocation": {"address": {"addressLocality": "Toruń"}},
    }
    html = (
        "<html><body>"
        f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        "<h1>Kontroler jakości</h1>"
        "<div>Reference Number: 30001</div>"
        "<h2>Location</h2><div>Toruń, Kujawsko-pomorskie</div>"
        "</body></html>"
    )

    job = parse_manpower_detail(
        "https://www.manpower.pl/pl/job/30001/kontroler-jakosci",
        html,
    )

    assert job is not None
    assert job.source_id == "30001"
    assert job.company_name == "Klient Jawny S.A."
    assert job.company_name_confidence == 0.99
    assert job.city == "Toruń"
    assert job.source_payload["agency_fallback"] is False
    assert job.source_payload["client_employer_disclosed"] is True
    assert job.source_payload["reference_number"] == "30001"
