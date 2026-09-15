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


EXPLICIT_SIGNALS: list[tuple[str, ChannelPurpose]] = [
    ("propozycje wspolpracy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("nawiaz wspolprace", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("zapraszamy do wspolpracy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("kontakt dla partnerow", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnerzy biznesowi", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("zostan partnerem", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("wspolpraca b2b", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("propozycje biznesowe", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("oferty handlowe", ChannelPurpose.SALES),
    ("kontakt handlowy", ChannelPurpose.SALES),
    ("dzial handlowy", ChannelPurpose.SALES),
    ("dla dostawcow", ChannelPurpose.SUPPLIER),
    ("zostan dostawca", ChannelPurpose.SUPPLIER),
    ("wspolpraca z dostawcami", ChannelPurpose.SUPPLIER),
    ("franczyza", ChannelPurpose.FRANCHISE),
]

REVIEW_SIGNALS: list[tuple[str, ChannelPurpose]] = [
    ("b2b", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("partnerzy", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("wspolpraca", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("dla firm", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("biznes", ChannelPurpose.BUSINESS_PARTNERSHIP),
    ("sprzedaz", ChannelPurpose.SALES),
]

NEGATIVE_SIGNALS = [
    "nie przyjmujemy ofert handlowych",
    "nie przesylac ofert handlowych",
    "nie wysylaj ofert handlowych",
    "zakaz przesylania ofert handlowych",
    "brak zgody na oferty handlowe",
]

PRIVACY_SIGNALS = ["rodo", "iod", "inspektor ochrony danych", "privacy", "dane osobowe"]
RECRUITMENT_SIGNALS = ["rekrutacja", "kariera", "praca", "cv", "hr@"]
SUPPORT_SIGNALS = ["obsluga klienta", "reklamacje", "pomoc", "support", "serwis"]

GREEN_LOCAL_PARTS = {
    "wspolpraca",
    "partnerzy",
    "partner",
    "b2b",
    "handel",
    "handlowy",
    "sprzedaz",
    "dostawcy",
    "franczyza",
}


def classify_context(context: str, value: str = "") -> tuple[ChannelPurpose, Decision, float, str]:
    normalized = normalize_text(f"{context} {value}")

    for phrase in NEGATIVE_SIGNALS:
        if phrase in normalized:
            return ChannelPurpose.NEGATIVE, Decision.IGNORE, 0.99, phrase

    if any(signal in normalized for signal in PRIVACY_SIGNALS):
        return ChannelPurpose.PRIVACY, Decision.IGNORE, 0.98, "privacy"

    for phrase, purpose in EXPLICIT_SIGNALS:
        if phrase in normalized:
            return purpose, Decision.GREEN, 0.95, phrase

    local_part = value.split("@", 1)[0].lower() if "@" in value else ""
    if local_part in GREEN_LOCAL_PARTS:
        return ChannelPurpose.BUSINESS_PARTNERSHIP, Decision.REVIEW, 0.82, f"localpart:{local_part}"

    if any(signal in normalized for signal in RECRUITMENT_SIGNALS):
        return ChannelPurpose.RECRUITMENT, Decision.IGNORE, 0.94, "recruitment"

    if any(signal in normalized for signal in SUPPORT_SIGNALS):
        return ChannelPurpose.SUPPORT, Decision.IGNORE, 0.90, "support"

    for phrase, purpose in REVIEW_SIGNALS:
        if phrase in normalized:
            return purpose, Decision.REVIEW, 0.72, phrase

    return ChannelPurpose.GENERIC, Decision.REVIEW, 0.40, "generic"


def contains_discovery_signal(text: str) -> bool:
    normalized = normalize_text(text)
    phrases = [phrase for phrase, _ in EXPLICIT_SIGNALS + REVIEW_SIGNALS]
    return any(phrase in normalized for phrase in phrases)
