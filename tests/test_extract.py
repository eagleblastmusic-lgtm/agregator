from agregator.extract import extract_channels
from agregator.models import ChannelPurpose, Decision


def test_explicit_partnership_email_is_green() -> None:
    html = """
    <html><body>
      <p>Propozycje współpracy biznesowej prosimy kierować na
      <a href="mailto:wspolpraca@example.pl">wspolpraca@example.pl</a>.</p>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/kontakt")
    email = next(item for item in channels if item.value == "wspolpraca@example.pl")
    assert email.decision == Decision.GREEN
    assert email.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert email.confidence >= 0.9


def test_negative_commercial_context_is_ignored() -> None:
    html = """
    <html><body>
      <p>Nie przyjmujemy ofert handlowych. kontakt@example.pl</p>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/kontakt")
    email = next(item for item in channels if item.value == "kontakt@example.pl")
    assert email.decision == Decision.IGNORE
    assert email.purpose == ChannelPurpose.NEGATIVE


def test_privacy_email_is_ignored() -> None:
    html = """
    <html><body>
      <p>Inspektor Ochrony Danych (RODO): iod@example.pl</p>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/rodo")
    email = next(item for item in channels if item.value == "iod@example.pl")
    assert email.decision == Decision.IGNORE
    assert email.purpose == ChannelPurpose.PRIVACY


def test_generic_contact_is_not_green() -> None:
    html = "<html><body><p>Kontakt: kontakt@example.pl</p></body></html>"
    channels = extract_channels(html, "https://example.pl/kontakt")
    email = next(item for item in channels if item.value == "kontakt@example.pl")
    assert email.decision == Decision.REVIEW


def test_obfuscated_at_and_dot_email_is_reconstructed_with_context() -> None:
    html = """
    <html><body>
      <p>Propozycje współpracy prosimy kierować na wspolpraca [at] example [dot] pl.</p>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/wspolpraca")
    email = next(item for item in channels if item.value == "wspolpraca@example.pl")
    assert email.decision == Decision.GREEN
    assert email.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert "wspolpraca [at] example [dot] pl" in email.evidence.text.lower()


def test_obfuscated_polish_malpa_email_is_reconstructed() -> None:
    html = """
    <html><body>
      <p>Kontakt dla partnerów: partnerzy (małpa) example.pl</p>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/partnerzy")
    email = next(item for item in channels if item.value == "partnerzy@example.pl")
    assert email.decision == Decision.GREEN
    assert email.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP


def test_commercial_consent_checkbox_marks_form_for_review() -> None:
    html = """
    <html><body>
      <form action="/kontakt/wyslij">
        <label>
          <input type="checkbox" name="marketing">
          Zgadzam się na otrzymywanie informacji handlowych drogą elektroniczną.
        </label>
        <button>Wyślij</button>
      </form>
    </body></html>
    """
    channels = extract_channels(html, "https://example.pl/kontakt")
    form = next(item for item in channels if item.value == "https://example.pl/kontakt/wyslij")
    assert form.decision == Decision.REVIEW
    assert form.purpose == ChannelPurpose.SALES
    assert form.confidence == 0.78
