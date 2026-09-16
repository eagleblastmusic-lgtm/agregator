from agregator.sources.public_html import extract_offer_links, parse_job_detail_html
from agregator.sources.public_sources import rocketjobs_source, skillshot_source


def test_rocketjobs_config_accepts_current_offer_path() -> None:
    source = rocketjobs_source()
    html = """
    <a href="/oferta-pracy/acme-specjalista-warszawa-sales">Aktualna oferta</a>
    <a href="/job-offer/legacy">Stara ścieżka</a>
    """

    links = extract_offer_links("https://rocketjobs.pl/", html, source.config)

    assert links == [
        "https://rocketjobs.pl/oferta-pracy/acme-specjalista-warszawa-sales"
    ]


def test_skillshot_config_uses_current_user_employer_link() -> None:
    source = skillshot_source()
    html = """
    <html><body>
      <h1>Senior Technical Gameplay Designer</h1>
      <p>for <a href="/users/3737">Starward Industries</a> in Kraków</p>
      <article>Opis stanowiska.</article>
    </body></html>
    """

    job = parse_job_detail_html(
        source.config,
        "https://www.skillshot.pl/jobs/39524-senior-technical-gameplay-designer-at-starward-ind",
        html,
    )

    assert job is not None
    assert job.company_name == "Starward Industries"
    assert job.title == "Senior Technical Gameplay Designer"
