from __future__ import annotations

import csv
from pathlib import Path

from .models import JobPosting

REQUIRED_CSV_COLUMNS = {"url", "title", "company_name"}


def load_jobs_csv(path: str | Path, *, default_source: str = "csv") -> list[JobPosting]:
    jobs: list[JobPosting] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_CSV_COLUMNS - fieldnames
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"CSV missing required columns: {names}")

        for index, row in enumerate(reader, start=1):
            source = _value(row, "source") or default_source
            url = _value(row, "url")
            title = _value(row, "title")
            company_name = _value(row, "company_name")
            if not url or not title or not company_name:
                continue

            source_id = _value(row, "source_id") or f"row-{index}"
            confidence_text = _value(row, "company_name_confidence")
            confidence = float(confidence_text) if confidence_text else 1.0

            jobs.append(
                JobPosting(
                    source=source,
                    source_id=source_id,
                    url=url,
                    title=title,
                    company_name=company_name,
                    company_name_source=_value(row, "company_name_source") or "csv",
                    company_name_confidence=confidence,
                    city=_value(row, "city"),
                    description=_value(row, "description"),
                    published_at=_value(row, "published_at"),
                    refreshed_at=_value(row, "refreshed_at"),
                )
            )
    return jobs


def _value(row: dict[str, str | None], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None
