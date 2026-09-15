from agregator.sources.public_html import extract_offer_links, parse_job_detail_html
from agregator.sources.public_sources import bulldogjob_source


def test_bulldogjob_source_discovers_public_job_links() -> None:
    source = bulldogjob_source()
    html = """
    <html><body>
      <a href="/companies/jobs/255004-junior-devops-engineer-warsaw-teamquest">
        Junior DevOps Engineer
      </a>
      <a href="/companies/jobs/255004-junior-devops-engineer-warsaw-teamquest#apply">
        Duplicate
      </a>
      <a href="/companies/profiles/2964-teamquest">Company profile</a>
      <a href="https://other.example/companies/jobs/999-external">External</a>
    </body></html>
    """

    links = extract_offer_links(
        "https://bulldogjob.pl/companies/jobs",
        html,
        source.config,
    )

    assert links == [
        "https://bulldogjob.pl/companies/jobs/255004-junior-devops-engineer-warsaw-teamquest"
    ]
    assert source.config.paginated is False


def test_bulldogjob_source_parses_jsonld_jobposting() -> None:
    source = bulldogjob_source()
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"value": "255004"},
        "title": "Junior DevOps Engineer",
        "datePosted": "2026-09-15",
        "description": "<p>Praca z Docker i Kubernetes.</p>",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "TeamQuest",
          "url": "https://teamquest.pl"
        },
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Warszawa"
          }
        }
      }
      </script>
      <a href="/companies/profiles/2964-teamquest">TeamQuest</a>
      <main>Publiczna treść oferty.</main>
    </body></html>
    """

    job = parse_job_detail_html(
        source.config,
        (
            "https://bulldogjob.pl/companies/jobs/"
            "255004-junior-devops-engineer-warsaw-teamquest"
        ),
        html,
    )

    assert job is not None
    assert job.source == "bulldogjob"
    assert job.source_id == "255004"
    assert job.title == "Junior DevOps Engineer"
    assert job.company_name == "TeamQuest"
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-15"
    assert job.company_website_candidates[0].url == "https://teamquest.pl"
    assert "json_ld_job_posting" in job.source_payload


def test_bulldogjob_source_has_html_fallback_for_company_profile() -> None:
    source = bulldogjob_source()
    html = """
    <html><body>
      <h1>Backend Developer</h1>
      <a href="/companies/profiles/3527-devire">Devire</a>
      <div class="location">Warszawa</div>
      <main><p>Opis publicznej oferty.</p></main>
    </body></html>
    """

    job = parse_job_detail_html(
        source.config,
        "https://bulldogjob.pl/companies/jobs/254766-backend-developer-warsaw-devire",
        html,
    )

    assert job is not None
    assert job.company_name == "Devire"
    assert job.city == "Warszawa"
    assert job.description == "Opis publicznej oferty."
