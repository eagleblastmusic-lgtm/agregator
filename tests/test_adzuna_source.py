import httpx
import pytest

from agregator.sources.adzuna import AdzunaApiSource, parse_adzuna_payload


def test_parse_adzuna_payload() -> None:
    payload = {
        "count": 1,
        "results": [
            {
                "id": "abc-123",
                "title": "Data Engineer",
                "description": "Budowa pipeline'ów danych.",
                "created": "2026-09-15T01:00:00Z",
                "redirect_url": "https://www.adzuna.pl/details/abc-123",
                "company": {"display_name": "Example Polska"},
                "location": {"display_name": "Warszawa"},
            }
        ],
    }

    jobs = parse_adzuna_payload(payload)

    assert len(jobs) == 1
    assert jobs[0].source == "adzuna"
    assert jobs[0].source_id == "abc-123"
    assert jobs[0].company_name == "Example Polska"
    assert jobs[0].company_name_source == "api.company.display_name"
    assert jobs[0].company_name_confidence == 0.97
    assert jobs[0].city == "Warszawa"


@pytest.mark.asyncio
async def test_collect_calls_adzuna_search_endpoint() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/api/jobs/pl/search/1"
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "count": 40,
                "results": [
                    {
                        "id": str(index),
                        "title": f"Oferta {index}",
                        "description": "Opis",
                        "created": "2026-09-15T01:00:00Z",
                        "redirect_url": f"https://www.adzuna.pl/details/{index}",
                        "company": {"display_name": f"Firma {index}"},
                        "location": {"display_name": "Polska"},
                    }
                    for index in range(20)
                ],
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.adzuna.com",
    )
    source = AdzunaApiSource(
        "app-id",
        "app-key",
        what="python",
        where="Polska",
        client=client,
        results_per_page=20,
    )

    try:
        batch = await source.collect()
    finally:
        await client.aclose()

    assert len(batch.jobs) == 20
    assert batch.next_cursor == "2"
    assert seen[0]["app_id"] == "app-id"
    assert seen[0]["app_key"] == "app-key"
    assert seen[0]["results_per_page"] == "20"
    assert seen[0]["what"] == "python"
    assert seen[0]["where"] == "Polska"
