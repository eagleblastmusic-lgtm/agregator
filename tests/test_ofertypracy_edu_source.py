import httpx
import pytest

from agregator.sources.ofertypracy_edu import (
    OfertyPracyEduPublicSource,
    extract_offer_links,
    parse_offer_detail,
)


@pytest.mark.asyncio
async def test_source_collects_public_education_offer() -> None:
    listing = """
    <html><body>
      <a href="/oferty/223593">Oferta</a>
      <a href="/oferty/223593?x=1">Duplikat</a>
      <a href="https://other.example/oferty/1">External</a>
    </body></html>
    """
    detail = """
    <html><body>
      <div>ID: 213252/2025</div>
      <h3>Terapeuta pedagogiczny</h3>
      <h4>SZKOŁA PODSTAWOWA IM. TESTOWEJ (Szczegóły placówki)</h4>
      <h2>Szczegóły oferty</h2>
      <div>Miejsce zatrudnienia</div>
      <div>SZKOŁA PODSTAWOWA IM. TESTOWEJ</div>
      <div>ul. Szkolna 1</div>
      <div>05-400 Otwock</div>
      <div>221234567</div>
      <div>sekretariat@szkola.example</div>
      <a href="https://szkola.example/">www.szkola.example</a>
      <h2>Opis oferty pracy</h2>
      <p>Praca z uczniami.</p>
      <p>Wymagane dokumenty aplikacyjne: sekretariat@szkola.example</p>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferty/223593":
            return httpx.Response(200, text=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OfertyPracyEduPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert batch.next_cursor == "2"
    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.source == "ofertypracyedu"
    assert job.source_id == "223593"
    assert job.title == "Terapeuta pedagogiczny"
    assert job.company_name == "SZKOŁA PODSTAWOWA IM. TESTOWEJ"
    assert job.city == "Otwock"
    assert job.source_payload["official_offer_id"] == "213252/2025"
    assert "sekretariat@szkola.example" in job.source_payload["recruitment_emails"]
    assert job.source_payload["recruitment_phones"]
    assert job.company_website_candidates[0].url.startswith("https://szkola.example")


@pytest.mark.asyncio
async def test_source_respects_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OfertyPracyEduPublicSource(client=client, request_delay=0)
        with pytest.raises(PermissionError, match="robots.txt disallows OfertyPracy.edu.pl"):
            await source.collect()


def test_extract_offer_links_keeps_only_portal_offer_paths() -> None:
    html = """
    <a href="/oferty/159256">one</a>
    <a href="/oferty/159256/">duplicate</a>
    <a href="/placowki/123">school</a>
    <a href="https://other.example/oferty/2">external</a>
    """

    assert extract_offer_links("https://ofertypracy.edu.pl/?page=1", html) == [
        "https://ofertypracy.edu.pl/oferty/159256"
    ]


def test_parse_offer_detail_does_not_promote_recruitment_contact_to_green() -> None:
    html = """
    <html><body>
      <div>ID: 141107/2025</div>
      <h3>Wychowawca w świetlicy szkolnej</h3>
      <h4>SZKOŁA PODSTAWOWA NR 11 (Szczegóły placówki)</h4>
      <div>02-495 Warszawa</div>
      <div>sekretariat@example.edu.pl</div>
      <a href="https://sp11.example.edu.pl">WWW</a>
    </body></html>
    """

    job = parse_offer_detail("https://ofertypracy.edu.pl/oferty/147699", html)

    assert job is not None
    assert job.source_payload["recruitment_emails"] == ["sekretariat@example.edu.pl"]
    assert not hasattr(job, "channels")
