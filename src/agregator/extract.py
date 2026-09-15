from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import ChannelKind, ContactChannel, Evidence
from .signals import classify_context, contains_discovery_signal

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)
OBFUSCATED_EMAIL_RE = re.compile(
    r"(?P<local>[A-Z0-9._%+-]{1,64})\s*"
    r"(?:\[|\()\s*(?:at|malpa|małpa)\s*(?:\]|\))\s*"
    r"(?P<domain>[A-Z0-9-]+(?:\.[A-Z0-9-]+)*)\s*"
    r"(?:\[|\()\s*(?:dot|kropka)\s*(?:\]|\))\s*"
    r"(?P<tld>[A-Z]{2,24})",
    re.I,
)
OBFUSCATED_AT_RE = re.compile(
    r"(?P<local>[A-Z0-9._%+-]{1,64})\s*"
    r"(?:\[|\()\s*(?:at|malpa|małpa)\s*(?:\]|\))\s*"
    r"(?P<domain>[A-Z0-9-]+(?:\.[A-Z0-9-]+)+)",
    re.I,
)


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)


def _context(text: str, needle: str, radius: int = 220) -> str:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return text[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return text[start:end]


def _obfuscated_emails(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    occupied: list[tuple[int, int]] = []

    for match in OBFUSCATED_EMAIL_RE.finditer(text):
        email = (
            f"{match.group('local')}@{match.group('domain')}.{match.group('tld')}"
        ).lower()
        found[email] = match.group(0)
        occupied.append(match.span())

    for match in OBFUSCATED_AT_RE.finditer(text):
        start, end = match.span()
        if any(start >= left and end <= right for left, right in occupied):
            continue
        email = f"{match.group('local')}@{match.group('domain')}".lower()
        found[email] = match.group(0)

    return found


def extract_channels(html: str, page_url: str) -> list[ContactChannel]:
    soup = BeautifulSoup(html, "html.parser")
    text = _clean_text(soup)
    found: dict[tuple[str, str], ContactChannel] = {}

    email_needles: dict[str, str] = {}
    for email in EMAIL_RE.findall(text):
        email_needles[email.lower()] = email
    email_needles.update(_obfuscated_emails(text))

    for anchor in soup.select('a[href^="mailto:"]'):
        raw = anchor.get("href", "")[7:].split("?", 1)[0].strip()
        if raw:
            label = " ".join(anchor.stripped_strings).strip()
            email_needles[raw.lower()] = label or raw

    for email, needle in email_needles.items():
        context = _context(text, needle)
        purpose, decision, confidence, signal = classify_context(context, email)
        channel = ContactChannel(
            kind=ChannelKind.EMAIL,
            value=email,
            purpose=purpose,
            decision=decision,
            confidence=confidence,
            evidence=Evidence(url=page_url, text=context, signal=signal),
        )
        found[(channel.kind.value, channel.value)] = channel

    for form in soup.find_all("form"):
        form_text = " ".join(form.stripped_strings)
        if not contains_discovery_signal(form_text):
            continue
        action = form.get("action") or page_url
        value = urljoin(page_url, action)
        purpose, decision, confidence, signal = classify_context(form_text, value)
        found[(ChannelKind.FORM.value, value)] = ContactChannel(
            kind=ChannelKind.FORM,
            value=value,
            purpose=purpose,
            decision=decision,
            confidence=confidence,
            evidence=Evidence(url=page_url, text=form_text[:500], signal=signal),
        )

    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.stripped_strings)
        href = anchor["href"]
        combined = f"{label} {href}"
        if not contains_discovery_signal(combined):
            continue
        if href.startswith("mailto:"):
            continue
        value = urljoin(page_url, href)
        purpose, decision, confidence, signal = classify_context(combined, value)
        key = (ChannelKind.FORM.value, value)
        found.setdefault(
            key,
            ContactChannel(
                kind=ChannelKind.FORM,
                value=value,
                purpose=purpose,
                decision=decision,
                confidence=min(confidence, 0.86),
                evidence=Evidence(url=page_url, text=combined[:500], signal=signal),
            ),
        )

    return sorted(found.values(), key=lambda item: item.confidence, reverse=True)
