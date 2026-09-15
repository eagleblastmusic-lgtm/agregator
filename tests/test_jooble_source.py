import json

import httpx
import pytest

from agregator.sources.jooble import JoobleApiSource, parse_jooble_payload


def test_parse_jooble_payload() -> None:
    payload = {
        "totalCount": 1,
        "jobs": [
            {
                "id": 123,
                "title": "Python Developer",
                "location": "Warszawa",
                "snippet": "Budowa aplikacji.",
                "source": "example.com",
                "link": "https://pl.jooble.org/jdp/123",
                "company": "Example Sp. z o.o.",
                "updated": "2026-09-15T01:00:00Z",
            }
        ],
    }

    jobs = parse_jooble_payload(payload)

    assert len(jobs) == 1
    assert jobs[0].source == "jooble"
    assert jobs[0].source_id == "123"
    assert jobs[0].company_name == "Example Sp. z o.o."
    assert jobs[0].company_name_source == "api.company"
    assert jobs[0].company_name_confidence == 0.97
    assert jobs[0].city == "Warszawa"


@pytest.mark.asyncio
async def test_collect_posts_documented_jooble_payload_and_paginates() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/test-key"
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "totalCount": 50,
                "jobs": [
                    {
                        "id": index,
                        "title": f"Oferta {index}",
                        "location": "Polska",
                        "snippet": "Opis",
                        "link": f"https://pl.jooble.org/jdp/{index}",
                        "company": f"Firma {index}",
                        "updated": "2026-09-15T01:00:00Z",
                    }
                    for index in range(20)
                ],
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://pl.jooble.org",
    )
    source = JoobleApiSource(
        "test-key",
        keywords="sprzedawca",
        location="Polska",
        client=client,
        result_on_page=20,
    )

    try:
        batch = await source.collect()
    finally:
        await client.aclose()

    assert len(batch.jobs) == 20
    assert batch.next_cursor == "2"
    assert seen == [
        {
            "keywords": "sprzedawca",
            "location": "Polska",
            "page": 1,
            "ResultOnPage": 20,
            "companysearch": False,
        }
    ]
