import json

import httpx
import pytest

from agregator.sources.karierawfinansach import (
    KarieraWFinansachPublicSource,
    extract_employer_profile_url,
    extract_employer_website,
)


def test_extract_employer_profile_url_prefers_matching_company_anchor() -> None:
    html = """
    <html><body>
      <a href="/pracodawca/other">Inna Firma</a>
      <a href="/pracodawca/bank-millennium-sa">Bank Millennium S.A.</a>
      <a href="/pracodawca/bank-millennium-sa">Przejdź do profilu pracodawcy</a>
    </body></html>
    """

    assert extract_employer_profile_url(
        html,
        "https://www.karierawfinansach.pl/oferta-pracy/1,test",
        "Bank Millennium S.A.",
    ) == "https://www.karierawfinansach.pl/pracodawca/bank-millennium-sa"


def test_extract_employer_website_skips_portal_social_and_app_links() -> None:
    html = """
    <html><body>
      <a href="https://przewodnik.karierawfinansach.pl/">Przewodnik</a>
      <a href="https://www.linkedin.com/company/example">LinkedIn</a>
      <a href="https://www.bankmillennium.pl/o-banku/kariera#jobs">
        https://www.bankmillennium.pl/o-banku/kariera
      </a>
      <a href="https://grupambe.pl">Agencja employer branding</a>
      <a href="https://play.google.com/store/apps/details?id=portal">Aplikacja</a>
    </body></html>
    """

    candidate = extract_employer_website(
        html,
        "https://www.karierawfinansach.pl/pracodawca/bank-millennium-sa",
    )

    assert candidate is not None
    assert candidate.url == "https://www.bankmillennium.pl/o-banku/kariera"
    assert candidate.source == "karierawfinansach.employer_profile.website"
    assert candidate.confidence == 0.95


@pytest.mark.asyncio
async def test_collect_caches_employer_profile_for_multiple_offers() -> None:
    listing = """
    <html><body>
      <a href="/oferta-pracy/101,analityk">Analityk</a>
      <a href="/oferta-pracy/102,konsultant">Konsultant</a>
    </body></html>
    """
    detail_1 = """
    <html><body>
      <h1>Analityk</h1>
      <a href="/pracodawca/bank-millennium-sa">Bank Millennium S.A.</a>
      <main>Opis oferty 1</main>
    </body></html>
    """
    detail_2 = """
    <html><body>
      <h1>Konsultant</h1>
      <a href="/pracodawca/bank-millennium-sa">Bank Millennium S.A.</a>
      <main>Opis oferty 2</main>
    </body></html>
    """
    profile = """
    <html><body>
      <a href="https://www.bankmillennium.pl/o-banku/kariera">https://www.bankmillennium.pl/o-banku/kariera</a>
      <a href="https://grupambe.pl">Agencja employer branding</a>
    </body></html>
    """
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/praca":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta-pracy/101,analityk":
            return httpx.Response(200, text=detail_1)
        if request.url.path == "/oferta-pracy/102,konsultant":
            return httpx.Response(200, text=detail_2)
        if request.url.path == "/pracodawca/bank-millennium-sa":
            return httpx.Response(200, text=profile)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KarieraWFinansachPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 2
    assert requests.count("/pracodawca/bank-millennium-sa") == 1
    for job in batch.jobs:
        assert job.source_payload["employer_profile_url"].endswith(
            "/pracodawca/bank-millennium-sa"
        )
        assert any(
            item.kind == "karierawfinansach_employer_profile"
            and item.value.endswith("/pracodawca/bank-millennium-sa")
            for item in job.company_identifiers
        )
        assert len(job.company_website_candidates) == 1
        assert job.company_website_candidates[0].url == (
            "https://www.bankmillennium.pl/o-banku/kariera"
        )


@pytest.mark.asyncio
async def test_existing_jsonld_website_avoids_employer_profile_fetch() -> None:
    listing = '<a href="/oferta-pracy/201,test">Oferta</a>'
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Analityk",
        "description": "Opis",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "ACME S.A.",
            "url": "https://acme.example",
        },
    }
    detail = f"""
    <html><body>
      <script type="application/ld+json">{json.dumps(payload)}</script>
      <a href="/pracodawca/acme">ACME S.A.</a>
    </body></html>
    """
    profile_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal profile_requests
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/praca":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta-pracy/201,test":
            return httpx.Response(200, text=detail)
        if request.url.path == "/pracodawca/acme":
            profile_requests += 1
            return httpx.Response(200, text='<a href="https://wrong.example">Wrong</a>')
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KarieraWFinansachPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source_payload["employer_profile_url"].endswith("/pracodawca/acme")
    assert [item.url for item in job.company_website_candidates] == ["https://acme.example"]
    assert profile_requests == 0
