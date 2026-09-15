import json
from pathlib import Path

from typer.testing import CliRunner

from agregator.benchmark_cli import app
from agregator.company_identifiers import persist_job_company_identifiers
from agregator.company_websites import persist_job_company_website_candidates
from agregator.models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from agregator.storage import SQLiteStore

runner = CliRunner()


def test_source_diagnostics_cli_reports_identity_and_provenance(tmp_path: Path) -> None:
    database = tmp_path / "benchmark.sqlite3"
    store = SQLiteStore(database)
    store.init_schema()
    job = JobPosting(
        source="epraca",
        source_id="1",
        url="https://jobs.test/1",
        title="Magazynier",
        company_name="ACME Logistics",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_identifiers=[
            CompanyIdentifier(
                kind="nip",
                value="1234567890",
                source="official_feed.nip",
                confidence=0.995,
            )
        ],
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://acme.example",
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdańsk",
        description="Opis oferty",
    )
    store.upsert_jobs([job])
    persist_job_company_identifiers(store, [job])
    persist_job_company_website_candidates(store, [job])

    result = runner.invoke(
        app,
        ["source-diagnostics", "--db", str(database)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["identity"]["epraca"]["jobs"] == 1
    assert payload["identity"]["epraca"]["avg_company_name_confidence"] == 0.995
    provenance = payload["provenance"]["epraca"]
    assert provenance["companies_with_identifiers"] == 1
    assert provenance["identifier_company_rate"] == 1.0
    assert provenance["identifier_evidence_sources"] == {"official_feed.nip": 1}
    assert provenance["companies_with_website_candidates"] == 1
    assert provenance["website_candidate_company_rate"] == 1.0
    assert provenance["website_evidence_sources"] == {
        "official_feed.adresWww": 1
    }
