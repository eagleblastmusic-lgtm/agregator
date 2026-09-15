from __future__ import annotations

import re
import unicodedata

# Patterns are applied after normalize_text(), so punctuation and diacritics are
# already reduced to spaces / ASCII. Longer legal forms go first.
LEGAL_SUFFIX_PATTERNS = (
    r"\bspolka\s+komandytowo\s+akcyjna\b",
    r"\bspolka\s+z\s+ograniczona\s+odpowiedzialnoscia\b",
    r"\bspolka\s+akcyjna\b",
    r"\bspolka\s+komandytowa\b",
    r"\bspolka\s+jawna\b",
    r"\bspolka\s+cywilna\b",
    r"\bsp\s*z\s*o\s*o\b",
    r"\bsp\s*k\s*a\b",
    r"\bsp\s*j\b",
    r"\bsp\s*k\b",
    r"\bs\s*c\b",
    r"\bs\s*a\b",
    r"\bsa\b",
    r"\blimited\s+liability\s+company\b",
    r"\blimited\s+liability\b",
    r"\bltd\b",
    r"\bllc\b",
    r"\bincorporated\b",
    r"\binc\b",
    r"\bgmbh\b",
)


def normalize_text(value: str) -> str:
    value = value.strip().lower().replace("ł", "l")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_company_name(value: str) -> str:
    normalized = normalize_text(value)
    previous = None
    while normalized != previous:
        previous = normalized
        for pattern in LEGAL_SUFFIX_PATTERNS:
            normalized = re.sub(pattern, " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def company_key(name: str, city: str | None = None) -> str:
    normalized_name = normalize_company_name(name)
    normalized_city = normalize_text(city or "")
    return f"{normalized_name}|{normalized_city}" if normalized_city else normalized_name
