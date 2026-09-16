from pathlib import Path

import pytest

from agregator.ingest import ingest_source
from agregator.models import CompanyIdentifier, JobPosting
from agregator.sources.base import SourceBatch
from agregator.storage import SQLiteStore


class _PwCSource:
    name = "karierawfinansach"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        profile = CompanyIdentifier(
            kind="karierawfinansach_employer_profile",
            value="https://www.karierawfinansach.pl/pracodawca/pwc",
            source="karierawfinansach.detail.employer_profile",
            confidence=0.99,
        )
        return SourceBatch(
            jobs=[
                JobPosting(
                    source=self.name,
                    source_id="pwc-1",
                    url="https://www.karierawfinansach.pl/oferta-pracy/1,pwc",
                    title="Konsultant",
                    company_name="PwC",
                    company_name_source="html.selector",
                    company_name_confidence=0.80,
                    company_identifiers=[profile],
                ),
                JobPosting(
                    source=self.name,
                    source_id="pwc-2",
                    url="https://www.karierawfinansach.pl/oferta-pracy/2,pwc",
                    title="Audytor",
                    company_name="PwC",
                    company_name_source="html.selector",
                    company_name_confidence=0.80,
                    company_identifiers=[profile],
                ),
            ],
            next_cursor=None,
        )


@pytest.mark.asyncio
async def test_ingest_uses_identifier_aware_company_key_without_changing_caller_store(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "ingest.sqlite3")

    result = await ingest_source(_PwCSource(), store, pages=1, resume=False)

    companies = store.list_companies()
    assert result.stats.jobs_seen == 2
    assert result.stats.jobs_inserted == 2
    assert result.stats.companies_created == 1
    assert len(companies) == 1
    assert companies[0]["canonical_name"] == "PwC"
    assert companies[0]["job_count"] == 2

    with store.connect() as connection:
        observations = connection.execute(
            "SELECT COUNT(*) FROM job_posting_observations"
        ).fetchone()[0]
        identifiers = connection.execute(
            "SELECT COUNT(*) FROM company_identifiers"
        ).fetchone()[0]

    assert observations == 2
    assert identifiers == 1
