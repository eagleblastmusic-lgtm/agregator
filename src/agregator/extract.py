from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import ChannelKind, ContactChannel, Evidence
from .signals import classify_context, contains_discovery_signal
from .url_utils import canonicalize_http_url

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
WORD_OBFUSCATED_EMAIL_RE = re.compile(
    r"(?P<local>[A-Z0-9._%+-]{1,64})\s+"
    r"(?:at|malpa|małpa)\s+"
    r"(?P<domain>[A-Z0-9-]+(?:\s+(?:dot|kropka)\s+[A-Z0-9-]+)+)",
    re.I,
)
WORD_OBFUSCATED_AT_RE = re.compile(
    r"(?P<local>[A-Z0-9._%+-]{1,64})\s+"
    r"(?:at|malpa|małpa)\s+"
    r"(?P<domain>[A-Z0-9-]+(?:\.[A-Z0-9-]+)+)",
    re.I,
)
WORD_DOT_RE = re.compile(r"\s+(?:dot|kropka)\s+", re.I)


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
        occupied.append(match.span())

    for match in WORD_OBFUSCATED_EMAIL_RE.finditer(text):
        start, end = match.span()
        if any(start >= left and end <= right for left, right in occupied):
            continue
        domain = WORD_DOT_RE.sub(".", match.group("domain"))
        email = f"{match.group('local')}@{domain}".lower()
        found[email] = match.group(0)
        occupied.append(match.span())

    for match in WORD_OBFUSCATED_AT_RE.finditer(text):
        start, end = match.span()
        if any(start >= left and end <= right for left, right in occupied):
            continue
        email = f"{match.group('local')}@{match.group('domain')}".lower()
        found[email] = match.group(0)

    return found


def _attribute_text(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "").strip()


def _form_semantics(form: Tag) -> str:
    """Collect visible and structural form semantics without user-entered values."""

    parts: list[str] = []
    visible = " ".join(form.stripped_strings).strip()
    if visible:
        parts.append(visible)

    for attribute in ("id", "name", "aria-label", "title", "data-purpose", "data-form-type"):
        value = _attribute_text(form, attribute)
        if value:
            parts.append(value)

    action = _attribute_text(form, "action")
    method = _attribute_text(form, "method")
    if action:
        parts.append(action)
    if method:
        parts.append(method)

    for control in form.find_all(("input", "textarea", "select", "button")):
        if not isinstance(control, Tag):
            continue
        for attribute in ("name", "id", "placeholder", "aria-label", "title"):
            value = _attribute_text(control, attribute)
            if value:
                parts.append(value)
        control_type = _attribute_text(control, "type").lower()
        if control.name == "input" and control_type in {"submit", "button"}:
            value = _attribute_text(control, "value")
            if value:
                parts.append(value)

    deduplicated = list(dict.fromkeys(part.strip() for part in parts if part.strip()))
    return " ".join(deduplicated)[:4000]


def _channel_url(raw: str, page_url: str) -> str | None:
    return canonicalize_http_url(raw, base_url=page_url)


def _page_channel_url(page_url: str) -> str:
    return canonicalize_http_url(page_url) or page_url


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
        if not isinstance(form, Tag):
            continue
        form_text = _form_semantics(form)
        if not contains_discovery_signal(form_text):
            continue
        raw_action = _attribute_text(form, "action")
        value = _channel_url(raw_action, page_url) if raw_action else None
        value = value or _page_channel_url(page_url)
        purpose, decision, confidence, signal = classify_context(form_text, value)
        found[(ChannelKind.FORM.value, value)] = ContactChannel(
            kind=ChannelKind.FORM,
            value=value,
            purpose=purpose,
            decision=decision,
            confidence=confidence,
            evidence=Evidence(url=page_url, text=form_text[:1000], signal=signal),
        )

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        label = " ".join(anchor.stripped_strings)
        href = _attribute_text(anchor, "href")
        combined = f"{label} {href}"
        if not contains_discovery_signal(combined):
            continue
        if href.lower().startswith("mailto:"):
            continue
        value = _channel_url(href, page_url)
        if value is None and href.startswith("#"):
            value = _page_channel_url(page_url)
        if value is None:
            continue
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
