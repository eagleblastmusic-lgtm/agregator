import base64

import httpx
import pytest

from agregator.sources.careerjet import CareerjetApiSource, parse_careerjet_payload


def test_parse_careerjet_payload() -> None:
    payload = {
        "type": "JOBS",
        "hits": 1,
        "pages": 1,
        "jobs": [
            {
                "title": "Python Developer",
                "company": "Example Polska",
                "date": "Mon, 14 Sep 2026 10:15:00 GMT",
                "description": "Rozwój aplikacji backendowych.",
                "locations": "Warszawa",
                "salary": "15000 - 20000 PLN",
                "url": "https://jobviewtrack.com/v2/example-123",
            }
        ],
    }

    jobs = parse_careerjet_payload(payload)

    assert len(jobs) == 1
    assert jobs[0].source == "careerjet"
    assert jobs[0].company_name == "Example Polska"
    assert jobs[0].company_name_source == "api.company"
    assert jobs[0].company_name_confidence == 0.96
    assert jobs[0].city == "Warszawa"
    assert jobs[0].published_at == "Mon, 14 Sep 2026 10:15:00 GMT"
    assert jobs[0].source_id


def test_parse_careerjet_location_mode_returns_no_jobs() -> None:
    jobs = parse_careerjet_payload(
        {
            "type": "LOCATIONS",
            "locations": ["Warszawa, mazowieckie"],
            "message": "multiple locations found",
        }
    )
    assert jobs == []


@pytest.mark.asyncio
async def test_collect_uses_required_careerjet_publisher_parameters() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["referer"] = request.headers.get("Referer")
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "type": "JOBS",
                "hits": 40,
                "pages": 2,
                "jobs": [
                    {
                        "title": f"Oferta {index}",
                        "company": f"Firma {index}",
                        "date": "Mon, 14 Sep 2026 10:15:00 GMT",
                        "description": "Opis",
                        "locations": "Polska",
                        "url": f"https://jobviewtrack.com/v2/{index}",
                    }
                    for index in range(20)
                ],
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://search.api.careerjet.net",
    )
    source = CareerjetApiSource(
        "publisher-key",
        referer="https://faro.example/jobs",
        user_ip="203.0.113.10",
        user_agent="Mozilla/5.0 Test",
        locale_code="pl_PL",
        keywords="python",
        location="Polska",
        page_size=20,
        client=client,
    )

    try:
        batch = await source.collect()
    finally:
        await client.aclose()

    assert len(batch.jobs) == 20
    assert batch.next_cursor == "2"
    assert seen["referer"] == "https://faro.example/jobs"
    expected = base64.b64encode(b"publisher-key:").decode("ascii")
    assert seen["authorization"] == f"Basic {expected}"

    params = seen["params"]
    assert isinstance(params, dict)
    assert params["locale_code"] == "pl_PL"
    assert params["page"] == "1"
    assert params["page_size"] == "20"
    assert params["sort"] == "date"
    assert params["user_ip"] == "203.0.113.10"
    assert params["user_agent"] == "Mozilla/5.0 Test"
    assert params["keywords"] == "python"
    assert params["location"] == "Polska"


def test_careerjet_rejects_missing_required_publisher_context() -> None:
    with pytest.raises(ValueError, match="referer"):
        CareerjetApiSource(
            "publisher-key",
            referer="",
            user_ip="203.0.113.10",
            user_agent="Mozilla/5.0",
        )
