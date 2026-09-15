from pathlib import Path

import pytest

from agregator.label_workflow import LabelKind, next_unlabeled_row, set_row_label


def _write_label_files(directory: Path) -> None:
    directory.mkdir()
    (directory / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id,predicted_company_id,company_name_raw\n"
        "a,1,,10,Alpha\n"
        "a,2,group-2,20,Beta\n",
        encoding="utf-8-sig",
    )
    (directory / "website_resolution_truth.csv").write_text(
        "company_id,truth_domain,predicted_domain,canonical_name\n"
        "10,,www.alpha.example,Alpha\n"
        "20,,,Beta\n",
        encoding="utf-8-sig",
    )
    (directory / "contact_classification_truth.csv").write_text(
        "contact_id,truth_decision,truth_purpose,predicted_decision,predicted_purpose,value\n"
        "1,,,green,business_partnership,partnerzy@alpha.example\n"
        "2,review,,review,generic,kontakt@beta.example\n",
        encoding="utf-8-sig",
    )


def test_next_unlabeled_row_returns_stable_data_row_number(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    row = next_unlabeled_row(labels, LabelKind.COMPANY_RESOLUTION)

    assert row is not None
    assert row.row_number == 1
    assert row.label_field == "truth_company_id"
    assert row.row["predicted_company_id"] == "10"


def test_accept_predicted_company_and_refuse_accidental_overwrite(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.COMPANY_RESOLUTION,
        1,
        accept_predicted=True,
    )

    assert update.new_value == "10"
    assert update.remaining_rows == 0
    assert next_unlabeled_row(labels, LabelKind.COMPANY_RESOLUTION) is None

    with pytest.raises(ValueError, match="already labeled"):
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            1,
            value="other-company",
        )


def test_website_accept_predicted_normalizes_host_and_none(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    first = set_row_label(
        labels,
        LabelKind.WEBSITE_RESOLUTION,
        1,
        accept_predicted=True,
    )
    second = set_row_label(
        labels,
        LabelKind.WEBSITE_RESOLUTION,
        2,
        accept_predicted=True,
    )

    assert first.new_value == "alpha.example"
    assert second.new_value == "__none__"
    assert second.remaining_rows == 0


def test_contact_accept_predicted_copies_decision_and_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        1,
        accept_predicted=True,
    )

    assert update.new_value == "green"
    assert update.purpose_value == "business_partnership"
    text = (labels / "contact_classification_truth.csv").read_text(encoding="utf-8-sig")
    assert "1,green,business_partnership,green,business_partnership" in text


def test_explicit_contact_label_validates_decision_and_purpose(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    update = set_row_label(
        labels,
        LabelKind.CONTACT_CLASSIFICATION,
        1,
        value="review",
        purpose="generic",
    )
    assert update.new_value == "review"
    assert update.purpose_value == "generic"

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
    assert "2,__exclude__,,review,generic" in text


def test_label_modes_are_mutually_exclusive(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write_label_files(labels)

    with pytest.raises(ValueError, match="exactly one labeling mode"):
        set_row_label(
            labels,
            LabelKind.COMPANY_RESOLUTION,
            1,
            value="truth-a",
            accept_predicted=True,
        )
