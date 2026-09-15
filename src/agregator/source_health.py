from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source: str
    state: str
    runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    success_rate: float | None = None
    jobs_seen: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    companies_created: int = 0
    latest_status: str | None = None
    latest_started_at: str | None = None
    latest_finished_at: str | None = None
    last_success_at: str | None = None
    last_error_type: str | None = None
    last_error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_source_health(
    store: SQLiteStore,
    source_names: list[str],
) -> list[SourceHealth]:
    """Build persisted health summaries from the append-only source run history."""

    store.init_schema()
    names = list(dict.fromkeys(name.strip().lower() for name in source_names if name.strip()))
    if not names:
        return []

    placeholders = ",".join("?" for _ in names)
    with store.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                source,
                status,
                jobs_seen,
                jobs_inserted,
                jobs_updated,
                companies_created,
                error_type,
                error_message,
                started_at,
                finished_at
            FROM source_runs
            WHERE source IN ({placeholders})
            ORDER BY source ASC, id DESC
            """,
            tuple(names),
        ).fetchall()

    grouped: dict[str, list[Any]] = {name: [] for name in names}
    for row in rows:
        grouped.setdefault(str(row["source"]), []).append(row)

    result: list[SourceHealth] = []
    for name in names:
        source_rows = grouped.get(name, [])
        if not source_rows:
            result.append(SourceHealth(source=name, state="unexercised"))
            continue

        latest = source_rows[0]
        successful = [row for row in source_rows if row["status"] == "success"]
        failed = [row for row in source_rows if row["status"] == "failed"]
        last_failure = failed[0] if failed else None
        last_success = successful[0] if successful else None
        runs = len(source_rows)
        result.append(
            SourceHealth(
                source=name,
                state=_source_state(latest),
                runs=runs,
                successful_runs=len(successful),
                failed_runs=len(failed),
                success_rate=round(len(successful) / runs, 4),
                jobs_seen=sum(int(row["jobs_seen"] or 0) for row in source_rows),
                jobs_inserted=sum(int(row["jobs_inserted"] or 0) for row in source_rows),
                jobs_updated=sum(int(row["jobs_updated"] or 0) for row in source_rows),
                companies_created=sum(
                    int(row["companies_created"] or 0) for row in source_rows
                ),
                latest_status=str(latest["status"]),
                latest_started_at=latest["started_at"],
                latest_finished_at=latest["finished_at"],
                last_success_at=last_success["finished_at"] if last_success else None,
                last_error_type=last_failure["error_type"] if last_failure else None,
                last_error_message=(
                    last_failure["error_message"] if last_failure else None
                ),
            )
        )

    return result


def _source_state(latest: Any) -> str:
    if latest["status"] == "success":
        return "healthy"

    error_type = str(latest["error_type"] or "").lower()
    error_message = str(latest["error_message"] or "").lower()
    access_markers = (
        "401 unauthorized",
        "403 forbidden",
        "access denied",
        "captcha",
        "robots.txt disallows",
        "robots disallows",
    )
    if error_type == "httpstatuserror" and any(
        marker in error_message for marker in access_markers[:2]
    ):
        return "access_blocked"
    if any(marker in error_message for marker in access_markers[2:]):
        return "access_blocked"
    return "failing"
