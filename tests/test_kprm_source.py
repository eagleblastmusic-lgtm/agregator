import httpx
import pytest

from agregator.sources.kprm import KprmPublicSource, extract_kprm_offer_links, parse_kprm_detail


@pytest.mark.asyncio
async def test_kprm_source_collects_public_notice_from_official_xml() -> None:
    xml = """
    <root><![CDATA[
      https://nabory.kprm.gov.pl/mazowieckie/warszawa/specjalista,167999,v8
      https://nabory.kprm.gov.pl/mazowieckie/warszawa/specjalista,167999,v8
    ]]></root>
    """
    detail = """
    <html><head>
      <title>specjalista/specjalistka | Ministerstwo Testów w Warszawie | Warszawa | Praca w służbie cywilnej</title>
    </head><body>
      <nav>Ogłoszenia o naborach</nav>
      <div class="institution">Ministerstwo Testów w Warszawie</div>
      <div>Ogłoszenie nr 167999 / 15.09.2026</div>
      <div>Poszukujemy osoby na stanowisko:</div>
      <h1>specjalista/specjalistka</h1>
      <section>
        <h2>Miejsce pracy</h2>
        <p>ul. Testowa 1, 00-001 Warszawa</p>
      </section>
      <section>
        <h2>Czym będziesz się zajmować</h2>
        <p>Analiza dokumentów i obsługa procesów.</p>
      </section>
      <div>Zapraszamy również do kontaktu telefonicznego:</div>
      <div>22 123 45 67</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/pls/serwis/app.xml":
            return httpx.Response(200, text=xml)
        if request.url.path.endswith("/specjalista,167999,v8"):
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KprmPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor is None
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "kprm"
    assert job.source_id == "167999"
    assert job.title == "specjalista/specjalistka"
    assert job.company_name == "Ministerstwo Testów w Warszawie"
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-15"
    assert "Analiza dokumentów" in (job.description or "")
    assert job.source_payload["announcement_number"] == "167999"
    assert job.source_payload["discovery_source"].endswith("/pls/serwis/app.xml")
    assert job.source_payload["recruitment_contact_phones"]


@pytest.mark.asyncio
async def test_kprm_source_chunks_xml_links_with_cursor() -> None:
    urls = "\n".join(
        f"https://nabory.kprm.gov.pl/mazowieckie/warszawa/specjalista,{167900 + i},v8"
        for i in range(3)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/pls/serwis/app.xml":
            return httpx.Response(200, text=f"<root><![CDATA[{urls}]]></root>")
        return httpx.Response(200, text="<html><body><h1>x</h1></body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KprmPublicSource(client=client, request_delay=0, max_details_per_page=2)
        first = await source.collect()
        second = await source.collect("2")

    assert first.next_cursor == "2"
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_kprm_source_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KprmPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows KPRM"):
            await source.collect()


def test_extract_kprm_offer_links_handles_html_and_xml() -> None:
    html = """
    <a href="/mazowieckie/warszawa/radca,123456,v7">one</a>
    <a href="/mazowieckie/warszawa/radca,123456,v7#x">same</a>
    https://nabory.kprm.gov.pl/pomorskie/gdansk/referent,123457,v8
    <a href="/site/results">results</a>
    """

    assert extract_kprm_offer_links("https://nabory.kprm.gov.pl/pls/serwis/app.xml", html) == [
        "https://nabory.kprm.gov.pl/mazowieckie/warszawa/radca,123456,v7",
        "https://nabory.kprm.gov.pl/pomorskie/gdansk/referent,123457,v8",
    ]


def test_parse_kprm_detail_uses_document_title_company_fallback() -> None:
    html = """
    <html><head>
      <title>referent/referentka | Urząd Testowy w Gdańsku | Gdańsk | Praca w służbie cywilnej</title>
    </head><body>
      <h1>referent/referentka</h1>
      <p>Opis bez standardowej linii daty.</p>
    </body></html>
    """

    job = parse_kprm_detail(
        "https://nabory.kprm.gov.pl/pomorskie/gdansk/referent,123123,v7",
        html,
    )

    assert job is not None
    assert job.source_id == "123123"
    assert job.company_name == "Urząd Testowy w Gdańsku"
    assert job.company_name_source == "kprm.document_title"
