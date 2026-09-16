from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup
from bs4.element import Comment, Tag

from .models import ChannelKind, ContactChannel, Evidence
from .signals import classify_context, classify_form_context, contains_discovery_signal
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
_EMAIL_CONTEXT_TAGS = {"p", "li", "address", "td", "th", "dd", "dt", "label"}
_CLOUDFLARE_EMAIL_PATH = "/cdn-cgi/l/email-protection"
_CLOUDFLARE_HEX_RE = re.compile(r"^[0-9a-f]+$", re.I)


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


def _node_text(node: object) -> str:
    if isinstance(node, Tag):
        return " ".join(node.stripped_strings).strip()
    return str(node).strip()


def _bounded_preceding_context(tag: Tag, *, limit: int = 260) -> str:
    """Collect nearby labels before a contact without swallowing the whole footer."""

    parts: list[str] = []
    total = 0
    for sibling in tag.previous_siblings:
        if isinstance(sibling, Tag) and sibling.name == "a":
            break
        value = _node_text(sibling)
        if not value:
            continue
        if total + len(value) > limit:
            break
        parts.append(value)
        total += len(value) + 1
        if len(parts) >= 3:
            break
    parts.reverse()
    return " ".join(parts)


def _email_tag_context(tag: Tag, needle: str) -> str:
    """Prefer the smallest semantic contact block over page-wide flattened context."""

    current: Tag | None = tag
    while current is not None:
        if current.name in _EMAIL_CONTEXT_TAGS:
            value = _node_text(current)
            if value:
                return value[:1000]
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None

    own = _node_text(tag)
    preceding = _bounded_preceding_context(tag)
    value = " ".join(part for part in (preceding, own) if part).strip()
    if value:
        return value[:1000]
    return needle


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


def _decode_cloudflare_email(encoded: str) -> str | None:
    """Decode Cloudflare Email Address Obfuscation payloads without executing page JS."""

    payload = unquote(encoded).strip().lstrip("#")
    if (
        len(payload) < 4
        or len(payload) % 2 != 0
        or _CLOUDFLARE_HEX_RE.fullmatch(payload) is None
    ):
        return None

    try:
        key = int(payload[:2], 16)
        decoded = bytes(
            int(payload[index : index + 2], 16) ^ key
            for index in range(2, len(payload), 2)
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    match = EMAIL_RE.fullmatch(decoded.strip())
    return match.group(1).lower() if match else None


def _cloudflare_email(anchor: Tag) -> str | None:
    encoded = _attribute_text(anchor, "data-cfemail")
    if not encoded:
        protected = anchor.find(attrs={"data-cfemail": True})
        if isinstance(protected, Tag):
            encoded = _attribute_text(protected, "data-cfemail")

    if not encoded:
        href = _attribute_text(anchor, "href")
        if _CLOUDFLARE_EMAIL_PATH in href.lower() and "#" in href:
            encoded = href.rsplit("#", 1)[1].split("?", 1)[0]

    return _decode_cloudflare_email(encoded) if encoded else None


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
        if control.name == "input" and control_type in {"submit", "button", "checkbox", "radio"}:
            value = _attribute_text(control, "value")
            if value:
                parts.append(value)

    deduplicated = list(dict.fromkeys(part.strip() for part in parts if part.strip()))
    return " ".join(deduplicated)[:4000]


def _clickable_semantics(control: Tag) -> str:
    parts = [" ".join(control.stripped_strings).strip()]
    for attribute in (
        "id",
        "name",
        "aria-label",
        "title",
        "data-purpose",
        "data-target",
        "data-action",
    ):
        value = _attribute_text(control, attribute)
        if value:
            parts.append(value)
    return " ".join(dict.fromkeys(part for part in parts if part))[:2000]


def _channel_url(raw: str, page_url: str) -> str | None:
    return canonicalize_http_url(raw, base_url=page_url)


def _page_channel_url(page_url: str) -> str:
    return canonicalize_http_url(page_url) or page_url


def extract_channels(html: str, page_url: str) -> list[ContactChannel]:
    soup = BeautifulSoup(html, "html.parser")
    text = _clean_text(soup)
    found: dict[tuple[str, str], ContactChannel] = {}

    email_needles: dict[str, str] = {}
    email_contexts: dict[str, str] = {}
    for email in EMAIL_RE.findall(text):
        email_needles[email.lower()] = email
    email_needles.update(_obfuscated_emails(text))

    # Recover a DOM-local block for ordinary visible emails. This prevents unrelated footer
    # links such as `Polityka prywatności / RODO` from classifying a generic contact as DPO.
    for string_node in soup.find_all(string=True):
        if isinstance(string_node, Comment):
            continue
        raw = str(string_node)
        if "@" not in raw:
            continue
        parent = string_node.parent
        if not isinstance(parent, Tag):
            continue
        for email in EMAIL_RE.findall(raw):
            key = email.lower()
            email_needles[key] = email
            email_contexts[key] = _email_tag_context(parent, email)

    for anchor in soup.select('a[href^="mailto:"]'):
        encoded = anchor.get("href", "")[7:].split("?", 1)[0]
        decoded = unquote(encoded).strip()
        if not decoded:
            continue
        label = " ".join(anchor.stripped_strings).strip()
        for email in EMAIL_RE.findall(decoded):
            key = email.lower()
            email_needles[key] = label or email
            email_contexts[key] = _email_tag_context(anchor, label or email)

    # Cloudflare replaces protected addresses with a deterministic XOR payload. Decode the
    # payload directly from HTML so the contact remains usable without running page JavaScript.
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = _attribute_text(anchor, "href")
        protected = anchor.find(attrs={"data-cfemail": True})
        if (
            _CLOUDFLARE_EMAIL_PATH not in href.lower()
            and not anchor.has_attr("data-cfemail")
            and protected is None
        ):
            continue
        email = _cloudflare_email(anchor)
        if not email:
            continue
        label = " ".join(anchor.stripped_strings).strip()
        email_needles[email] = label or email
        email_contexts[email] = _email_tag_context(anchor, label or email)

    for email, needle in email_needles.items():
        context = email_contexts.get(email) or _context(text, needle)
        # The page path is useful evidence: /wspolpraca or /partnerzy should make an
        # otherwise generic mailbox review-worthy, while /kariera can suppress it.
        purpose, decision, confidence, signal = classify_context(
            f"{context} {page_url}",
            email,
        )
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
        purpose, decision, confidence, signal = classify_form_context(form_text, value)
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
        label = " ".join(anchor.stripped_strings).strip()
        href = _attribute_text(anchor, "href")
        if _CLOUDFLARE_EMAIL_PATH in href.lower():
            continue
        discovery_probe = label or href
        if not contains_discovery_signal(discovery_probe):
            continue
        if href.lower().startswith("mailto:"):
            continue
        combined = f"{label} {href}"
        value = _channel_url(href, page_url)
        if value is None and (
            href.startswith("#") or href.lower().startswith("javascript:")
        ):
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

    # Some modern sites open a partnership/contact modal from a button instead of a
    # literal <form> or navigable <a>. Preserve the page URL as the stable endpoint.
    for control in soup.find_all(("button", "div", "span")):
        if not isinstance(control, Tag):
            continue
        if control.find_parent("form") is not None:
            continue
        if control.name in {"div", "span"} and _attribute_text(control, "role").lower() != "button":
            continue
        semantics = _clickable_semantics(control)
        if not contains_discovery_signal(semantics):
            continue
        value = _page_channel_url(page_url)
        purpose, decision, confidence, signal = classify_context(semantics, value)
        key = (ChannelKind.FORM.value, value)
        candidate = ContactChannel(
            kind=ChannelKind.FORM,
            value=value,
            purpose=purpose,
            decision=decision,
            confidence=min(confidence, 0.84),
            evidence=Evidence(url=page_url, text=semantics[:500], signal=signal),
        )
        previous = found.get(key)
        if previous is None or candidate.confidence > previous.confidence:
            found[key] = candidate

    return sorted(found.values(), key=lambda item: item.confidence, reverse=True)
