from pathlib import Path

import pytest

from agregator.ground_truth import (
    GroundTruthLabel,
    evaluate_company_resolution,
    load_ground_truth_csv,
)
from agregator.models import JobPosting
from agregator.storage import SQLiteStore


def _job(
    source: str,
    source_id: str,
    company_name: str,
    city: str,
    confidence: float = 0.95,
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://jobs.test/{source}/{source_id}",
        title="Test",
        company_name=company_name,
        company_name_source="api.company",
        company_name_confidence=confidence,
        city=city,
    )


def test_pairwise_resolution_metrics_detect_false_negative(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "evaluation.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("a", "1", "ABC", "Gdańsk"),
            _job("b", "2", "ABC", "Warszawa"),
            _job("c", "3", "Inna Firma", "Gdynia"),
        ]
    )

    report = evaluate_company_resolution(
        store,
        [
            GroundTruthLabel("a", "1", "truth-abc"),
            GroundTruthLabel("b", "2", "truth-abc"),
            GroundTruthLabel("c", "3", "truth-other"),
        ],
    )

    assert report.labeled_rows == 3
    assert report.matched_rows == 3
    assert report.evaluated_pairs == 3
    assert report.true_positive == 0
    assert report.false_positive == 0
    assert report.false_negative == 1
    assert report.true_negative == 2
    assert report.precision == 0.0
    assert report.recall == 0.0
    assert report.f1 == 0.0


def test_pairwise_resolution_metrics_for_correct_merge(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "evaluation-correct.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("a", "1", "ACME Logistics", "Gdańsk"),
            _job("b", "2", "ACME Logistics Sp. z o.o.", "Warszawa"),
            _job("c", "3", "Inna Firma", "Gdynia"),
        ]
    )

    report = evaluate_company_resolution(
        store,
        [
            GroundTruthLabel("a", "1", "truth-acme"),
            GroundTruthLabel("b", "2", "truth-acme"),
            GroundTruthLabel("c", "3", "truth-other"),
        ],
    )

    assert report.true_positive == 1
    assert report.false_positive == 0
    assert report.false_negative == 0
    assert report.true_negative == 2
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1 == 1.0


def test_ground_truth_csv_loader_validates_columns_and_duplicates(tmp_path: Path) -> None:
    valid = tmp_path / "truth.csv"
    valid.write_text(
        "source,source_id,truth_company_id\n"
        "olx,1,company-a\n"
        "jooble,2,company-a\n",
        encoding="utf-8",
    )

    labels = load_ground_truth_csv(valid)
    assert len(labels) == 2
    assert labels[0].truth_company_id == "company-a"

    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text(
        "source,source_id,truth_company_id\n"
        "olx,1,company-a\n"
        "olx,1,company-a\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate ground truth job"):
        load_ground_truth_csv(duplicate)

    missing = tmp_path / "missing.csv"
    missing.write_text("source,source_id\nolx,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_ground_truth_csv(missing)
