from __future__ import annotations

from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {
    "dclid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "yclid",
    "_ga",
    "_gl",
}


def is_tracking_query_key(value: str) -> bool:
    key = value.strip().lower()
    return key.startswith("utm_") or key in TRACKING_QUERY_KEYS


def canonicalize_http_url(value: str, *, base_url: str | None = None) -> str | None:
    """Return a stable public HTTP(S) URL for channel/crawl deduplication.

    The canonicalizer intentionally makes only conservative changes: it resolves
    relative URLs, removes fragments and known marketing-tracking parameters, lowercases
    the scheme/host, and removes default ports. Functional query parameters are kept in
    their original order because form endpoints may attach meaning to them.
    """

    raw = value.strip()
    if not raw:
        return None

    absolute = urljoin(base_url, raw) if base_url else raw
    absolute = urldefrag(absolute)[0]
    parsed = urlsplit(absolute)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return None

    try:
        port = parsed.port
    except ValueError:
        return None

    display_host = f"[{hostname}]" if ":" in hostname else hostname
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = display_host
    else:
        netloc = f"{display_host}:{port}"

    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not is_tracking_query_key(key)
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, parsed.path, query, ""))
