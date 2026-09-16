import json

import httpx
import pytest

from agregator.sources.olx import OlxPublicSource, parse_olx_html, parse_olx_payload


def _prerendered_html(*, total: int = 1, pages: int = 1) -> str:
    state = {
        "listing": {
            "listing": {
                "visibleTotalCount": total,
                "totalElements": min(total, 1000),
                "totalPages": pages,
                "ads": [
                    {
                        "id": 1034527314,
                        "title": "Kasjer Sprzedawca",
                        "url": "/d/oferta/kasjer-sprzedawca-IDABC123.html",
                        "description": "<p>Opis stanowiska</p>",
                        "createdTime": "2026-09-10T10:00:00+02:00",
                        "lastRefreshTime": "2026-09-12T10:00:00+02:00",
                        "location": {
                            "cityName": "Koleczkowo",
                            "regionName": "Pomorskie",
                        },
                        "user": {
                            "companyName": "Słodka Chatka Sp. z o.o.",
                            "name": "Kazimierz",
                        },
                    }
                ],
            }
        }
    }
    encoded = json.dumps(json.dumps(state, ensure_ascii=False))
    return f'<html><body><script>window.__PRERENDERED_STATE__= {encoded};</script></body></html>'


def test_parse_olx_public_html_prerendered_state() -> None:
    page = parse_olx_html(
        _prerendered_html(),
        page_url="https://www.olx.pl/praca/administracja-biurowa/pomorskie/",
    )

    assert page.total_count == 1
    assert page.total_pages == 1
    assert len(page.jobs) == 1
    job = page.jobs[0]
    assert job.source == "olx"
    assert job.source_id == "1034527314"
    assert job.company_name == "Słodka Chatka Sp. z o.o."
    assert job.company_name_source == "user.companyName"
    assert job.company_name_confidence == 0.95
    assert job.city == "Koleczkowo"
    assert job.description == "Opis stanowiska"
    assert job.source_payload["collection_mode"] == "public_html_prerendered"


def test_parse_olx_dom_fallback_keeps_offer_without_public_company_identity() -> None:
    html = """
    <html><body>
      <div data-cy="l-card" id="998877">
        <div data-testid="ad-card-title">
          <a href="/d/oferta/magazynier-IDXYZ987.html"><h4>Magazynier</h4></a>
        </div>
        <p data-testid="location-date">Gdańsk - Dzisiaj 12:00</p>
      </div>
      <div data-testid="total-count">1 ogłoszenie</div>
    </body></html>
    """

    page = parse_olx_html(
        html,
        page_url="https://www.olx.pl/praca/prace-magazynowe/pomorskie/",
    )

    assert len(page.jobs) == 1
    job = page.jobs[0]
    assert job.source_id == "XYZ987"
    assert job.title == "Magazynier"
    assert job.city == "Gdańsk"
    assert job.company_name == "Nieujawniony pracodawca OLX #XYZ987"
    assert job.company_name_confidence == 0.0


def test_capped_olx_shard_discovers_public_child_location_shards() -> None:
    html = _prerendered_html(total=1200, pages=25).replace(
        "</body>",
        '<a href="/praca/administracja-biurowa/wroclaw/">Wrocław</a>'
        '<a href="/praca/administracja-biurowa/legnica/">Legnica</a>'
        "</body>",
    )

    page = parse_olx_html(
        html,
        page_url="https://www.olx.pl/praca/administracja-biurowa/dolnoslaskie/",
    )

    assert page.total_count == 1200
    assert page.total_pages == 25
    assert "https://www.olx.pl/praca/administracja-biurowa/wroclaw/" in page.child_shards
    assert "https://www.olx.pl/praca/administracja-biurowa/legnica/" in page.child_shards


@pytest.mark.asyncio
async def test_olx_source_uses_public_html_not_blocked_api() -> None:
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            text=_prerendered_html(),
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OlxPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 1
    assert requested_urls == [
        "https://www.olx.pl/praca/administracja-biurowa/dolnoslaskie/"
    ]
    assert "/api/" not in requested_urls[0]
    assert batch.next_cursor is not None


def test_parse_olx_prefers_company_name() -> None:
    payload = {
        "data": [
            {
                "id": 1034527314,
                "title": "Kasjer Sprzedawca",
                "url": "https://www.olx.pl/oferta/praca/test.html",
                "description": "Opis",
                "created_time": "2026-09-10T10:00:00+02:00",
                "last_refresh_time": "2026-09-12T10:00:00+02:00",
                "location": {"city": {"name": "Koleczkowo"}},
                "user": {
                    "company_name": "Słodka Chatka Sp. z o.o.",
                    "name": "Kazimierz",
                },
            }
        ]
    }

    jobs = parse_olx_payload(payload)

    assert len(jobs) == 1
    assert jobs[0].source == "olx"
    assert jobs[0].source_id == "1034527314"
    assert jobs[0].company_name == "Słodka Chatka Sp. z o.o."
    assert jobs[0].company_name_source == "user.company_name"
    assert jobs[0].company_name_confidence == 0.95
    assert jobs[0].city == "Koleczkowo"


def test_parse_olx_marks_account_name_as_low_confidence_fallback() -> None:
    payload = {
        "data": [
            {
                "id": 1,
                "title": "Piekarz",
                "url": "https://www.olx.pl/oferta/praca/piekarz.html",
                "location": {"city": {"name": "Gdynia"}},
                "user": {"company_name": "", "name": "Kazimierz"},
                "contact": {"name": "Kazimierz"},
            }
        ]
    }

    job = parse_olx_payload(payload)[0]

    assert job.company_name == "Kazimierz"
    assert job.company_name_source == "user.name"
    assert job.company_name_confidence == 0.45


def test_parse_olx_skips_offer_without_identity() -> None:
    payload = {
        "data": [
            {
                "id": 1,
                "title": "Piekarz",
                "url": "https://www.olx.pl/oferta/praca/piekarz.html",
                "user": {"company_name": "", "name": ""},
            }
        ]
    }

    assert parse_olx_payload(payload) == []
