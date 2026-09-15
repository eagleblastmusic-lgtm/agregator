import csv
from pathlib import Path

from agregator.benchmark_evaluation import evaluate_labeled_benchmark
from agregator.label_workflow import LabelKind, set_row_label
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
from agregator.quality_labels import export_quality_label_bundle
from agregator.storage import SQLiteStore


def _job(
    source: str,
    source_id: str,
    company: str,
    title: str,
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title=title,
        company_name=company,
        company_name_source="fixture.company",
        company_name_confidence=0.99,
        city="Gdańsk",
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_blind_manual_labels_round_trip_into_passing_quality_gate(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "benchmark.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("olx", "1", "Alpha Sp. z o.o.", "Magazynier"),
            _job("jooble", "2", "Alpha Sp. z o.o.", "Kierowca"),
            _job("olx", "3", "Beta Sp. z o.o.", "Kasjer"),
        ]
    )

    companies = {
        str(row["canonical_name"]): int(row["id"])
        for row in store.list_companies(limit=10)
    }
    alpha_id = companies["Alpha Sp. z o.o."]

    store.save_discovery_result(
        alpha_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="Alpha Sp. z o.o.",
                city="Gdańsk",
                website_url="https://alpha.test",
                domain="alpha.test",
                website_confidence=0.99,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@alpha.test",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.99,
                    evidence=Evidence(
                        url="https://alpha.test/partnerzy",
                        text="Kontakt dla partnerów: partnerzy@alpha.test",
                        signal="kontakt dla partnerow",
                    ),
                )
            ],
        ),
    )

    labels = tmp_path / "labels"
    bundle = export_quality_label_bundle(
        store,
        labels,
        job_limit=10,
        company_limit=10,
        contact_limit=10,
        sampling_seed="roundtrip-test",
    )

    company_rows = _rows(bundle.company_resolution_path)
    assert company_rows
    assert all("predicted_company_id" not in row for row in company_rows)
    for index, row in enumerate(company_rows, start=1):
        truth_id = (
            "truth-alpha"
            if row["company_name_raw"] == "Alpha Sp. z o.o."
            else "truth-beta"
        )
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            index,
            value=truth_id,
        )

    website_rows = _rows(bundle.website_resolution_path)
    assert website_rows
    assert all("predicted_domain" not in row for row in website_rows)
    for index, row in enumerate(website_rows, start=1):
        value = "alpha.test" if row["canonical_name"] == "Alpha Sp. z o.o." else "__none__"
        set_row_label(
            labels,
            LabelKind.WEBSITE_RESOLUTION,
            index,
            value=value,
        )

    contact_rows = _rows(bundle.contact_classification_path)
    assert len(contact_rows) == 1
    assert "predicted_decision" not in contact_rows[0]
    set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        1,
        value="green",
        purpose="business_partnership",
    )

    result = evaluate_labeled_benchmark(
        store,
        labels,
        min_resolution_f1=1.0,
        min_website_f1=1.0,
        min_contact_macro_f1=1.0,
    )

    assert result.evaluated is True
    assert result.passed is True
    assert result.blockers == ()
    assert result.quality_gate is not None
    assert result.quality_gate.reports["company_resolution"]["f1"] == 1.0
    assert result.quality_gate.reports["website_resolution"]["f1"] == 1.0
    assert result.quality_gate.reports["contact_classification"]["decision_macro_f1"] == 1.0
