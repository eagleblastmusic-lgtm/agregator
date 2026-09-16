from agregator.extract import extract_channels
from agregator.models import ChannelPurpose, Decision


def test_sales_keyword_on_job_search_route_is_recruitment_not_sales() -> None:
    html = """
    <html><body>
      <a href="/pl/szukaj-pracy?page=1&searchKeyword=Sprzedaż">Sprzedaż</a>
    </body></html>
    """

    channels = extract_channels(html, "https://www.manpower.pl/")
    channel = next(
        item
        for item in channels
        if item.value.startswith("https://www.manpower.pl/pl/szukaj-pracy")
    )

    assert channel.purpose == ChannelPurpose.RECRUITMENT
    assert channel.decision == Decision.IGNORE
    assert channel.evidence.signal == "recruitment"
