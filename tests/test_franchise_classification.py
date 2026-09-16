from agregator.models import ChannelPurpose, Decision
from agregator.signals import classify_context, classify_form_context


def test_franchise_only_context_requires_review() -> None:
    purpose, decision, confidence, signal = classify_context(
        "Franczyza - zostań franczyzobiorcą",
        "https://example.pl/franczyza",
    )

    assert purpose == ChannelPurpose.FRANCHISE
    assert decision == Decision.REVIEW
    assert confidence == 0.72
    assert signal == "franczyza"


def test_franchise_only_form_requires_review() -> None:
    purpose, decision, confidence, signal = classify_form_context(
        "Formularz franczyzowy",
        "https://example.pl/franczyza",
    )

    assert purpose == ChannelPurpose.FRANCHISE
    assert decision == Decision.REVIEW
    assert confidence == 0.72
    assert signal == "franczyza"


def test_explicit_business_partnership_stays_green() -> None:
    purpose, decision, confidence, signal = classify_form_context(
        "Kontakt dla firm - nawiąż współpracę",
        "https://example.pl/wspolpraca-z-biznesem/kontakt-dla-firm/",
    )

    assert purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert decision == Decision.GREEN
    assert confidence == 0.95
    assert signal in {"nawiaz wspolprace", "kontakt dla firm"}
