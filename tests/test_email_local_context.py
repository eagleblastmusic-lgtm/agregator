from agregator.extract import extract_channels
from agregator.models import ChannelPurpose, Decision


def _email_channel(html: str, email: str):
    channels = extract_channels(html, "https://example.pl/contact")
    return next(item for item in channels if item.value == email)


def test_footer_privacy_link_does_not_turn_generic_contact_into_privacy() -> None:
    html = """
    <footer>
      <span>Kontakt:</span>
      <a href="mailto:kontakt@example.pl">kontakt@example.pl</a>
      <a href="/privacy">Polityka prywatności i RODO</a>
    </footer>
    """

    channel = _email_channel(html, "kontakt@example.pl")

    assert channel.decision == Decision.REVIEW
    assert channel.purpose == ChannelPurpose.GENERIC
    assert "rodo" not in channel.evidence.text.lower()


def test_privacy_email_in_same_semantic_block_stays_ignored() -> None:
    html = """
    <p>
      Inspektor Ochrony Danych (RODO):
      <a href="mailto:iod@example.pl">iod@example.pl</a>
    </p>
    """

    channel = _email_channel(html, "iod@example.pl")

    assert channel.decision == Decision.IGNORE
    assert channel.purpose == ChannelPurpose.PRIVACY


def test_plain_email_uses_nearby_preceding_business_label_not_footer_privacy() -> None:
    html = """
    <footer>
      <strong>Kontakt handlowy:</strong>
      <span>salesdesk@example.pl</span>
      <a href="/privacy">Polityka prywatności i RODO</a>
    </footer>
    """

    channel = _email_channel(html, "salesdesk@example.pl")

    assert channel.decision == Decision.GREEN
    assert channel.purpose == ChannelPurpose.SALES
    assert channel.evidence.signal == "kontakt handlowy"


def test_explicit_partnership_mail_keeps_green_with_separate_privacy_link() -> None:
    html = """
    <footer>
      <p>
        Propozycje współpracy:
        <a href="mailto:wspolpraca@example.pl">wspolpraca@example.pl</a>
      </p>
      <a href="/privacy">Privacy / RODO</a>
    </footer>
    """

    channel = _email_channel(html, "wspolpraca@example.pl")

    assert channel.decision == Decision.GREEN
    assert channel.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP


def test_email_inside_html_comment_is_not_discovered() -> None:
    html = """
    <div>Public contact page</div>
    <!-- internal@example.pl -->
    """

    channels = extract_channels(html, "https://example.pl/contact")

    assert all(item.value != "internal@example.pl" for item in channels)
