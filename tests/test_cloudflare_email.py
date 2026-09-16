from agregator.extract import extract_channels
from agregator.models import ChannelPurpose, Decision

CF_EMAIL = "11736462787f74626251637473747d3c667e7d6774623f727e7c"


def test_cloudflare_protected_business_email_is_decoded_and_not_pseudo_form() -> None:
    html = f"""
    <html><body>
      <p>
        Business inquiries:
        <a href="/cdn-cgi/l/email-protection#{CF_EMAIL}">
          <span class="__cf_email__" data-cfemail="{CF_EMAIL}">
            [email protected]
          </span>
        </a>
      </p>
    </body></html>
    """

    channels = extract_channels(html, "https://rebel-wolves.com/en/press-center")

    email = next(item for item in channels if item.value == "business@rebel-wolves.com")
    assert email.decision == Decision.GREEN
    assert email.purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert email.kind.value == "email"
    assert "Business inquiries" in email.evidence.text

    technical_forms = [
        item
        for item in channels
        if item.kind.value == "form" and "/cdn-cgi/l/email-protection" in item.value
    ]
    assert technical_forms == []


def test_invalid_cloudflare_payload_is_ignored() -> None:
    html = """
    <p>Business inquiries:
      <a href="/cdn-cgi/l/email-protection#not-hex">[email protected]</a>
    </p>
    """

    channels = extract_channels(html, "https://example.com/contact")

    assert not any(item.value == "/cdn-cgi/l/email-protection#not-hex" for item in channels)
    assert not any("/cdn-cgi/l/email-protection" in item.value for item in channels)
