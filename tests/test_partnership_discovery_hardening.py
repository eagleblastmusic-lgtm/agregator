from agregator.crawler import WebsiteCrawler
from agregator.extract import extract_channels
from agregator.models import ChannelPurpose, Decision
from agregator.signals import classify_context


def test_wspolpraca_does_not_trigger_praca_recruitment_substring() -> None:
    purpose, decision, confidence, signal = classify_context(
        "https://example.pl/wspolpraca",
        "kontakt@example.pl",
    )

    assert purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert decision == Decision.REVIEW
    assert confidence == 0.72
    assert signal == "wspolpraca"


def test_oferty_mailbox_is_sales_review_signal() -> None:
    purpose, decision, confidence, signal = classify_context(
        "Kontakt",
        "oferty@example.pl",
    )

    assert purpose == ChannelPurpose.SALES
    assert decision == Decision.REVIEW
    assert confidence == 0.82
    assert signal == "localpart:oferty"


def test_recruitment_context_overrides_ambiguous_oferty_mailbox() -> None:
    purpose, decision, _, signal = classify_context(
        "Kariera - prześlij CV i dołącz do zespołu",
        "oferty@example.pl",
    )

    assert purpose == ChannelPurpose.RECRUITMENT
    assert decision == Decision.IGNORE
    assert signal == "recruitment"


def test_page_path_upgrades_generic_email_to_partnership_review() -> None:
    html = "<html><body><p>Kontakt: kontakt@example.pl</p></body></html>"

    channels = extract_channels(html, "https://example.pl/wspolpraca")
    email = next(item for item in channels if item.value == "kontakt@example.pl")

    assert email.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert email.decision == Decision.REVIEW


def test_checkbox_value_can_reveal_commercial_consent() -> None:
    html = """
    <html><body>
      <form action="/send">
        <input
          type="checkbox"
          name="consent"
          value="zgoda na informacje handlowe"
        >
        <button type="submit">Wyślij</button>
      </form>
    </body></html>
    """

    channels = extract_channels(html, "https://example.pl/kontakt")
    form = next(item for item in channels if item.value == "https://example.pl/send")

    assert form.purpose == ChannelPurpose.SALES
    assert form.decision == Decision.REVIEW
    assert form.confidence == 0.78


def test_javascript_partnership_link_uses_page_as_stable_endpoint() -> None:
    html = """
    <html><body>
      <a href="javascript:openPartnerForm()">Zostań partnerem</a>
    </body></html>
    """

    channels = extract_channels(html, "https://example.pl/partnerzy#cta")
    form = next(item for item in channels if item.kind.value == "form")

    assert form.value == "https://example.pl/partnerzy"
    assert form.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert form.decision == Decision.GREEN


def test_standalone_partnership_button_is_detected() -> None:
    html = """
    <html><body>
      <button data-purpose="partnership">Nawiąż współpracę</button>
    </body></html>
    """

    channels = extract_channels(html, "https://example.pl/biznes")
    form = next(item for item in channels if item.kind.value == "form")

    assert form.value == "https://example.pl/biznes"
    assert form.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert form.decision == Decision.GREEN


def test_crawler_prioritizes_supplier_and_procurement_paths() -> None:
    assert WebsiteCrawler._priority("https://example.pl/dla-dostawcow") == 0
    assert WebsiteCrawler._priority("https://example.pl/procurement") == 0
    assert WebsiteCrawler._priority("https://example.pl/vendor") == 0
