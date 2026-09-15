import html as html_module
import json

import httpx
import pytest

from agregator.sources.ofertypracy_edu import (
    OfertyPracyEduPublicSource,
    extract_listing_offer_links,
    extract_offer_links,
    parse_offer_detail,
)


def _inertia_page(component: str, props: dict) -> str:
    payload = json.dumps(
        {
            "component": component,
            "props": props,
            "url": "/",
            "version": "test",
        },
        ensure_ascii=False,
    )
    escaped = html_module.escape(payload, quote=True)
    return f'<html><body><div id="app" data-page="{escaped}"></div></body></html>'


@pytest.mark.asyncio
async def test_source_collects_public_inertia_education_offer() -> None:
    listing = _inertia_page(
        "Home/Search/SearchIndex",
        {
            "offers": {
                "data": [
                    {
                        "id": 313542,
                        "reference": "298631/2026",
                        "position_category_name": "Nauczyciel rytmiki",
                        "published_at": "2026-09-08T05:47:55.000000Z",
                        "rspo": {"city": "Warszawa"},
                    }
                ],
                "meta": {"current_page": 1, "last_page": 2, "total": 2},
            }
        },
    )
    offer = {
        "id": 313542,
        "reference_number": 298631,
        "reference": "298631/2026",
        "status": "PUBLISHED",
        "published_at": "2026-09-08T05:47:55.000000Z",
        "position_category_name": "Nauczyciel rytmiki",
        "deadline_for_submission_of_documents": "2026-09-21T22:00:00.000000Z",
        "job_description": "Prowadzenie zajęć rytmicznych.",
        "requirements": "Przygotowanie pedagogiczne.",
        "required_application_documents_to": "rekrutacja@szkola.example",
        "contact": "Sekretariat szkoły, tel. 22 123 45 67",
        "sample_statements_available_at": "https://docs.szkola.example",
        "rspo": {
            "name": "PRZEDSZKOLE NR 328",
            "city": "Warszawa",
            "post_office": "Warszawa",
            "postal_code": "01-903",
            "phone_number": "226697813",
            "phone_number_2": None,
            "email": "sekretariat@szkola.example",
            "website": "www.szkola.example",
        },
        "employee_type": {"id": 1, "name": "Nauczyciel przedmiotu lub zajęć"},
        "position_category": None,
        "subject": None,
        "profession": None,
    }
    detail = _inertia_page("Home/Search/OfferShow", {"offer": offer})
    listing_queries: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/":
            listing_queries.append(dict(request.url.params.multi_items()))
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferty/313542":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OfertyPracyEduPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert listing_queries == [
        {
            "page": "1",
            "per_page": "25",
            "search": "1",
            "sort": "-published_at",
        }
    ]
    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "ofertypracyedu"
    assert job.source_id == "313542"
    assert job.title == "Nauczyciel rytmiki"
    assert job.company_name == "PRZEDSZKOLE NR 328"
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-08T05:47:55.000000Z"
    assert job.source_payload["official_offer_id"] == "298631/2026"
    assert "rekrutacja@szkola.example" in job.source_payload["recruitment_emails"]
    assert job.source_payload["recruitment_phones"]
    assert job.company_website_candidates[0].url == "https://www.szkola.example/"
    assert job.source_payload["public_inertia_offer"]["id"] == 313542


@pytest.mark.asyncio
async def test_source_treats_zero_total_inertia_listing_as_truthful_empty() -> None:
    listing = _inertia_page(
        "Home/Search/SearchIndex",
        {
            "offers": {
                "data": [],
                "meta": {"current_page": 1, "last_page": 1, "total": 0},
            }
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/":
            return httpx.Response(200, text=listing)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OfertyPracyEduPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.jobs == []
    assert batch.next_cursor is None


@pytest.mark.asyncio
async def test_source_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OfertyPracyEduPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows OfertyPracy.edu.pl"):
            await source.collect()


def test_extract_listing_links_reads_public_inertia_records() -> None:
    listing = _inertia_page(
        "Home/Search/SearchIndex",
        {
            "offers": {
                "data": [{"id": 159256}, {"id": 159257}, {"id": 159256}],
                "meta": {"current_page": 2, "last_page": 4, "total": 50},
            }
        },
    )

    links, next_cursor = extract_listing_offer_links(
        "https://ofertypracy.edu.pl/?page=2",
        listing,
    )

    assert links == [
        "https://ofertypracy.edu.pl/oferty/159256",
        "https://ofertypracy.edu.pl/oferty/159257",
    ]
    assert next_cursor == "3"


def test_extract_offer_links_keeps_only_legacy_portal_offer_paths() -> None:
    html = """
    <a href="/oferty/159256">one</a>
    <a href="/oferty/159256/">duplicate</a>
    <a href="/placowki/123">school</a>
    <a href="https://other.example/oferty/2">external</a>
    """

    assert extract_offer_links("https://ofertypracy.edu.pl/?page=1", html) == [
        "https://ofertypracy.edu.pl/oferty/159256"
    ]


def test_parse_inertia_detail_keeps_recruitment_contacts_as_raw_evidence() -> None:
    offer = {
        "id": 147699,
        "reference": "141107/2025",
        "published_at": "2025-09-01T08:00:00.000000Z",
        "position_category_name": "Wychowawca w świetlicy szkolnej",
        "required_application_documents_to": "sekretariat@example.edu.pl",
        "job_description": "Opieka nad uczniami.",
        "rspo": {
            "name": "SZKOŁA PODSTAWOWA NR 11",
            "city": "Warszawa",
            "email": "sekretariat@example.edu.pl",
            "phone_number": "221234567",
            "website": "https://sp11.example.edu.pl",
        },
    }
    page = _inertia_page("Home/Search/OfferShow", {"offer": offer})

    job = parse_offer_detail("https://ofertypracy.edu.pl/oferty/147699", page)

    assert job is not None
    assert job.source_payload["recruitment_emails"] == ["sekretariat@example.edu.pl"]
    assert job.source_payload["recruitment_phones"] == ["221234567"]
    assert not hasattr(job, "channels")


def test_parse_legacy_offer_detail_remains_supported() -> None:
    html = """
    <html><body>
      <div>ID: 213252/2025</div>
      <h3>Terapeuta pedagogiczny</h3>
      <h4>SZKOŁA PODSTAWOWA IM. TESTOWEJ (Szczegóły placówki)</h4>
      <div>05-400 Otwock</div>
      <div>sekretariat@szkola.example</div>
      <a href="https://szkola.example/">WWW</a>
    </body></html>
    """

    job = parse_offer_detail("https://ofertypracy.edu.pl/oferty/223593", html)

    assert job is not None
    assert job.title == "Terapeuta pedagogiczny"
    assert job.company_name == "SZKOŁA PODSTAWOWA IM. TESTOWEJ"
    assert job.city == "Otwock"
    assert job.source_payload["official_offer_id"] == "213252/2025"
