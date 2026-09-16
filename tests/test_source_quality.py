from pathlib import Path

from agregator.models import JobPosting
from agregator.source_quality import build_source_identity_metrics
from agregator.storage import SQLiteStore


def _job(
    source: str,
    source_id: str,
    *,
    company: str,
    confidence: float,
    city: str | None,
    description: str | None,
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title="Magazynier",
        company_name=company,
        company_name_source="fixture.company",
        company_name_confidence=confidence,
        city=city,
        description=description,
    )


def test_source_identity_metrics_are_computed_per_source(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "quality.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job(
                "olx",
                "1",
                company="Alpha",
                confidence=0.90,
                city="Gdańsk",
                description="Opis",
            ),
            _job(
                "olx",
                "2",
                company="Beta",
                confidence=0.50,
                city=None,
                description=None,
            ),
            _job(
                "jooble",
                "1",
                company="Gamma",
                confidence=0.80,
                city="Gdynia",
                description="Opis",
            ),
        ]
    )

    with store.connect() as connection:
        connection.execute(
            """
            UPDATE job_postings
            SET company_resolution_confidence = 0.8,
                company_resolution_method = 'exact_name_city'
            WHERE source = 'olx' AND source_id = '1'
            """
        )
        connection.execute(
            """
            UPDATE job_postings
            SET company_resolution_confidence = 0.4,
                company_resolution_method = 'new_company'
            WHERE source = 'olx' AND source_id = '2'
            """
        )
        connection.execute(
            """
            UPDATE job_postings
            SET company_resolution_confidence = 0.9,
                company_resolution_method = 'new_company'
            WHERE source = 'jooble' AND source_id = '1'
            """
        )

    metrics = build_source_identity_metrics(store)

    olx = metrics["olx"]
    assert olx.jobs == 2
    assert olx.companies == 2
    assert olx.company_to_job_ratio == 1.0
    assert olx.avg_company_name_confidence == 0.7
    assert olx.avg_company_resolution_confidence == 0.6
    assert olx.company_name_confidence_ge_070_rate == 0.5
    assert olx.resolution_confidence_ge_070_rate == 0.5
    assert olx.city_coverage_rate == 0.5
    assert olx.description_coverage_rate == 0.5
    assert olx.resolution_methods == {"exact_name_city": 1, "new_company": 1}

    jooble = metrics["jooble"]
    assert jooble.jobs == 1
    assert jooble.companies == 1
    assert jooble.avg_company_name_confidence == 0.8
    assert jooble.avg_company_resolution_confidence == 0.9
    assert jooble.company_name_confidence_ge_070_rate == 1.0
    assert jooble.resolution_confidence_ge_070_rate == 1.0
    assert jooble.city_coverage_rate == 1.0
    assert jooble.description_coverage_rate == 1.0
    assert jooble.resolution_methods == {"new_company": 1}


def test_source_identity_metrics_empty_database(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "empty.sqlite3")

    assert build_source_identity_metrics(store) == {}
