from pathlib import Path

from agregator.company_identifiers import persist_job_company_identifiers
from agregator.company_websites import persist_job_company_website_candidates
from agregator.models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from agregator.source_provenance import build_source_provenance_metrics
from agregator.storage import SQLiteStore


def _job(
    source: str,
    source_id: str,
    *,
    identifier_source: str,
    website_source: str,
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title="Magazynier",
        company_name="ACME Logistics Sp. z o.o.",
        company_name_source=f"{source}.company",
        company_name_confidence=0.99,
        company_identifiers=[
            CompanyIdentifier(
                kind="nip",
                value="123-456-78-90",
                source=identifier_source,
                confidence=0.99,
            )
        ],
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://www.acme.example",
                source=website_source,
                confidence=0.98,
            )
        ],
        city="Gdańsk",
    )


def _persist_explicit_evidence(store: SQLiteStore, job: JobPosting) -> None:
    store.upsert_jobs([job])
    persist_job_company_identifiers(store, [job])
    persist_job_company_website_candidates(store, [job])


def test_source_provenance_credits_same_company_evidence_to_each_source(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "provenance.sqlite3")
    store.init_schema()
    epraca = _job(
        "epraca",
        "1",
        identifier_source="official_feed.nip",
        website_source="official_feed.adresWww",
    )
    partner = _job(
        "partnerfeed",
        "2",
        identifier_source="partner.nip",
        website_source="partner.website",
    )

    _persist_explicit_evidence(store, epraca)
    _persist_explicit_evidence(store, partner)
    persist_job_company_identifiers(store, [epraca])
    persist_job_company_website_candidates(store, [epraca])

    metrics = build_source_provenance_metrics(store)

    assert set(metrics) == {"epraca", "partnerfeed"}

    epraca_metrics = metrics["epraca"]
    assert epraca_metrics.jobs == 1
    assert epraca_metrics.companies == 1
    assert epraca_metrics.identifier_observations == 2
    assert epraca_metrics.identifiers == 1
    assert epraca_metrics.companies_with_identifiers == 1
    assert epraca_metrics.identifier_company_rate == 1.0
    assert epraca_metrics.identifier_kinds == {"nip": 1}
    assert epraca_metrics.identifier_evidence_sources == {"official_feed.nip": 1}
    assert epraca_metrics.website_candidate_observations == 2
    assert epraca_metrics.website_candidates == 1
    assert epraca_metrics.companies_with_website_candidates == 1
    assert epraca_metrics.website_candidate_company_rate == 1.0
    assert epraca_metrics.website_evidence_sources == {
        "official_feed.adresWww": 1
    }

    partner_metrics = metrics["partnerfeed"]
    assert partner_metrics.jobs == 1
    assert partner_metrics.companies == 1
    assert partner_metrics.identifier_observations == 1
    assert partner_metrics.identifier_evidence_sources == {"partner.nip": 1}
    assert partner_metrics.website_candidate_observations == 1
    assert partner_metrics.website_evidence_sources == {"partner.website": 1}

    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM company_identifiers"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM company_identifier_observations"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM company_website_candidates"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM company_website_candidate_observations"
        ).fetchone()[0] == 2


def test_source_provenance_includes_sources_without_explicit_evidence(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "no-evidence.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="olx",
                source_id="1",
                url="https://jobs.test/olx/1",
                title="Kasjer",
                company_name="Sklep Testowy",
                company_name_source="company.name",
                company_name_confidence=0.98,
                city="Gdynia",
            )
        ]
    )

    metrics = build_source_provenance_metrics(store)["olx"]

    assert metrics.jobs == 1
    assert metrics.companies == 1
    assert metrics.identifier_observations == 0
    assert metrics.identifier_company_rate == 0.0
    assert metrics.website_candidate_observations == 0
    assert metrics.website_candidate_company_rate == 0.0
