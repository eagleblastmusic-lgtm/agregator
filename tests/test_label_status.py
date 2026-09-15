import json
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
    assert partial.sampling_manifest.exists is False
    assert partial.audit_warnings == ("missing_sampling_manifest",)

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
    assert complete.audit_warnings == ("missing_sampling_manifest",)


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
    assert status.audit_warnings == ("missing_sampling_manifest",)


def test_label_status_surfaces_valid_sampling_manifest_without_blocking_gate(
    tmp_path: Path,
) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id\na,1,company-1\n",
        encoding="utf-8",
    )
    (labels / "website_resolution_truth.csv").write_text(
        "company_id,truth_domain\n1,example.com\n",
        encoding="utf-8",
    )
    (labels / "contact_classification_truth.csv").write_text(
        "contact_id,truth_decision\n1,green\n",
        encoding="utf-8",
    )
    (labels / "sampling_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "seed": "audit-seed",
                "strategy": "deterministic stratified sampling",
                "files": [{"name": "company_resolution", "sampled_rows": 1}],
            }
        ),
        encoding="utf-8",
    )

    status = build_label_bundle_status(labels)

    assert status.ready_for_quality_gate is True
    assert status.audit_warnings == ()
    assert status.sampling_manifest.exists is True
    assert status.sampling_manifest.valid is True
    assert status.sampling_manifest.schema_version == "1"
    assert status.sampling_manifest.seed == "audit-seed"
    assert status.sampling_manifest.file_count == 1


def test_label_status_warns_about_invalid_sampling_manifest(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "sampling_manifest.json").write_text(
        '{"schema_version":"1","seed":""}',
        encoding="utf-8",
    )

    status = build_label_bundle_status(labels)

    assert status.sampling_manifest.exists is True
    assert status.sampling_manifest.valid is False
    assert status.sampling_manifest.error is not None
    assert status.audit_warnings[0].startswith("invalid_sampling_manifest:")
