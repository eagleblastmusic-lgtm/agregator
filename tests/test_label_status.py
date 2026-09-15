from pathlib import Path

from agregator.label_status import build_label_bundle_status


def test_label_status_reports_partial_and_complete_bundle(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id\n"
        "a,1,company-1\n"
        "a,2,\n",
        encoding="utf-8",
    )
    (labels / "website_resolution_truth.csv").write_text(
        "company_id,truth_domain\n"
        "1,example.com\n"
        "2,__none__\n",
        encoding="utf-8",
    )
    (labels / "contact_classification_truth.csv").write_text(
        "contact_id,truth_decision,truth_purpose\n"
        "1,green,business_partnership\n"
        "2,review,\n",
        encoding="utf-8",
    )

    partial = build_label_bundle_status(labels)

    assert partial.total_rows == 6
    assert partial.labeled_rows == 5
    assert partial.remaining_rows == 1
    assert partial.completion_rate == 0.8333
    assert partial.ready_for_quality_gate is False
    assert partial.blockers == ("labels_remaining:company_resolution:1",)

    (labels / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id\n"
        "a,1,company-1\n"
        "a,2,company-2\n",
        encoding="utf-8",
    )

    complete = build_label_bundle_status(labels)

    assert complete.total_rows == 6
    assert complete.labeled_rows == 6
    assert complete.remaining_rows == 0
    assert complete.completion_rate == 1.0
    assert complete.ready_for_quality_gate is True
    assert complete.blockers == ()


def test_label_status_reports_missing_and_invalid_files(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "company_resolution_truth.csv").write_text(
        "source,source_id,wrong_column\na,1,x\n",
        encoding="utf-8",
    )

    status = build_label_bundle_status(labels)

    assert status.ready_for_quality_gate is False
    assert "invalid_file:company_resolution:missing_column:truth_company_id" in status.blockers
    assert "missing_file:website_resolution" in status.blockers
    assert "missing_file:contact_classification" in status.blockers
