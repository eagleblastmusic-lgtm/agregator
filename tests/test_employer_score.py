from pathlib import Path

from agregator.employer_score import rank_companies
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
)
from agregator.storage import SQLiteStore


def _job(source: str, source_id: str, title: str) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title=title,
        company_name="ACME Logistics Sp. z o.o.",
        company_name_source="api.company",
        company_name_confidence=0.97,
        city="Gdańsk",
    )


def test_employer_score_combines_jobs_sources_domain_and_business_channel(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "score.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("a", "1", "A"),
            _job("a", "2", "B"),
            _job("b", "3", "C"),
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="ACME Logistics Sp. z o.o.",
                city="Gdańsk",
                website_url="https://acme.test",
                domain="acme.test",
                website_confidence=0.93,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@acme.test",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.97,
                    evidence=Evidence(
                        url="https://acme.test/partnerzy",
                        text="Kontakt dla partnerów: partnerzy@acme.test",
                        signal="kontakt dla partnerow",
                    ),
                )
            ],
        ),
    )

    ranked = rank_companies(store)

    assert len(ranked) == 1
    result = ranked[0]
    assert result.score == 100
    assert result.job_count == 3
    assert result.source_count == 2
    assert result.green_channels == 1
    assert set(result.signals) == {
        "jobs_3_plus:+25",
        "sources_2_plus:+15",
        "verified_website:+15",
        "explicit_business_page:+20",
        "green_channel:+20",
        "strong_identity:+5",
    }


def test_employer_score_filter_keeps_only_requested_priority(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "filter.sqlite3")
    store.init_schema()
    store.upsert_jobs([_job("a", "1", "A")])

    assert rank_companies(store, min_score=10) == []
    result = rank_companies(store, min_score=5)
    assert len(result) == 1
    assert result[0].score == 5
