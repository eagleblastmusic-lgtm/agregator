from pathlib import Path

from agregator.benchmark_evaluation import evaluate_labeled_benchmark
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


def _seed(store: SQLiteStore) -> tuple[int, int]:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="fixture-a",
                source_id="1",
                url="https://jobs.test/1",
                title="A",
                company_name="ACME Logistics",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdańsk",
            ),
            JobPosting(
                source="fixture-b",
                source_id="2",
                url="https://jobs.test/2",
                title="B",
                company_name="ACME Logistics",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdańsk",
            ),
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="ACME Logistics",
                city="Gdańsk",
                website_url="https://acme.test",
                domain="acme.test",
                website_confidence=0.99,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@acme.test",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.99,
                    evidence=Evidence(
                        url="https://acme.test/partnerzy",
                        text="Kontakt dla partnerów: partnerzy@acme.test",
                        signal="partnerzy",
                    ),
                )
            ],
        ),
    )
    with store.connect() as connection:
        row = connection.execute(
            "SELECT id FROM contact_channels WHERE company_id = ? AND value = ?",
            (company_id, "partnerzy@acme.test"),
        ).fetchone()
    assert row is not None
    return company_id, int(row["id"])


def _write_complete_labels(label_dir: Path, company_id: int, contact_id: int) -> None:
    label_dir.mkdir(parents=True)
    (label_dir / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id\n"
        "fixture-a,1,acme\n"
        "fixture-b,2,acme\n",
        encoding="utf-8",
    )
    (label_dir / "website_resolution_truth.csv").write_text(
        f"company_id,truth_domain\n{company_id},acme.test\n",
        encoding="utf-8",
    )
    (label_dir / "contact_classification_truth.csv").write_text(
        "contact_id,truth_decision,truth_purpose\n"
        f"{contact_id},green,business_partnership\n",
        encoding="utf-8",
    )


def test_evaluate_labeled_benchmark_passes_complete_matching_truth(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "benchmark.sqlite3")
    company_id, contact_id = _seed(store)
    labels = tmp_path / "labels"
    _write_complete_labels(labels, company_id, contact_id)

    result = evaluate_labeled_benchmark(store, labels)

    assert result.evaluated is True
    assert result.passed is True
    assert result.blockers == ()
    assert result.quality_gate is not None
    assert result.quality_gate.passed is True
    assert len(result.quality_gate.checks) == 3


def test_evaluate_labeled_benchmark_refuses_partial_truth(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "benchmark.sqlite3")
    company_id, contact_id = _seed(store)
    labels = tmp_path / "labels"
    _write_complete_labels(labels, company_id, contact_id)
    (labels / "website_resolution_truth.csv").write_text(
        f"company_id,truth_domain\n{company_id},\n",
        encoding="utf-8",
    )

    result = evaluate_labeled_benchmark(store, labels)

    assert result.evaluated is False
    assert result.passed is False
    assert result.quality_gate is None
    assert result.blockers == ("labels_remaining:website_resolution:1",)
