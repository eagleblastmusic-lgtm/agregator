import httpx
import pytest

from agregator.sources.aplikuj import AplikujPublicSource, extract_offer_links, parse_aplikuj_detail


@pytest.mark.asyncio
async def test_aplikuj_source_collects_public_offer_and_preserves_employer_data() -> None:
    listing = """
    <html><body>
      <a href="/oferta/123456/specjalista-ds-sprzedazy">Oferta 1</a>
      <a href="/oferta/123456/specjalista-ds-sprzedazy#opis">Duplikat</a>
      <a href="/pracodawca/acme">Pracodawca</a>
    </body></html>
    """
    detail = """
    <html><body>
      <a href="/pracodawca/acme-sa">ACME S.A.</a>
      <h1>Specjalista ds. sprzedaży</h1>
      <div>Warszawa</div>
      <div>Dodana 15 września 2026</div>
      <main>
        <p>Obsługa klientów biznesowych.</p>
        <p>Administratorem danych jest ACME S.A., NIP: 1234567890.</p>
      </main>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/praca":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta/123456/specjalista-ds-sprzedazy":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AplikujPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "aplikuj"
    assert job.source_id == "123456"
    assert job.title == "Specjalista ds. sprzedaży"
    assert job.company_name == "ACME S.A."
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-15"
    assert any(
        item.kind == "nip" and item.value == "1234567890"
        for item in job.company_identifiers
    )
    assert job.source_payload["portal_offer_id"] == "123456"
    assert job.source_payload["employer_profile_url"] == (
        "https://www.aplikuj.pl/pracodawca/acme-sa"
    )
    assert "Obsługa klientów biznesowych" in job.source_payload["visible_text"]


@pytest.mark.asyncio
async def test_aplikuj_source_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AplikujPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows Aplikuj.pl"):
            await source.collect()


def test_extract_aplikuj_offer_links_filters_and_deduplicates() -> None:
    html = """
    <a href="/oferta/111/testowa-oferta">one</a>
    <a href="/oferta/111/testowa-oferta?utm_source=x#opis">same</a>
    <a href="/pracodawca/acme">employer</a>
    <a href="https://other.example/oferta/222/other">external</a>
    """

    assert extract_offer_links("https://www.aplikuj.pl/praca", html) == [
        "https://www.aplikuj.pl/oferta/111/testowa-oferta"
    ]


def test_parse_aplikuj_detail_uses_jsonld_and_augments_nip() -> None:
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"value": "external-1"},
        "title": "Analityk danych",
        "datePosted": "2026-09-14",
        "description": "<p>Analiza danych.</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Data Sp. z o.o."},
        "jobLocation": {
          "@type": "Place",
          "address": {"@type": "PostalAddress", "addressLocality": "Gdańsk"}
        }
      }
      </script>
      <a href="/pracodawca/data">Data Sp. z o.o.</a>
      <h1>Analityk danych</h1>
      <p>NIP 9876543210</p>
    </body></html>
    """

    job = parse_aplikuj_detail(
        "https://www.aplikuj.pl/oferta/777/analityk-danych",
        html,
    )

    assert job is not None
    assert job.source_id == "777"
    assert job.company_name == "Data Sp. z o.o."
    assert job.city == "Gdańsk"
    assert job.published_at == "2026-09-14"
    assert any(
        item.kind == "nip" and item.value == "9876543210"
        for item in job.company_identifiers
    )
