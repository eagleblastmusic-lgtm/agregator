from pathlib import Path

from agregator.models import JobPosting
from agregator.reporting import build_benchmark_report
from agregator.storage import SQLiteStore


def _job(source: str, source_id: str, title: str) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title=title,
        company_name="ACME Sp. z o.o.",
        company_name_source="fixture.company",
        company_name_confidence=0.99,
        city="Gdańsk",
    )


def test_benchmark_report_exposes_diagnostic_source_overlap(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "report-overlap.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("olx", "1", "Magazynier"),
            _job("olx", "2", "Kasjer"),
            _job("jooble", "1", "MAGAZYNIER"),
        ]
    )

    report = build_benchmark_report(store)

    assert report.source_overlap["unique_job_fingerprints"] == 2
    assert report.source_overlap["cross_source_shared_fingerprints"] == 1
    assert report.source_overlap["cross_source_shared_fingerprint_rate"] == 0.5
    pair = report.source_overlap["pairwise"]["jooble|olx"]
    assert pair["shared_fingerprints"] == 1
    assert pair["union_fingerprints"] == 2
    assert pair["jaccard"] == 0.5
    assert pair["overlap_rate_a"] == 1.0
    assert pair["overlap_rate_b"] == 0.5
