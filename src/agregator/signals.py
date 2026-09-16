from __future__ import annotations

import re
import unicodedata

from .models import ChannelPurpose, Decision


def normalize_text(value: str) -> str:
    # Unicode NFKD does not decompose Polish ł/Ł, so map it explicitly.
    value = value.replace("Ł", "L").replace("ł", "l")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match normalized phrases without treating `praca` as part of `wspolpraca`."""

    if not phrase:
        return False
    if "@" in phrase:
        return phrase in text
    pattern = r"(?<!\w)" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text) is not None


EXPLICIT_SIGNALS: list[tuple[str, ChannelPurpose]] = [
    ("propozycje wspolpracy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("oferty wspolpracy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("nawiaz wspolprace", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("zapraszamy do wspolpracy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("kontakt dla partnerow", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnerzy biznesowi", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("zostan partnerem", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("wspolpraca b2b", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("propozycje biznesowe", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business enquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business inquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business proposals", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnership enquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnership inquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnership proposals", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business development enquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business development inquiries", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("oferty handlowe", ChannelPurpose.SALES),
    ("kontakt handlowy", ChannelPurpose.SALES),
    ("dzial handlowy", ChannelPurpose.SALES),
    ("commercial offers", ChannelPurpose.SALES),
    ("sales enquiries", ChannelPurpose.SALES),
    ("sales inquiries", ChannelPurpose.SALES),
    ("dla dostawcow", ChannelPurpose.SUPPLIER),
    ("zostan dostawca", ChannelPurpose.SUPPLIER),
    ("wspolpraca z dostawcami", ChannelPurpose.SUPPLIER),
    ("supplier enquiries", ChannelPurpose.SUPPLIER),
    ("supplier inquiries", ChannelPurpose.SUPPLIER),
    ("vendor enquiries", ChannelPurpose.SUPPLIER),
    ("vendor inquiries", ChannelPurpose.SUPPLIER),
]

EXPLICIT_COMPANY_CONTACT_SIGNALS = (
    "kontakt dla firm",
    "wspolpraca z biznesem",
)
DEDICATED_COMPANY_CONTACT_PATHS = (
    "kontakt-dla-firm",
    "wspolpraca-z-biznesem",
)

COMMERCIAL_CONSENT_SIGNALS = [
    "zgadzam sie na otrzymywanie informacji handlowych",
    "zgoda na otrzymywanie informacji handlowych",
    "wyrazam zgode na otrzymywanie informacji handlowych",
    "wyrazam zgode na przesylanie informacji handlowych",
    "zgoda na informacje handlowe",
    "consent to receive commercial information",
    "consent to receive marketing information",
]

REVIEW_SIGNALS: list[tuple[str, ChannelPurpose]] = [
    ("b2b", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnerzy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partner", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnership", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnerships", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("cooperation", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("wspolpraca", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("dla firm", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("kontakt biznesowy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business contact", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("business development", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("biznes", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("sprzedaz", ChannelPurpose.SALES),
    ("sales", ChannelPurpose.SALES),
    ("commercial", ChannelPurpose.SALES),
    ("zakupy", ChannelPurpose.SUPPLIER),
    ("procurement", ChannelPurpose.SUPPLIER),
    ("supplier", ChannelPurpose.SUPPLIER),
    ("suppliers", ChannelPurpose.SUPPLIER),
    ("vendor", ChannelPurpose.SUPPLIER),
    ("vendors", ChannelPurpose.SUPPLIER),
    ("franczyza", ChannelPurpose.FRANCHISE),
    ("franchise enquiries", ChannelPurpose.FRANCHISE),
    ("franchise inquiries", ChannelPurpose.FRANCHISE),
    ("franchise", ChannelPurpose.FRANCHISE),
]

NEGATIVE_SIGNALS = [
    "nie przyjmujemy ofert handlowych",
    "nie przesylac ofert handlowych",
    "nie wysylaj ofert handlowych",
    "zakaz przesylania ofert handlowych",
    "brak zgody na oferty handlowe",
    "no commercial offers",
    "do not send commercial offers",
    "no sales solicitations",
]

PRIVACY_SIGNALS = [
    "rodo",
    "iod",
    "inspektor ochrony danych",
    "privacy",
    "dane osobowe",
    "dpo@",
    "data protection officer",
]
RECRUITMENT_SIGNALS = [
    "rekrutacja",
    "kariera",
    "praca",
    "szukaj-pracy",
    "szukaj pracy",
    "wyszukiwarka ofert pracy",
    "cv",
    "hr@",
    "jobs@",
    "careers",
    "career",
    "recruitment",
    "talent acquisition",
]
SUPPORT_SIGNALS = [
    "obsluga klienta",
    "reklamacje",
    "pomoc",
    "support",
    "serwis",
    "customer service",
    "helpdesk",
]

LOCAL_PART_PURPOSES = {
    "wspolpraca": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "wspolpracab2b": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "partnerzy": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "partner": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "partners": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "partnership": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "partnerships": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "b2b": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "biznes": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "business": ChannelPurpose.BUSINESS_PARTNERSHIP,
    "oferty": ChannelPurpose.SALES,
    "ofertyhandlowe": ChannelPurpose.SALES,
    "handel": ChannelPurpose.SALES,
    "handlowy": ChannelPurpose.SALES,
    "sprzedaz": ChannelPurpose.SALES,
    "sales": ChannelPurpose.SALES,
    "commercial": ChannelPurpose.SALES,
    "zakupy": ChannelPurpose.SUPPLIER,
    "procurement": ChannelPurpose.SUPPLIER,
    "dostawcy": ChannelPurpose.SUPPLIER,
    "supplier": ChannelPurpose.SUPPLIER,
    "suppliers": ChannelPurpose.SUPPLIER,
    "vendor": ChannelPurpose.SUPPLIER,
    "vendors": ChannelPurpose.SUPPLIER,
    "franczyza": ChannelPurpose.FRANCHISE,
    "franchise": ChannelPurpose.FRANCHISE,
}


def _local_part_purpose(value: str) -> tuple[ChannelPurpose | None, str | None]:
    if "@" not in value:
        return None, None
    local_part = normalize_text(value.split("@", 1)[0])
    compact = re.sub(r"[^a-z0-9]", "", local_part)
    if compact in LOCAL_PART_PURPOSES:
        return LOCAL_PART_PURPOSES[compact], compact
    for token in re.split(r"[._+\-\s]+", local_part):
        compact_token = re.sub(r"[^a-z0-9]", "", token)
        if compact_token in LOCAL_PART_PURPOSES:
            return LOCAL_PART_PURPOSES[compact_token], compact_token
    return None, None


def _explicit_company_contact_signal(normalized: str) -> str | None:
    for phrase in EXPLICIT_COMPANY_CONTACT_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return phrase
    return None


def classify_context(context: str, value: str = "") -> tuple[ChannelPurpose, Decision, float, str]:
    normalized = normalize_text(f"{context} {value}")

    for phrase in NEGATIVE_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return ChannelPurpose.NEGATIVE, Decision.IGNORE, 0.99, phrase

    if any(_contains_phrase(normalized, signal) for signal in PRIVACY_SIGNALS):
        return ChannelPurpose.PRIVACY, Decision.IGNORE, 0.98, "privacy"

    for phrase, purpose in EXPLICIT_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return purpose, Decision.GREEN, 0.95, phrase

    for phrase in COMMERCIAL_CONSENT_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return ChannelPurpose.SALES, Decision.REVIEW, 0.78, phrase

    # Strong page/context negatives win over mailbox naming. This prevents addresses such
    # as oferty@... on a careers page from being treated as a business lead.
    if any(_contains_phrase(normalized, signal) for signal in RECRUITMENT_SIGNALS):
        return ChannelPurpose.RECRUITMENT, Decision.IGNORE, 0.94, "recruitment"

    local_part_purpose, local_part = _local_part_purpose(value)
    company_contact_signal = _explicit_company_contact_signal(normalized)
    dedicated_company_route = any(
        marker in normalized for marker in DEDICATED_COMPANY_CONTACT_PATHS
    )
    if company_contact_signal and (
        local_part_purpose == ChannelPurpose.BUSINESS_PARTNERSHIP
        or dedicated_company_route
    ):
        return (
            ChannelPurpose.BUSINESS_PARTNERSHIP,
            Decision.GREEN,
            0.95,
            company_contact_signal,
        )

    if any(_contains_phrase(normalized, signal) for signal in SUPPORT_SIGNALS):
        return ChannelPurpose.SUPPORT, Decision.IGNORE, 0.90, "support"

    if local_part_purpose is not None and local_part is not None:
        return local_part_purpose, Decision.REVIEW, 0.82, f"localpart:{local_part}"

    for phrase, purpose in REVIEW_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return purpose, Decision.REVIEW, 0.72, phrase

    return ChannelPurpose.GENERIC, Decision.REVIEW, 0.40, "generic"


def classify_form_context(
    context: str,
    value: str = "",
) -> tuple[ChannelPurpose, Decision, float, str]:
    """Classify a form without letting standard privacy boilerplate hide its purpose.

    Contact and sales forms routinely contain mandatory GDPR/privacy notices. Those
    notices should not turn an otherwise commercial form into a privacy-only channel.
    Recruitment and support intent still suppress commercial use, and explicit negative
    solicitation language remains authoritative.
    """

    normalized = normalize_text(f"{context} {value}")

    for phrase in NEGATIVE_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return ChannelPurpose.NEGATIVE, Decision.IGNORE, 0.99, phrase

    if any(_contains_phrase(normalized, signal) for signal in RECRUITMENT_SIGNALS):
        return ChannelPurpose.RECRUITMENT, Decision.IGNORE, 0.94, "recruitment"

    if any(_contains_phrase(normalized, signal) for signal in SUPPORT_SIGNALS):
        return ChannelPurpose.SUPPORT, Decision.IGNORE, 0.90, "support"

    for phrase in COMMERCIAL_CONSENT_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return ChannelPurpose.SALES, Decision.REVIEW, 0.78, phrase

    for phrase, purpose in EXPLICIT_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return purpose, Decision.GREEN, 0.95, phrase

    company_contact_signal = _explicit_company_contact_signal(normalized)
    dedicated_company_route = any(
        marker in normalized for marker in DEDICATED_COMPANY_CONTACT_PATHS
    )
    if company_contact_signal and dedicated_company_route:
        return (
            ChannelPurpose.BUSINESS_PARTNERSHIP,
            Decision.GREEN,
            0.95,
            company_contact_signal,
        )

    for phrase, purpose in REVIEW_SIGNALS:
        if _contains_phrase(normalized, phrase):
            return purpose, Decision.REVIEW, 0.72, phrase

    if any(_contains_phrase(normalized, signal) for signal in PRIVACY_SIGNALS):
        return ChannelPurpose.PRIVACY, Decision.IGNORE, 0.98, "privacy"

    return ChannelPurpose.GENERIC, Decision.REVIEW, 0.40, "generic"


def contains_discovery_signal(text: str) -> bool:
    normalized = normalize_text(text)
    phrases = [phrase for phrase, _ in EXPLICIT_SIGNALS + REVIEW_SIGNALS]
    phrases.extend(EXPLICIT_COMPANY_CONTACT_SIGNALS)
    phrases.extend(COMMERCIAL_CONSENT_SIGNALS)
    phrases.extend(NEGATIVE_SIGNALS)
    return any(_contains_phrase(normalized, phrase) for phrase in phrases)
