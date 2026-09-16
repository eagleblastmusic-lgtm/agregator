from agregator.models import ChannelPurpose, Decision
from agregator.signals import classify_context


def test_explicit_company_contact_beats_generic_support_word() -> None:
    purpose, decision, confidence, signal = classify_context(
        "Kontakt dla firm. Zapraszamy do współpracy z biznesem. Pomoc seniorom.",
        "biznes@example.org",
    )

    assert purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert decision == Decision.GREEN
    assert confidence == 0.95
    assert signal == "kontakt dla firm"


def test_explicit_business_cooperation_is_green() -> None:
    purpose, decision, _, signal = classify_context(
        "Współpraca z biznesem. Porozmawiajmy o zaangażowaniu firmy.",
        "kontakt@example.org",
    )

    assert purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
    assert decision == Decision.GREEN
    assert signal == "wspolpraca z biznesem"


def test_support_only_context_remains_ignored() -> None:
    purpose, decision, _, signal = classify_context(
        "Pomoc i obsługa klienta. Zgłoś problem z usługą.",
        "support@example.org",
    )

    assert purpose == ChannelPurpose.SUPPORT
    assert decision == Decision.IGNORE
    assert signal == "support"


def test_recruitment_context_still_overrides_commercial_mailbox_name() -> None:
    purpose, decision, _, signal = classify_context(
        "Kariera i rekrutacja. Wyślij CV na poniższy adres.",
        "oferty@example.org",
    )

    assert purpose == ChannelPurpose.RECRUITMENT
    assert decision == Decision.IGNORE
    assert signal == "recruitment"
