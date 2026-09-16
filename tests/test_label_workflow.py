from pathlib import Path

import pytest

from agregator.label_workflow import (
    LabelKind,
    next_unlabeled_row,
    prediction_reference_row,
    set_row_label,
)


def _write_label_files(directory: Path) -> None:
    directory.mkdir()
    (directory / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id,company_name_raw,city,url\n"
        "a,1,,Alpha,Gdańsk,https://jobs.test/1\n"
        "a,2,group-2,Beta,Gdynia,https://jobs.test/2\n",
        encoding="utf-8-sig",
    )
    (directory / "website_resolution_truth.csv").write_text(
        "company_id,truth_domain,canonical_name,city,job_count,sources\n"
        "10,,Alpha,Gdańsk,2,a\n"
        "20,,Beta,Gdynia,1,b\n",
        encoding="utf-8-sig",
    )
    (directory / "contact_classification_truth.csv").write_text(
        "contact_id,truth_decision,truth_purpose,canonical_name,kind,value,"
        "evidence_url,evidence_text,latest_evidence_snapshot_id,"
        "evidence_content_sha256,evidence_captured_at\n"
        "1,,,Alpha,email,partnerzy@alpha.example,https://alpha.example/partnerzy,"
        "Kontakt dla partnerów: partnerzy@alpha.example,1,abc,2026-09-15\n"
        "2,review,,Beta,email,kontakt@beta.example,https://beta.example/kontakt,"
        "Kontakt: kontakt@beta.example,2,def,2026-09-15\n",
        encoding="utf-8-sig",
    )


def _write_prediction_references(directory: Path) -> None:
    reference = directory / "prediction_reference"
    reference.mkdir()
    (reference / "company_resolution_reference.csv").write_text(
        "source,source_id,truth_company_id,company_name_raw,city,url,"
        "predicted_company_id,company_resolution_method,company_resolution_confidence\n"
        "a,1,,Alpha,Gdańsk,https://jobs.test/1,10,exact_name_city,0.99\n"
        "a,2,,Beta,Gdynia,https://jobs.test/2,20,new_company,0.99\n",
        encoding="utf-8-sig",
    )
    (reference / "website_resolution_reference.csv").write_text(
        "company_id,truth_domain,canonical_name,city,job_count,sources,"
        "predicted_domain,predicted_website_url,website_confidence\n"
        "10,,Alpha,Gdańsk,2,a,alpha.example,https://alpha.example,0.98\n"
        "20,,Beta,Gdynia,1,b,, ,0.20\n",
        encoding="utf-8-sig",
    )
    (reference / "contact_classification_reference.csv").write_text(
        "contact_id,truth_decision,truth_purpose,canonical_name,kind,value,"
        "evidence_url,evidence_text,latest_evidence_snapshot_id,"
        "evidence_content_sha256,evidence_captured_at,predicted_decision,"
        "predicted_purpose,predicted_confidence,evidence_signal\n"
        "1,,,Alpha,email,partnerzy@alpha.example,https://alpha.example/partnerzy,"
        "Kontakt dla partnerów: partnerzy@alpha.example,1,abc,2026-09-15,"
        "green,business_partnership,0.99,partnerzy\n"
        "2,,,Beta,email,kontakt@beta.example,https://beta.example/kontakt,"
        "Kontakt: kontakt@beta.example,2,def,2026-09-15,review,generic,0.65,kontakt\n",
        encoding="utf-8-sig",
    )


def test_next_unlabeled_row_returns_only_blind_primary_context(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    row = next_unlabeled_row(labels, LabelKind.COMPANY_RESOLUTION)

    assert row is not None
    assert row.row_number == 1
    assert row.label_field == "truth_company_id"
    assert row.row["company_name_raw"] == "Alpha"
    assert "predicted_company_id" not in row.row


def test_explicit_company_label_and_refuse_accidental_overwrite(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.COMPANY_RESOLUTION,
        1,
        value="truth-alpha",
    )

    assert update.new_value == "truth-alpha"
    assert update.remaining_rows == 0
    assert next_unlabeled_row(labels, LabelKind.COMPANY_RESOLUTION) is None

    with pytest.raises(ValueError, match="already labeled"):
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            1,
            value="other-company",
        )


def test_website_label_normalizes_host_and_supports_explicit_none(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    first = set_row_label(
        labels,
        LabelKind.WEBSITE_RESOLUTION,
        1,
        value="https://www.alpha.example/kontakt",
    )
    second = set_row_label(
        labels,
        LabelKind.WEBSITE_RESOLUTION,
        2,
        value="__none__",
    )

    assert first.new_value == "alpha.example"
    assert second.new_value == "__none__"
    assert second.remaining_rows == 0


def test_explicit_contact_label_validates_decision_and_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        1,
        value="green",
        purpose="business_partnership",
    )
    assert update.new_value == "green"
    assert update.purpose_value == "business_partnership"

    with pytest.raises(ValueError, match="invalid contact truth decision"):
        set_row_label(
            labels,
            LabelKind.CONTACT_CLASSIFICATION,
            2,
            value="maybe",
            overwrite=True,
        )


def test_exclude_is_explicit_and_clears_contact_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        2,
        exclude=True,
        overwrite=True,
    )

    assert update.new_value == "__exclude__"
    assert update.purpose_value is None
    text = (labels / "contact_classification_truth.csv").read_text(encoding="utf-8-sig")
    assert "2,__exclude__,,Beta,email,kontakt@beta.example" in text


def test_exclude_sentinel_requires_explicit_flag(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    with pytest.raises(ValueError, match="use exclude=True"):
        set_row_label(
            labels,
            LabelKind.WEBSITE_RESOLUTION,
            1,
            value="__exclude__",
        )


def test_exclude_rejects_contact_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    with pytest.raises(ValueError, match="purpose cannot be combined"):
        set_row_label(
            labels,
            LabelKind.CONTACT_CLASSIFICATION,
            1,
            exclude=True,
            purpose="generic",
        )


def test_label_modes_are_mutually_exclusive(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    with pytest.raises(ValueError, match="exactly one labeling mode"):
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            1,
            value="truth-a",
            exclude=True,
        )


def test_company_label_rejects_website_none_sentinel(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    with pytest.raises(ValueError, match="not valid for company_resolution"):
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            1,
            value="__none__",
        )


def test_prediction_reference_is_blocked_before_independent_label(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)
    _write_prediction_references(labels)

    with pytest.raises(ValueError, match="must be independently labeled"):
        prediction_reference_row(labels, LabelKind.COMPANY_RESOLUTION, 1)


def test_prediction_reference_opens_after_truth_and_preserves_prediction(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)
    _write_prediction_references(labels)
    set_row_label(
        labels,
        LabelKind.COMPANY_RESOLUTION,
        1,
        value="truth-alpha",
    )

    reference = prediction_reference_row(labels, LabelKind.COMPANY_RESOLUTION, 1)

    assert reference.truth_value == "truth-alpha"
    assert reference.truth_purpose is None
    assert reference.prediction["predicted_company_id"] == "10"
    assert reference.prediction["company_resolution_method"] == "exact_name_city"
    assert reference.reference_path.name == "company_resolution_reference.csv"


def test_prediction_reference_returns_contact_truth_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)
    _write_prediction_references(labels)
    set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        1,
        value="review",
        purpose="generic",
    )

    reference = prediction_reference_row(labels, LabelKind.CONTACT_CLASSIFICATION, 1)

    assert reference.truth_value == "review"
    assert reference.truth_purpose == "generic"
    assert reference.prediction["predicted_decision"] == "green"
    assert reference.prediction["predicted_purpose"] == "business_partnership"


def test_prediction_reference_detects_reference_alignment_drift(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)
    _write_prediction_references(labels)
    set_row_label(
        labels,
        LabelKind.COMPANY_RESOLUTION,
        1,
        value="truth-alpha",
    )

    reference_path = labels / "prediction_reference" / "company_resolution_reference.csv"
    text = reference_path.read_text(encoding="utf-8-sig")
    reference_path.write_text(
        text.replace("a,1,,Alpha", "a,999,,Alpha", 1),
        encoding="utf-8-sig",
    )

    with pytest.raises(ValueError, match="prediction reference misalignment"):
        prediction_reference_row(labels, LabelKind.COMPANY_RESOLUTION, 1)
