from __future__ import annotations

import base64
import binascii
import io
import json
import re
import zipfile
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree

import httpx

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .base import SourceBatch

EPRACA_V2_ENDPOINT = "https://oferty.praca.gov.pl/integration/services/v2/oferta"
EPRACA_V2_NAMESPACE = "https://oferty.praca.gov.pl/v2/oferta"

SUCCESS_STATUS = "Poprawny"
NO_DATA_STATUS = "Brak danych"
ERROR_STATUSES = {
    "Usługa niedostępna",
    "Przekroczono limit wywołań usługi",
    "Niepoprawna autoryzacja",
}


class EPracaSource:
    """Official ePraca WebService adapter for authorized integrators.

    The service requires a Partner value assigned by MRPiPS and exactly one
    criterion: voivodeship, unit or all active offers. The adapter never attempts
    to bypass this authorization requirement.
    """

    name = "epraca"

    def __init__(
        self,
        partner: str,
        *,
        language: str = "pl",
        voivodeship: str | None = None,
        unit: str | None = None,
        all_offers: bool = False,
        endpoint: str = EPRACA_V2_ENDPOINT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not partner.strip():
            raise ValueError("ePraca partner cannot be empty")
        if language not in {"pl", "ru", "by", "en", "ua"}:
            raise ValueError("ePraca language must be one of: pl, ru, by, en, ua")

        selected = sum(
            [
                bool(voivodeship and voivodeship.strip()),
                bool(unit and unit.strip()),
                bool(all_offers),
            ]
        )
        if selected != 1:
            raise ValueError(
                "ePraca requires exactly one criterion: voivodeship, unit or all_offers"
            )

        self.partner = partner.strip()
        self.language = language
        self.voivodeship = voivodeship.strip() if voivodeship else None
        self.unit = unit.strip() if unit else None
        self.all_offers = all_offers
        self.endpoint = endpoint
        self._client = client

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        if cursor not in {None, ""}:
            raise ValueError("ePraca source is snapshot-based and does not use cursors")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"Accept": "text/xml, application/soap+xml, application/zip"},
        )

        body = build_epraca_soap_request(
            self.partner,
            language=self.language,
            voivodeship=self.voivodeship,
            unit=self.unit,
            all_offers=self.all_offers,
        )

        try:
            response = await client.post(
                self.endpoint,
                content=body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response.raise_for_status()
            jobs = parse_epraca_response(response.content)
        finally:
            if owns_client:
                await client.aclose()

        return SourceBatch(jobs=jobs, next_cursor=None)


def build_epraca_soap_request(
    partner: str,
    *,
    language: str = "pl",
    voivodeship: str | None = None,
    unit: str | None = None,
    all_offers: bool = False,
) -> str:
    selected = sum(
        [
            bool(voivodeship and voivodeship.strip()),
            bool(unit and unit.strip()),
            bool(all_offers),
        ]
    )
    if selected != 1:
        raise ValueError(
            "ePraca requires exactly one criterion: voivodeship, unit or all_offers"
        )

    criterion: str
    if voivodeship:
        criterion = f"<Wojewodztwo>{_xml_escape(voivodeship.strip())}</Wojewodztwo>"
    elif unit:
        criterion = f"<Jednostka>{_xml_escape(unit.strip())}</Jednostka>"
    else:
        criterion = "<Wszystkie>true</Wszystkie>"

    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        f'xmlns:ofer="{EPRACA_V2_NAMESPACE}">'
        "<soapenv:Header/>"
        "<soapenv:Body>"
        "<ofer:Dane>"
        "<pytanie>"
        f"<Partner>{_xml_escape(partner.strip())}</Partner>"
        f"<Jezyk>{_xml_escape(language)}</Jezyk>"
        "<Kryterium>"
        f"{criterion}"
        "</Kryterium>"
        "</pytanie>"
        "</ofer:Dane>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )


def parse_epraca_response(content: bytes) -> list[JobPosting]:
    """Parse either a direct ZIP body or the normal SOAP envelope response."""

    if content.startswith(b"PK\x03\x04"):
        return parse_epraca_zip(content)
    return parse_epraca_soap_response(content)


def parse_epraca_soap_response(content: bytes) -> list[JobPosting]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("ePraca response is not valid SOAP/XML") from exc

    texts = [
        (element.text or "").strip()
        for element in root.iter()
        if (element.text or "").strip()
    ]
    status = _detect_status(texts)
    if status == NO_DATA_STATUS:
        return []
    if status in ERROR_STATUSES:
        raise RuntimeError(f"ePraca service status: {status}")

    archive = _find_zip_payload(texts)
    if archive is None:
        if status == SUCCESS_STATUS:
            raise ValueError("ePraca response says success but contains no ZIP payload")
        raise ValueError("ePraca response contains no recognizable ZIP payload")

    return parse_epraca_zip(archive)


def parse_epraca_zip(archive: bytes) -> list[JobPosting]:
    jobs: list[JobPosting] = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for name in bundle.namelist():
                if not name.lower().endswith(".json"):
                    continue
                raw = bundle.read(name)
                payload = json.loads(raw.decode("utf-8-sig"))
                for record in _extract_offer_records(payload):
                    job = _parse_offer(record)
                    if job is not None:
                        jobs.append(job)
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ePraca ZIP payload is invalid") from exc
    return jobs


def parse_epraca_json(payload: Any) -> list[JobPosting]:
    jobs: list[JobPosting] = []
    for record in _extract_offer_records(payload):
        job = _parse_offer(record)
        if job is not None:
            jobs.append(job)
    return jobs


def _extract_offer_records(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []

    if _looks_like_offer(payload):
        return [payload]

    for key in ("oferty", "offers", "data", "listaOfert"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            nested = _extract_offer_records(value)
            if nested:
                return nested
    return []


def _looks_like_offer(record: Mapping[str, Any]) -> bool:
    return bool(record.get("stanowisko") and record.get("pracodawca"))


def _parse_offer(raw: Mapping[str, Any]) -> JobPosting | None:
    source_id = _string(raw.get("identyfikatorOferty")) or _string(raw.get("hash"))
    title = _string(raw.get("stanowisko")) or _string(raw.get("stanowiskoNrm"))
    company_name = _string(raw.get("pracodawca"))
    url = _string(raw.get("link"))

    if not source_id or not title or not company_name or not url:
        return None

    city = _string(raw.get("miejscowosc")) or _string(
        raw.get("miejscePracyCzlonPierwszy")
    )
    if city is None:
        city = _first_workplace_city(raw.get("adresyMiejscPracy"))

    description = _string(raw.get("zakresObowiazkow"))
    if not description:
        description = _string(raw.get("rodzajObowiazkow"))

    website_candidates: list[CompanyWebsiteCandidate] = []
    website_url = _string(raw.get("adresWww"))
    if website_url:
        website_candidates.append(
            CompanyWebsiteCandidate(
                url=website_url,
                source="official_feed.adresWww",
                confidence=0.98,
            )
        )

    return JobPosting(
        source="epraca",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_identifiers=_company_identifiers(raw),
        company_website_candidates=website_candidates,
        city=city,
        description=description,
        published_at=_string(raw.get("dataDodaniaOferty")),
        refreshed_at=_string(raw.get("dataAktualizacji")),
    )


def _company_identifiers(raw: Mapping[str, Any]) -> list[CompanyIdentifier]:
    identifiers: list[CompanyIdentifier] = []
    for kind, field in (("nip", "nip"), ("regon", "regon")):
        value = _string(raw.get(field))
        if not value:
            continue
        identifiers.append(
            CompanyIdentifier(
                kind=kind,
                value=value,
                source=f"official_feed.{field}",
                confidence=0.995,
            )
        )
    return identifiers


def _first_workplace_city(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, Mapping):
            continue
        city = _string(item.get("miejscowosc"))
        if city:
            return city
    return None


def _detect_status(texts: list[str]) -> str | None:
    known = {SUCCESS_STATUS, NO_DATA_STATUS, *ERROR_STATUSES}
    for text in texts:
        if text in known:
            return text
    return None


def _find_zip_payload(texts: list[str]) -> bytes | None:
    candidates = sorted(texts, key=len, reverse=True)
    for text in candidates:
        compact = re.sub(r"\s+", "", text)
        if len(compact) < 16:
            continue
        try:
            decoded = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error):
            continue
        if decoded.startswith(b"PK\x03\x04"):
            return decoded
    return None


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
