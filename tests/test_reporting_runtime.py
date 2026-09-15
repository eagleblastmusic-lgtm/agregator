from pathlib import Path

from agregator.reporting import build_benchmark_report
from agregator.storage import SQLiteStore, UpsertStats


def test_benchmark_report_includes_source_run_health(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "runtime.sqlite3")
    store.init_schema()

    success_run = store.start_source_run(
        "olx",
        cursor_before=None,
        pages_requested=2,
    )
    store.finish_source_run(
        success_run,
        status="success",
        cursor_after="40",
        pages_processed=2,
        stats=UpsertStats(
            jobs_seen=20,
            jobs_inserted=18,
            jobs_updated=2,
            companies_created=10,
        ),
    )

    failed_run = store.start_source_run(
        "olx",
        cursor_before="40",
        pages_requested=1,
    )
    store.finish_source_run(
        failed_run,
        status="failed",
        cursor_after="40",
        pages_processed=0,
        stats=UpsertStats(),
        error=RuntimeError("boom"),
    )

    report = build_benchmark_report(store)
    metrics = report.source_run_metrics["olx"]

    assert metrics["runs_total"] == 2
    assert metrics["successful_runs"] == 1
    assert metrics["failed_runs"] == 1
    assert metrics["success_rate"] == 0.5
    assert metrics["pages_processed"] == 2
    assert metrics["jobs_seen"] == 20
    assert metrics["jobs_inserted"] == 18
    assert metrics["jobs_updated"] == 2
    assert metrics["companies_created"] == 10
    assert metrics["avg_seconds_per_run"] >= 0.0
    assert metrics["seconds_per_job_seen"] >= 0.0
