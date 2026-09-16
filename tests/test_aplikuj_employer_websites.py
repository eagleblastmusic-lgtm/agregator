import json

import httpx
import pytest

from agregator.sources.aplikuj import (
    AplikujPublicSource,
    extract_employer_website,
    extract_offer_entries,
)


def test_extract_offer_entries_pairs_offer_with_card_employer_profile() -> None:
    html = """
    <div class="offer-card-main-wrapper">
      <a href="https://www.aplikuj.pl/oferta/111/testowa-oferta">Oferta</a>
      <a href="/pracodawca/42/acme-sa">ACME S.A.</a>
    </div>
    <div class="offer-card-main-wrapper">
      <a href="/oferta/222/druga-oferta?utm_source=x#opis">Druga</a>
      <a href="/pracodawca/99/beta">Beta</a>
    </div>
    """

    assert extract_offer_entries("https://www.aplikuj.pl/praca", html) == [
        (
            "https://www.aplikuj.pl/oferta/111/testowa-oferta",
            "https://www.aplikuj.pl/pracodawca/42/acme-sa",
        ),
        (
            "https://www.aplikuj.pl/oferta/222/druga-oferta",
            "https://www.aplikuj.pl/pracodawca/99/beta",
        ),
    ]


def test_extract_employer_website_requires_explicit_strona_www_label() -> None:
    html = """
    <html><body>
      <a href="https://www.linkedin.com/company/acme">LinkedIn</a>
      <a href="https://play.google.com/store/apps/details?id=aplikuj">Aplikacja</a>
      <a href="https://acme.example/about?from=aplikuj#team">
        Strona www acme.example
      </a>
    </body></html>
    """

    assert extract_employer_website(
        "https://www.aplikuj.pl/pracodawca/42/acme",
        html,
    ) == "https://acme.example/about?from=aplikuj"


def test_extract_employer_website_rejects_internal_aplikuj_link() -> None:
    html = '<a href="/dla-firm">Strona www Aplikuj.pl</a>'

    assert (
        extract_employer_website(
            "https://www.aplikuj.pl/pracodawca/42/acme",
            html,
        )
        is None
    )


@pytest.mark.asyncio
async def test_aplikuj_collects_profile_website_once_and_reuses_candidate() -> None:
    listing = """
    <html><body>
      <div class="offer-card-main-wrapper">
        <a href="/oferta/111/analityk">Oferta 1</a>
        <a href="/pracodawca/42/acme-sa">ACME S.A.</a>
      </div>
      <div class="offer-card-main-wrapper">
        <a href="/oferta/222/programista">Oferta 2</a>
        <a href="/pracodawca/42/acme-sa">ACME S.A.</a>
      </div>
    </body></html>
    """
    profile = """
    <html><body>
      <h1>ACME S.A.</h1>
      <h4>Zobacz nas w sieci</h4>
      <a href="https://acme.example/">Strona www acme.example</a>
      <a href="https://www.linkedin.com/company/acme">LinkedIn</a>
    </body></html>
    """
    profile_hits = 0

    def job_detail(source_id: str, title: str) -> str:
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "identifier": {"value": source_id},
            "title": title,
            "description": "<p>Opis.</p>",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "ACME S.A.",
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Warszawa",
                },
            },
        }
        return (
            '<script type="application/ld+json">'
            + json.dumps(payload)
            + "</script><h1>"
            + title
            + "</h1>"
        )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal profile_hits
        if request.url.path == "/robots.txt":
            assert request.headers.get("accept") == "text/plain,*/*;q=0.1"
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/praca":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta/111/analityk":
            return httpx.Response(200, text=job_detail("111", "Analityk"))
        if request.url.path == "/oferta/222/programista":
            return httpx.Response(200, text=job_detail("222", "Programista"))
        if request.url.path == "/pracodawca/42/acme-sa":
            profile_hits += 1
            return httpx.Response(200, text=profile)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AplikujPublicSource(
            client=client,
            request_delay=0,
            max_details_per_page=2,
        )
        batch = await source.collect()

    assert len(batch.jobs) == 2
    assert profile_hits == 1
    for job in batch.jobs:
        assert job.source_payload["employer_profile_url"] == (
            "https://www.aplikuj.pl/pracodawca/42/acme-sa"
        )
        assert len(job.company_website_candidates) == 1
        candidate = job.company_website_candidates[0]
        assert candidate.url == "https://acme.example/"
        assert candidate.source == "aplikuj.employer_profile.website"
        assert candidate.confidence == 0.95
