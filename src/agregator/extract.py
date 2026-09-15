from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import ChannelKind, ContactChannel, Evidence
from .signals import classify_context, contains_discovery_signal

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)


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


def extract_channels(html: str, page_url: str) -> list[ContactChannel]:
    soup = BeautifulSoup(html, "html.parser")
    text = _clean_text(soup)
    found: dict[tuple[str, str], ContactChannel] = {}

    emails = set(EMAIL_RE.findall(text))
    for anchor in soup.select('a[href^="mailto:"]'):
        raw = anchor.get("href", "")[7:].split("?", 1)[0].strip()
        if raw:
            emails.add(raw)

    for email in emails:
        context = _context(text, email)
        purpose, decision, confidence, signal = classify_context(context, email)
        channel = ContactChannel(
            kind=ChannelKind.EMAIL,
            value=email.lower(),
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
