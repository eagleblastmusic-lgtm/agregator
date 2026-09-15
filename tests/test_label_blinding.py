import csv
from pathlib import Path

from agregator.label_blinding import blind_quality_label_files


def _write(path: Path, fieldnames: list[str], row: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def test_blind_quality_label_files_hides_predictions_and_preserves_reference(
    tmp_path: Path,
) -> None:
    company = tmp_path / "company_resolution_truth.csv"
    website = tmp_path / "website_resolution_truth.csv"
    contact = tmp_path / "contact_classification_truth.csv"

    _write(
        company,
        [
            "source",
            "source_id",
            "truth_company_id",
            "company_name_raw",
            "city",
            "url",
            "predicted_company_id",
            "company_resolution_method",
            "company_resolution_confidence",
        ],
        {
            "source": "fixture",
            "source_id": "1",
            "truth_company_id": "",
            "company_name_raw": "ACME",
            "city": "Gdańsk",
            "url": "https://jobs.test/1",
            "predicted_company_id": "17",
            "company_resolution_method": "exact_name_city",
            "company_resolution_confidence": "0.99",
        },
    )
    _write(
        website,
        [
            "company_id",
            "truth_domain",
            "canonical_name",
            "city",
            "predicted_website_url",
            "predicted_domain",
            "website_confidence",
            "latest_verification_id",
            "verification_outcome",
            "predicted_resolution_origin",
            "predicted_resolution_source",
            "source_website_candidate_count",
            "verification_signals_json",
            "job_count",
            "sources",
        ],
        {
            "company_id": "17",
            "truth_domain": "",
            "canonical_name": "ACME",
            "city": "Gdańsk",
            "predicted_website_url": "https://acme.test",
            "predicted_domain": "acme.test",
            "website_confidence": "0.97",
            "latest_verification_id": "9",
            "verification_outcome": "verified",
            "predicted_resolution_origin": "search",
            "predicted_resolution_source": "brave",
            "source_website_candidate_count": "0",
            "verification_signals_json": "[]",
            "job_count": "2",
            "sources": "fixture",
        },
    )
    _write(
        contact,
        [
            "contact_id",
            "truth_decision",
            "truth_purpose",
            "canonical_name",
            "kind",
            "value",
            "predicted_decision",
            "predicted_purpose",
            "predicted_confidence",
            "evidence_url",
            "evidence_text",
            "evidence_signal",
            "latest_evidence_snapshot_id",
            "evidence_content_sha256",
            "evidence_captured_at",
        ],
        {
            "contact_id": "5",
            "truth_decision": "",
            "truth_purpose": "",
            "canonical_name": "ACME",
            "kind": "email",
            "value": "partnerzy@acme.test",
            "predicted_decision": "green",
            "predicted_purpose": "business_partnership",
            "predicted_confidence": "0.99",
            "evidence_url": "https://acme.test/partnerzy",
            "evidence_text": "Kontakt dla partnerów",
            "evidence_signal": "partnerzy",
            "latest_evidence_snapshot_id": "12",
            "evidence_content_sha256": "a" * 64,
            "evidence_captured_at": "2026-09-15 10:00:00",
        },
    )

    result = blind_quality_label_files(
        company,
        website,
        contact,
        reference_dir=tmp_path / "prediction_reference",
    )

    company_fields, company_rows = _read(company)
    website_fields, website_rows = _read(website)
    contact_fields, contact_rows = _read(contact)

    assert "predicted_company_id" not in company_fields
    assert company_rows[0]["company_name_raw"] == "ACME"
    assert "predicted_website_url" not in website_fields
    assert website_rows[0]["canonical_name"] == "ACME"
    assert "predicted_decision" not in contact_fields
    assert "evidence_signal" not in contact_fields
    assert contact_rows[0]["evidence_text"] == "Kontakt dla partnerów"

    company_ref_fields, company_ref_rows = _read(
        result.company_resolution_reference_path
    )
    website_ref_fields, website_ref_rows = _read(
        result.website_resolution_reference_path
    )
    contact_ref_fields, contact_ref_rows = _read(
        result.contact_classification_reference_path
    )

    assert "predicted_company_id" in company_ref_fields
    assert company_ref_rows[0]["predicted_company_id"] == "17"
    assert "predicted_website_url" in website_ref_fields
    assert website_ref_rows[0]["predicted_domain"] == "acme.test"
    assert "predicted_decision" in contact_ref_fields
    assert contact_ref_rows[0]["predicted_decision"] == "green"


def test_blinding_rejects_missing_required_context_column(tmp_path: Path) -> None:
    company = tmp_path / "company_resolution_truth.csv"
    website = tmp_path / "website_resolution_truth.csv"
    contact = tmp_path / "contact_classification_truth.csv"
    _write(
        company,
        ["source", "source_id", "truth_company_id"],
        {"source": "a", "source_id": "1", "truth_company_id": ""},
    )
    _write(
        website,
        [
            "company_id",
            "truth_domain",
            "canonical_name",
            "city",
            "job_count",
            "sources",
        ],
        {
            "company_id": "1",
            "truth_domain": "",
            "canonical_name": "ACME",
            "city": "Gdańsk",
            "job_count": "1",
            "sources": "fixture",
        },
    )
    _write(
        contact,
        [
            "contact_id",
            "truth_decision",
            "truth_purpose",
            "canonical_name",
            "kind",
            "value",
            "evidence_url",
            "evidence_text",
            "latest_evidence_snapshot_id",
            "evidence_content_sha256",
            "evidence_captured_at",
        ],
        {
            "contact_id": "1",
            "truth_decision": "",
            "truth_purpose": "",
            "canonical_name": "ACME",
            "kind": "email",
            "value": "a@b.test",
            "evidence_url": "https://b.test",
            "evidence_text": "Kontakt",
            "latest_evidence_snapshot_id": "1",
            "evidence_content_sha256": "a" * 64,
            "evidence_captured_at": "now",
        },
    )

    try:
        blind_quality_label_files(
            company,
            website,
            contact,
            reference_dir=tmp_path / "reference",
        )
    except ValueError as exc:
        assert "company_name_raw" in str(exc)
    else:
        raise AssertionError("expected ValueError")
