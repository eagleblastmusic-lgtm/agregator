import base64
import io
import json
import zipfile

import httpx
import pytest

from agregator.sources.epraca import (
    EPracaSource,
    build_epraca_soap_request,
    parse_epraca_json,
    parse_epraca_soap_response,
)


def _offer(index: int = 1) -> dict[str, object]:
    return {
        "identyfikatorOferty": f"EPRACA-{index}",
        "stanowisko": "Sprzedawca",
        "stanowiskoNrm": "Sprzedawca",
        "pracodawca": "Przykładowa Firma Sp. z o.o.",
        "miejscowosc": "Gdańsk",
        "zakresObowiazkow": "Obsługa klientów i kasy.",
        "dataDodaniaOferty": "2026-09-15",
        "dataAktualizacji": "2026-09-15",
        "link": f"https://oferty.praca.gov.pl/portal/lista-ofert/szczegoly-oferty/hash-{index}",
        "nip": "1234567890",
        "regon": "123456789",
    }


def _zip_payload(payload: object) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("oferty_1.json", json.dumps(payload, ensure_ascii=False))
    return stream.getvalue()


def _soap_response(status: str, archive: bytes | None = None) -> bytes:
    payload = ""
    if archive is not None:
        payload = f"<plik>{base64.b64encode(archive).decode('ascii')}</plik>"
    return (
        "<soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>"
        "<soap:Body><DaneResponse><return>"
        f"<status>{status}</status>{payload}"
        "</return></DaneResponse></soap:Body></soap:Envelope>"
    ).encode("utf-8")


def test_parse_epraca_json_maps_official_fields() -> None:
    jobs = parse_epraca_json([_offer()])

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "epraca"
    assert job.source_id == "EPRACA-1"
    assert job.title == "Sprzedawca"
    assert job.company_name == "Przykładowa Firma Sp. z o.o."
    assert job.company_name_source == "official_feed.pracodawca"
    assert job.company_name_confidence == 0.995
    assert job.city == "Gdańsk"
    assert job.published_at == "2026-09-15"


def test_parse_epraca_soap_response_extracts_zip_json() -> None:
    archive = _zip_payload({"oferty": [_offer(1), _offer(2)]})

    jobs = parse_epraca_soap_response(_soap_response("Poprawny", archive))

    assert [job.source_id for job in jobs] == ["EPRACA-1", "EPRACA-2"]


def test_parse_epraca_no_data_status_returns_empty_list() -> None:
    assert parse_epraca_soap_response(_soap_response("Brak danych")) == []


def test_parse_epraca_auth_error_is_explicit() -> None:
    with pytest.raises(RuntimeError, match="Niepoprawna autoryzacja"):
        parse_epraca_soap_response(_soap_response("Niepoprawna autoryzacja"))


def test_build_epraca_request_uses_v2_language_and_single_criterion() -> None:
    body = build_epraca_soap_request(
        "Faro Partner",
        language="pl",
        voivodeship="22",
    )

    assert "https://oferty.praca.gov.pl/v2/oferta" in body
    assert "<Partner>Faro Partner</Partner>" in body
    assert "<Jezyk>pl</Jezyk>" in body
    assert "<Wojewodztwo>22</Wojewodztwo>" in body
    assert "<Wszystkie>" not in body


@pytest.mark.asyncio
async def test_collect_posts_soap_and_returns_snapshot() -> None:
    seen: dict[str, object] = {}
    archive = _zip_payload([_offer()])

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content_type"] = request.headers.get("Content-Type")
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, content=_soap_response("Poprawny", archive))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://oferty.praca.gov.pl",
    )
    source = EPracaSource(
        "Faro Partner",
        all_offers=True,
        client=client,
    )

    try:
        batch = await source.collect()
    finally:
        await client.aclose()

    assert len(batch.jobs) == 1
    assert batch.next_cursor is None
    assert seen["method"] == "POST"
    assert "text/xml" in str(seen["content_type"])
    assert "<Wszystkie>true</Wszystkie>" in str(seen["body"])


def test_epraca_requires_exactly_one_scope() -> None:
    with pytest.raises(ValueError, match="exactly one criterion"):
        EPracaSource("Faro Partner")

    with pytest.raises(ValueError, match="exactly one criterion"):
        EPracaSource(
            "Faro Partner",
            voivodeship="22",
            all_offers=True,
        )
