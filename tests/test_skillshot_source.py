import httpx
import pytest

from agregator.sources.skillshot import (
    SkillshotPublicSource,
    extract_employer_profile_url,
    extract_employer_website,
)


def test_extract_employer_profile_url_prefers_matching_company_anchor() -> None:
    html = """
    <html><body>
      <a href="/users/99">Inna Firma</a>
      <a href="/users/36">Teyon</a>
      <a href="/users/36">Profil pracodawcy</a>
    </body></html>
    """

    assert extract_employer_profile_url(
        html,
        "https://www.skillshot.pl/jobs/39765-narrative-designer-at-teyon",
        "Teyon",
    ) == "https://www.skillshot.pl/users/36"


def test_extract_employer_profile_url_rejects_non_numeric_user_path() -> None:
    html = '<a href="/users/teyon">Teyon</a>'

    assert extract_employer_profile_url(
        html,
        "https://www.skillshot.pl/jobs/39765-narrative-designer-at-teyon",
        "Teyon",
    ) is None


def test_extract_employer_website_uses_only_labelled_web_page_field() -> None:
    html = """
    <html><body>
      <p>Recruitment: <a href="https://teyon.elevato.net/">ATS</a></p>
      <p>Web page: <a href="http://teyon.com/#about">teyon.com</a></p>
      <p>Showreel: <a href="https://www.youtube.com/watch?v=1">YouTube</a></p>
      <p>FB: <a href="https://facebook.com/teyon">Facebook</a></p>
    </body></html>
    """

    candidate = extract_employer_website(
        html,
        "https://www.skillshot.pl/users/36",
    )

    assert candidate is not None
    assert candidate.url == "http://teyon.com/"
    assert candidate.source == "skillshot.employer_profile.web_page"
    assert candidate.confidence == 0.97


def test_extract_employer_website_rejects_portal_web_page_link() -> None:
    html = """
    <html><body>
      <p>Web page: <a href="https://jobs.skillshot.pl/company">Portal</a></p>
    </body></html>
    """

    assert extract_employer_website(
        html,
        "https://www.skillshot.pl/users/36",
    ) is None


@pytest.mark.asyncio
async def test_collect_caches_employer_profile_and_adds_strong_identifier() -> None:
    listing = """
    <html><body>
      <a href="/jobs/101-narrative-designer-at-teyon">Narrative Designer</a>
      <a href="/jobs/102-animator-at-teyon">Animator</a>
    </body></html>
    """
    detail_1 = """
    <html><body>
      <h1>Narrative Designer</h1>
      <a href="/users/36">Teyon</a>
      <main>Opis 1</main>
      <a href="https://teyon.elevato.net/">Go to recruitment site</a>
    </body></html>
    """
    detail_2 = """
    <html><body>
      <h1>Animator</h1>
      <a href="/users/36">Teyon</a>
      <main>Opis 2</main>
    </body></html>
    """
    profile = """
    <html><body>
      <h1>Teyon</h1>
      <p>Account type: Pro</p>
      <p>Web page: <a href="http://teyon.com/">teyon.com</a></p>
      <p>FB: <a href="https://facebook.com/teyon">Facebook</a></p>
    </body></html>
    """
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/jobs":
            return httpx.Response(200, text=listing)
        if request.url.path == "/jobs/101-narrative-designer-at-teyon":
            return httpx.Response(200, text=detail_1)
        if request.url.path == "/jobs/102-animator-at-teyon":
            return httpx.Response(200, text=detail_2)
        if request.url.path == "/users/36":
            return httpx.Response(200, text=profile)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SkillshotPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 2
    assert requests.count("/users/36") == 1
    for job in batch.jobs:
        assert job.source_payload["employer_profile_url"] == "https://www.skillshot.pl/users/36"
        assert any(
            item.kind == "skillshot_employer_profile"
            and item.value == "https://www.skillshot.pl/users/36"
            and item.confidence == 0.99
            for item in job.company_identifiers
        )
        assert [item.url for item in job.company_website_candidates] == ["http://teyon.com/"]


@pytest.mark.asyncio
async def test_existing_jsonld_website_avoids_profile_fetch_but_keeps_profile_id() -> None:
    listing = '<a href="/jobs/201-test-at-acme">Oferta</a>'
    detail = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Developer",
        "description": "Opis",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "ACME",
          "url": "https://acme.example"
        }
      }
      </script>
      <a href="/users/44">ACME</a>
    </body></html>
    """
    profile_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal profile_requests
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/jobs":
            return httpx.Response(200, text=listing)
        if request.url.path == "/jobs/201-test-at-acme":
            return httpx.Response(200, text=detail)
        if request.url.path == "/users/44":
            profile_requests += 1
            return httpx.Response(200, text='<p>Web page: <a href="https://wrong.example">Wrong</a></p>')
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SkillshotPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert [item.url for item in job.company_website_candidates] == ["https://acme.example"]
    assert any(item.kind == "skillshot_employer_profile" for item in job.company_identifiers)
    assert profile_requests == 0
