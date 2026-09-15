from pathlib import Path

from agregator.models import JobPosting
from agregator.source_overlap import build_source_overlap_report, job_overlap_fingerprint
from agregator.storage import SQLiteStore


def _job(
    source: str,
    source_id: str,
    *,
    title: str,
    company: str,
    city: str,
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title=title,
        company_name=company,
        company_name_source="fixture.company",
        company_name_confidence=0.99,
        city=city,
    )


def test_job_overlap_fingerprint_normalizes_company_title_and_city() -> None:
    left = job_overlap_fingerprint(
        "ACME Sp. z o.o.",
        "Magazynier / Magazynierka",
        "Gdańsk",
    )
    right = job_overlap_fingerprint(
        "ACME",
        "MAGAZYNIER - MAGAZYNIERKA",
        "GDANSK",
    )

    assert left == right == ("acme", "magazynier magazynierka", "gdansk")
    assert job_overlap_fingerprint("", "Magazynier", "Gdańsk") is None
    assert job_overlap_fingerprint("ACME", "", "Gdańsk") is None


def test_source_overlap_report_measures_pairwise_jaccard_without_double_counting(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "overlap.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job(
                "olx",
                "1",
                title="Magazynier",
                company="ACME Sp. z o.o.",
                city="Gdańsk",
            ),
            _job(
                "olx",
                "2",
                title="Kasjer",
                company="Sklep Testowy",
                city="Gdynia",
            ),
            _job(
                "adzuna",
                "a",
                title="MAGAZYNIER",
                company="ACME",
                city="GDANSK",
            ),
            _job(
                "adzuna",
                "b",
                title="Kierowca",
                company="Transport Test",
                city="Sopot",
            ),
            _job(
                "jooble",
                "j",
                title="Magazynier",
                company="ACME",
                city="Gdańsk",
            ),
        ]
    )

    report = build_source_overlap_report(store)

    assert report.unique_job_fingerprints == 3
    assert report.cross_source_shared_fingerprints == 1
    assert report.cross_source_shared_fingerprint_rate == 0.3333

    assert report.by_source["adzuna"].fingerprints == 2
    assert report.by_source["adzuna"].exclusive_fingerprints == 1
    assert report.by_source["adzuna"].shared_fingerprints == 1
    assert report.by_source["adzuna"].exclusive_rate == 0.5
    assert report.by_source["adzuna"].shared_rate == 0.5
    assert report.by_source["jooble"].exclusive_fingerprints == 0
    assert report.by_source["jooble"].shared_rate == 1.0
    assert report.by_source["olx"].exclusive_fingerprints == 1

    olx_adzuna = report.pairwise["adzuna|olx"]
    assert olx_adzuna.source_a_fingerprints == 2
    assert olx_adzuna.source_b_fingerprints == 2
    assert olx_adzuna.shared_fingerprints == 1
    assert olx_adzuna.union_fingerprints == 3
    assert olx_adzuna.jaccard == 0.3333
    assert olx_adzuna.overlap_rate_a == 0.5
    assert olx_adzuna.overlap_rate_b == 0.5

    adzuna_jooble = report.pairwise["adzuna|jooble"]
    assert adzuna_jooble.shared_fingerprints == 1
    assert adzuna_jooble.jaccard == 0.5
    assert adzuna_jooble.overlap_rate_a == 0.5
    assert adzuna_jooble.overlap_rate_b == 1.0


def test_source_overlap_report_is_empty_for_single_source(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "single.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job(
                "olx",
                "1",
                title="Magazynier",
                company="ACME",
                city="Gdańsk",
            )
        ]
    )

    report = build_source_overlap_report(store)

    assert report.unique_job_fingerprints == 1
    assert report.cross_source_shared_fingerprints == 0
    assert report.cross_source_shared_fingerprint_rate == 0.0
    assert report.by_source["olx"].exclusive_fingerprints == 1
    assert report.by_source["olx"].exclusive_rate == 1.0
    assert report.by_source["olx"].shared_rate == 0.0
    assert report.pairwise == {}
