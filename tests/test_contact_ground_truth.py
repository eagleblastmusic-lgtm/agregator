from pathlib import Path

import pytest

from agregator.contact_ground_truth import (
    ContactGroundTruthLabel,
    evaluate_contact_classification,
    evaluate_contact_classification_csv,
    export_contact_ground_truth_template,
    load_contact_ground_truth_csv,
)
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


def _channel(
    value: str,
    purpose: ChannelPurpose,
    decision: Decision,
    confidence: float,
    *,
    kind: ChannelKind = ChannelKind.EMAIL,
) -> ContactChannel:
    return ContactChannel(
        kind=kind,
        value=value,
        purpose=purpose,
        decision=decision,
        confidence=confidence,
        evidence=Evidence(
            url="https://firma.test/kontakt",
            text=f"Kontakt: {value}",
            signal=purpose.value,
        ),
    )


def _seed(store: SQLiteStore) -> dict[str, int]:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="a",
                source_id="1",
                url="https://jobs.test/1",
                title="Test",
                company_name="Firma Testowa",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdynia",
            )
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="Firma Testowa",
                city="Gdynia",
                website_url="https://firma.test",
                domain="firma.test",
                website_confidence=0.9,
            ),
            channels=[
                _channel(
                    "partnerzy@firma.test",
                    ChannelPurpose.BUSINESS_PARTNERSHIP,
                    Decision.GREEN,
                    0.98,
                ),
                _channel(
                    "kontakt@firma.test",
                    ChannelPurpose.GENERIC,
                    Decision.REVIEW,
                    0.50,
                ),
                _channel(
                    "rodo@firma.test",
                    ChannelPurpose.PRIVACY,
                    Decision.IGNORE,
                    0.99,
                ),
                _channel(
                    "https://firma.test/partnerzy",
                    ChannelPurpose.BUSINESS_PARTNERSHIP,
                    Decision.GREEN,
                    0.95,
                    kind=ChannelKind.FORM,
                ),
            ],
        ),
    )
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT id, value FROM contact_channels ORDER BY id"
        ).fetchall()
    return {str(row["value"]): int(row["id"]) for row in rows}


def test_contact_evaluation_reports_confusion_and_macro_f1(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "contacts.sqlite3")
    ids = _seed(store)

    report = evaluate_contact_classification(
        store,
        [
            ContactGroundTruthLabel(
                ids["partnerzy@firma.test"],
                Decision.GREEN,
                ChannelPurpose.BUSINESS_PARTNERSHIP,
            ),
            ContactGroundTruthLabel(
                ids["kontakt@firma.test"],
                Decision.GREEN,
                None,
            ),
            ContactGroundTruthLabel(
                ids["rodo@firma.test"],
                Decision.IGNORE,
                ChannelPurpose.PRIVACY,
            ),
        ],
    )

    assert report.labeled_rows == 3
    assert report.matched_rows == 3
    assert report.decision_accuracy == 0.6667
    assert report.decision_macro_f1 == 0.8334
    assert report.decision_confusion["green"]["green"] == 1
    assert report.decision_confusion["green"]["review"] == 1
    assert report.decision_by_class["green"].recall == 0.5
    assert report.decision_by_kind["email"].matched_rows == 3
    assert report.decision_by_kind["email"].decision_macro_f1 == 0.8334
    assert "form" not in report.decision_by_kind
    assert report.purpose_labeled_rows == 2
    assert report.purpose_accuracy == 1.0
    assert report.excluded_rows == 0


def test_contact_evaluation_reports_metrics_separately_by_kind(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "contact-kinds.sqlite3")
    ids = _seed(store)

    report = evaluate_contact_classification(
        store,
        [
            ContactGroundTruthLabel(ids["partnerzy@firma.test"], Decision.GREEN),
            ContactGroundTruthLabel(ids["kontakt@firma.test"], Decision.REVIEW),
            ContactGroundTruthLabel(ids["rodo@firma.test"], Decision.IGNORE),
            ContactGroundTruthLabel(ids["https://firma.test/partnerzy"], Decision.GREEN),
        ],
    )

    assert report.decision_accuracy == 1.0
    assert report.decision_by_kind["email"].matched_rows == 3
    assert report.decision_by_kind["email"].decision_accuracy == 1.0
    assert report.decision_by_kind["email"].decision_macro_f1 == 1.0
    assert report.decision_by_kind["form"].matched_rows == 1
    assert report.decision_by_kind["form"].decision_accuracy == 1.0
    assert report.decision_by_kind["form"].decision_macro_f1 == 1.0


def test_contact_ground_truth_template_and_loader(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "template.sqlite3")
    _seed(store)

    output = export_contact_ground_truth_template(store, tmp_path / "contact_truth.csv")
    text = output.read_text(encoding="utf-8-sig")
    assert "truth_decision" in text
    assert "predicted_decision" in text
    assert "partnerzy@firma.test" in text

    labeled = tmp_path / "labeled.csv"
    labeled.write_text(
        "contact_id,truth_decision,truth_purpose\n"
        "1,green,business_partnership\n"
        "2,review,\n"
        "3,,\n",
        encoding="utf-8",
    )
    labels = load_contact_ground_truth_csv(labeled)
    assert len(labels) == 2
    assert labels[0].truth_decision == Decision.GREEN
    assert labels[0].truth_purpose == ChannelPurpose.BUSINESS_PARTNERSHIP

    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "contact_id,truth_decision\n1,maybe\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid truth_decision"):
        load_contact_ground_truth_csv(invalid)


def test_contact_ground_truth_exclusion_is_omitted_from_scoring(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "excluded.sqlite3")
    ids = _seed(store)
    truth = tmp_path / "excluded_truth.csv"
    truth.write_text(
        "contact_id,truth_decision,truth_purpose\n"
        f"{ids['partnerzy@firma.test']},green,business_partnership\n"
        f"{ids['kontakt@firma.test']},__exclude__,\n"
        f"{ids['rodo@firma.test']},ignore,privacy\n",
        encoding="utf-8",
    )

    labels = load_contact_ground_truth_csv(truth)
    report = evaluate_contact_classification_csv(store, truth)

    assert len(labels) == 2
    assert [label.truth_decision for label in labels] == [Decision.GREEN, Decision.IGNORE]
    assert report.labeled_rows == 2
    assert report.excluded_rows == 1
    assert report.matched_rows == 2
    assert report.decision_accuracy == 1.0
    assert report.decision_macro_f1 == 1.0
