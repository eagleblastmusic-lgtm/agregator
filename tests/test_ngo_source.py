import httpx
import pytest

from agregator.sources.ngo import NgoPublicSource, extract_offer_links, parse_offer_detail


@pytest.mark.asyncio
async def test_ngo_source_collects_public_job_advertisement() -> None:
    listing = """
    <html><body>
      <a href="/548446-senior-data-and-crm-analyst.html">Oferta</a>
      <a href="/548446-senior-data-and-crm-analyst.html#x">Duplikat</a>
      <a href="/praca-staz/dam-prace?page=2">Następna</a>
    </body></html>
    """
    detail = """
    <html><body>
      <h1>Ogłoszenia - ngo.pl</h1>
      <h2>Senior Data and CRM Analyst</h2>
      <div>Warszawa</div>
      <div>15 września 2026 12:58</div>
      <p>Polska Akcja Humanitarna poszukuje osoby do zespołu.</p>
      <h2>Dane kontaktowe</h2>
      <div>Ogłoszeniodawca:</div>
      <div>Polska Akcja Humanitarna</div>
      <div>Strona internetowa:</div>
      <div><a href="https://www.pah.org.pl/">https://www.pah.org.pl/</a></div>
      <div>E-mail:</div>
      <div>Pokaż</div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/praca-staz/dam-prace":
            return httpx.Response(200, text=listing)
        if request.url.path == "/548446-senior-data-and-crm-analyst.html":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = NgoPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "ngo"
    assert job.source_id == "548446"
    assert job.title == "Senior Data and CRM Analyst"
    assert job.company_name == "Polska Akcja Humanitarna"
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-15"
    assert job.company_website_candidates[0].url == "https://www.pah.org.pl/"
    assert job.source_payload["advertiser"] == "Polska Akcja Humanitarna"
    assert job.source_payload["recruitment_email_visible"] == "Pokaż"


@pytest.mark.asyncio
async def test_ngo_source_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = NgoPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows NGO.pl"):
            await source.collect()


def test_extract_offer_links_filters_category_and_external_urls() -> None:
    html = """
    <a href="/548313-specjalista-specjalistka-ds-administracyjnych-548313.html">one</a>
    <a href="/548313-specjalista-specjalistka-ds-administracyjnych-548313.html#x">same</a>
    <a href="/praca-staz/dam-prace?page=2">pagination</a>
    <a href="https://other.example/548313-offer.html">external</a>
    """

    assert extract_offer_links("https://ogloszenia.ngo.pl/praca-staz/dam-prace", html) == [
        "https://ogloszenia.ngo.pl/548313-specjalista-specjalistka-ds-administracyjnych-548313.html"
    ]


def test_parse_ngo_detail_keeps_recruitment_contact_as_raw_evidence() -> None:
    html = """
    <html><body>
      <h2>Specjalista / Specjalistka ds. administracyjnych</h2>
      <div>Warszawa</div>
      <div>13 września 2026 10:57</div>
      <div>Ogłoszeniodawca:</div>
      <div>Stowarzyszenie mali bracia Ubogich</div>
      <div>E-mail:</div>
      <div>Pokaż</div>
    </body></html>
    """

    job = parse_offer_detail(
        "https://ogloszenia.ngo.pl/548313-specjalista-specjalistka-ds-administracyjnych-548313.html",
        html,
    )

    assert job is not None
    assert job.source_payload["recruitment_email_visible"] == "Pokaż"
    assert not hasattr(job, "channels")
