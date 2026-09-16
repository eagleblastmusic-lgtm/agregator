from agregator.sources.public_html import PublicHtmlJobSource, extract_offer_links
from agregator.sources.public_sources import pracuj_source


def test_pracuj_uses_public_paginated_html_listing() -> None:
    source = pracuj_source()

    assert isinstance(source, PublicHtmlJobSource)
    assert source.config.listing_url_template == "https://www.pracuj.pl/praca?pn={page}"
    assert source.config.paginated is True
    assert source.config.start_page == 1


def test_pracuj_current_offer_links_are_discovered_from_listing_html() -> None:
    source = pracuj_source()
    html = """
    <a href="/praca/ksiegowy-ksiegowa-wroclaw,oferta,1005020561">Księgowy</a>
    <a href="/praca/ksiegowy-ksiegowa-wroclaw,oferta,1005020561#apply">duplikat</a>
    <a href="https://pracodawcy.pracuj.pl/company/123">profil firmy</a>
    """

    links = extract_offer_links(
        "https://www.pracuj.pl/praca?pn=1",
        html,
        source.config,
    )

    assert links == [
        "https://www.pracuj.pl/praca/ksiegowy-ksiegowa-wroclaw,oferta,1005020561"
    ]
