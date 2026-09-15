import httpx
import pytest

from agregator.sources.kprm import KprmPublicSource, extract_kprm_offer_links, parse_kprm_detail


@pytest.mark.asyncio
async def test_kprm_source_collects_public_notice_and_preserves_visible_text() -> None:
    listing = """
    <html><body>
      <a href="/mazowieckie/warszawa/specjalista,167999,v8">Oferta 1</a>
      <a href="/mazowieckie/warszawa/specjalista,167999,v8">Oferta duplikat linku</a>
      <a href="/site/results">Wyniki</a>
    </body></html>
    """
    detail = """
    <html><body>
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
        if request.url.path == "/":
            return httpx.Response(200, text=listing)
        if request.url.path.endswith("/specjalista,167999,v8"):
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KprmPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
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
    assert "22 123 45 67" in job.source_payload["visible_text"]
    assert job.source_payload["recruitment_contact_phones"]


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


def test_extract_kprm_offer_links_filters_non_offer_paths() -> None:
    html = """
    <a href="/mazowieckie/warszawa/radca,123456,v7">one</a>
    <a href="/mazowieckie/warszawa/radca,123456,v7#x">same</a>
    <a href="/site/results">results</a>
    <a href="https://other.example/mazowieckie/warszawa/radca,2,v7">external</a>
    """

    assert extract_kprm_offer_links("https://nabory.kprm.gov.pl/?page=1", html) == [
        "https://nabory.kprm.gov.pl/mazowieckie/warszawa/radca,123456,v7"
    ]


def test_parse_kprm_detail_uses_url_id_fallback() -> None:
    html = """
    <html><body>
      <div>Urząd Testowy w Gdańsku</div>
      <h1>referent/referentka</h1>
      <p>Opis bez standardowej linii daty.</p>
    </body></html>
    """

    job = parse_kprm_detail(
        "https://nabory.kprm.gov.pl/pomorskie/gdansk/referent,123123,v7",
        html,
    )

    assert job is None
