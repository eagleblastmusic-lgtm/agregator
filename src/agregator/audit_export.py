from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .audit import init_audit_schema
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class WebsiteSnapshotExportResult:
    path: Path
    rows: int
    verification_runs: int
    parse_errors: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


def export_website_page_snapshots(
    store: SQLiteStore,
    output: str | Path,
) -> WebsiteSnapshotExportResult:
    """Flatten immutable website page snapshots for offline benchmark review.

    Verification attempts are preferred because they include both rejected and accepted
    candidate domains. Runs without attempts (for example a known URL scan) fall back to
    the run-level final page snapshots. The export contains hashes and text excerpts, not
    hidden/private data or a second network crawl.
    """

    store.init_schema()
    init_audit_schema(store)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)

    with store.connect() as connection:
        runs = connection.execute(
            """
            SELECT
                w.id AS verification_id,
                w.company_id,
                c.canonical_name,
                w.outcome,
                w.website_url,
                w.resolution_origin,
                w.resolution_source,
                w.website_attempts_json,
                w.page_snapshots_json,
                w.captured_at
            FROM website_verification_runs w
            JOIN companies c ON c.id = w.company_id
            ORDER BY w.id ASC
            """
        ).fetchall()

    rows: list[dict[str, Any]] = []
    parse_errors = 0
    for run in runs:
        try:
            attempts = _json_list(run["website_attempts_json"])
            final_snapshots = _json_list(run["page_snapshots_json"])
        except (json.JSONDecodeError, TypeError, ValueError):
            parse_errors += 1
            continue

        if attempts:
            rows.extend(_attempt_rows(run, attempts))
        else:
            rows.extend(_final_rows(run, final_snapshots))

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_fields(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return WebsiteSnapshotExportResult(
        path=path,
        rows=len(rows),
        verification_runs=len(runs),
        parse_errors=parse_errors,
    )


def _attempt_rows(run: Any, attempts: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt_index, attempt_raw in enumerate(attempts):
        if not isinstance(attempt_raw, dict):
            continue
        snapshots = attempt_raw.get("page_snapshots")
        if not isinstance(snapshots, list):
            continue
        for page_index, snapshot_raw in enumerate(snapshots):
            if not isinstance(snapshot_raw, dict):
                continue
            rows.append(
                _base_row(run)
                | {
                    "snapshot_scope": "attempt",
                    "attempt_index": attempt_index,
                    "attempt_url": attempt_raw.get("url"),
                    "attempt_resolved_url": attempt_raw.get("resolved_url"),
                    "attempt_accepted": attempt_raw.get("accepted"),
                    "attempt_origin": attempt_raw.get("origin"),
                    "attempt_source": attempt_raw.get("source"),
                    "page_index": page_index,
                    "page_url": snapshot_raw.get("url"),
                    "status_code": snapshot_raw.get("status_code"),
                    "content_sha256": snapshot_raw.get("content_sha256"),
                    "text_excerpt": snapshot_raw.get("text_excerpt"),
                }
            )
    return rows


def _final_rows(run: Any, snapshots: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page_index, snapshot_raw in enumerate(snapshots):
        if not isinstance(snapshot_raw, dict):
            continue
        rows.append(
            _base_row(run)
            | {
                "snapshot_scope": "final",
                "attempt_index": None,
                "attempt_url": None,
                "attempt_resolved_url": None,
                "attempt_accepted": None,
                "attempt_origin": None,
                "attempt_source": None,
                "page_index": page_index,
                "page_url": snapshot_raw.get("url"),
                "status_code": snapshot_raw.get("status_code"),
                "content_sha256": snapshot_raw.get("content_sha256"),
                "text_excerpt": snapshot_raw.get("text_excerpt"),
            }
        )
    return rows


def _base_row(run: Any) -> dict[str, Any]:
    return {
        "verification_id": run["verification_id"],
        "company_id": run["company_id"],
        "canonical_name": run["canonical_name"],
        "outcome": run["outcome"],
        "website_url": run["website_url"],
        "resolution_origin": run["resolution_origin"],
        "resolution_source": run["resolution_source"],
        "captured_at": run["captured_at"],
    }


def _json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    payload = json.loads(str(value))
    if not isinstance(payload, list):
        raise ValueError("snapshot payload must be a list")
    return payload


def _fields() -> list[str]:
    return [
        "verification_id",
        "company_id",
        "canonical_name",
        "outcome",
        "website_url",
        "resolution_origin",
        "resolution_source",
        "snapshot_scope",
        "attempt_index",
        "attempt_url",
        "attempt_resolved_url",
        "attempt_accepted",
        "attempt_origin",
        "attempt_source",
        "page_index",
        "page_url",
        "status_code",
        "content_sha256",
        "text_excerpt",
        "captured_at",
    ]
