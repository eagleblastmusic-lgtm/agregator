from pathlib import Path

import httpx

from agregator.source_health import build_source_health
from agregator.storage import SQLiteStore, UpsertStats


def test_source_health_aggregates_persisted_runs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "health.sqlite3")
    store.init_schema()

    success_stats = UpsertStats(
        jobs_seen=10,
        jobs_inserted=8,
        jobs_updated=2,
        companies_created=4,
    )
    first = store.start_source_run("alpha", cursor_before=None, pages_requested=1)
    store.finish_source_run(
        first,
        status="success",
        cursor_after="page-2",
        pages_processed=1,
        stats=success_stats,
    )

    failure_stats = UpsertStats(jobs_seen=2, jobs_inserted=1)
    second = store.start_source_run("alpha", cursor_before="page-2", pages_requested=1)
    store.finish_source_run(
        second,
        status="failed",
        cursor_after="page-2",
        pages_processed=0,
        stats=failure_stats,
        error=RuntimeError("source changed layout"),
    )

    health = {item.source: item for item in build_source_health(store, ["alpha", "beta"])}

    alpha = health["alpha"]
    assert alpha.state == "failing"
    assert alpha.runs == 2
    assert alpha.successful_runs == 1
    assert alpha.failed_runs == 1
    assert alpha.success_rate == 0.5
    assert alpha.jobs_seen == 12
    assert alpha.jobs_inserted == 9
    assert alpha.jobs_updated == 2
    assert alpha.companies_created == 4
    assert alpha.latest_status == "failed"
    assert alpha.last_success_at is not None
    assert alpha.last_error_type == "RuntimeError"
    assert alpha.last_error_message == "source changed layout"

    beta = health["beta"]
    assert beta.state == "unexercised"
    assert beta.runs == 0
    assert beta.success_rate is None
    assert beta.latest_status is None


def test_source_health_distinguishes_success_with_zero_records(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "empty.sqlite3")
    store.init_schema()
    run_id = store.start_source_run("empty", cursor_before=None, pages_requested=1)
    store.finish_source_run(
        run_id,
        status="success",
        cursor_after=None,
        pages_processed=1,
        stats=UpsertStats(),
    )

    health = build_source_health(store, ["empty"])[0]

    assert health.state == "empty"
    assert health.successful_runs == 1
    assert health.jobs_seen == 0


def _record_http_failure(tmp_path: Path, status_code: int, reason: str) -> str:
    store = SQLiteStore(tmp_path / f"blocked-{status_code}.sqlite3")
    store.init_schema()
    run_id = store.start_source_run("blocked", cursor_before=None, pages_requested=1)
    response = httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://example.test/jobs"),
    )
    error = httpx.HTTPStatusError(
        f"Client error '{status_code} {reason}' for url 'https://example.test/jobs'",
        request=response.request,
        response=response,
    )
    store.finish_source_run(
        run_id,
        status="failed",
        cursor_after=None,
        pages_processed=0,
        stats=UpsertStats(),
        error=error,
    )
    return build_source_health(store, ["blocked"])[0].state


def test_source_health_distinguishes_http_access_block(tmp_path: Path) -> None:
    assert _record_http_failure(tmp_path, 403, "Forbidden") == "access_blocked"


def test_source_health_distinguishes_http_406_access_block(tmp_path: Path) -> None:
    assert _record_http_failure(tmp_path, 406, "Not Acceptable") == "access_blocked"
