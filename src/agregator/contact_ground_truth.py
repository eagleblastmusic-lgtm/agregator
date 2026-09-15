from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .audit import init_audit_schema
from .models import ChannelKind, ChannelPurpose, Decision
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class ContactGroundTruthLabel:
    contact_id: int
    truth_decision: Decision
    truth_purpose: ChannelPurpose | None = None


@dataclass(frozen=True, slots=True)
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionSliceMetrics:
    matched_rows: int
    decision_accuracy: float
    decision_macro_f1: float
    decision_confusion: dict[str, dict[str, int]]
    decision_by_class: dict[str, ClassMetrics]

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_rows": self.matched_rows,
            "decision_accuracy": self.decision_accuracy,
            "decision_macro_f1": self.decision_macro_f1,
            "decision_confusion": self.decision_confusion,
            "decision_by_class": {
                key: value.to_dict() for key, value in self.decision_by_class.items()
            },
        }


@dataclass(frozen=True, slots=True)
class ContactEvaluation:
    labeled_rows: int
    matched_rows: int
    missing_rows: int
    decision_accuracy: float
    decision_macro_f1: float
    decision_confusion: dict[str, dict[str, int]]
    decision_by_class: dict[str, ClassMetrics]
    decision_by_kind: dict[str, DecisionSliceMetrics]
    purpose_labeled_rows: int
    purpose_accuracy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "labeled_rows": self.labeled_rows,
            "matched_rows": self.matched_rows,
            "missing_rows": self.missing_rows,
            "decision_accuracy": self.decision_accuracy,
            "decision_macro_f1": self.decision_macro_f1,
            "decision_confusion": self.decision_confusion,
            "decision_by_class": {
                key: value.to_dict() for key, value in self.decision_by_class.items()
            },
            "decision_by_kind": {
                key: value.to_dict() for key, value in self.decision_by_kind.items()
            },
            "purpose_labeled_rows": self.purpose_labeled_rows,
            "purpose_accuracy": self.purpose_accuracy,
        }


def load_contact_ground_truth_csv(path: str | Path) -> list[ContactGroundTruthLabel]:
    labels: list[ContactGroundTruthLabel] = []
    seen: set[int] = set()
    valid_decisions = {item.value for item in Decision}
    valid_purposes = {item.value for item in ChannelPurpose}

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"contact_id", "truth_decision"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"contact ground truth CSV missing columns: {missing_text}")

        for line_number, row in enumerate(reader, start=2):
            raw_decision = (row.get("truth_decision") or "").strip().lower()
            if not raw_decision:
                continue
            if raw_decision not in valid_decisions:
                raise ValueError(
                    f"contact ground truth CSV has invalid truth_decision at line {line_number}"
                )

            raw_contact_id = (row.get("contact_id") or "").strip()
            try:
                contact_id = int(raw_contact_id)
            except ValueError as exc:
                raise ValueError(
                    f"contact ground truth CSV has invalid contact_id at line {line_number}"
                ) from exc
            if contact_id <= 0:
                raise ValueError(
                    f"contact ground truth CSV has invalid contact_id at line {line_number}"
                )
            if contact_id in seen:
                raise ValueError(
                    f"duplicate contact ground truth row at line {line_number}: {contact_id}"
                )
            seen.add(contact_id)

            raw_purpose = (row.get("truth_purpose") or "").strip().lower()
            if raw_purpose and raw_purpose not in valid_purposes:
                raise ValueError(
                    f"contact ground truth CSV has invalid truth_purpose at line {line_number}"
                )

            labels.append(
                ContactGroundTruthLabel(
                    contact_id=contact_id,
                    truth_decision=Decision(raw_decision),
                    truth_purpose=ChannelPurpose(raw_purpose) if raw_purpose else None,
                )
            )
    return labels


def export_contact_ground_truth_template(
    store: SQLiteStore,
    output: str | Path,
    *,
    limit: int = 1000,
) -> Path:
    store.init_schema()
    init_audit_schema(store)
    path = Path(output)
    with store.connect() as connection:
        rows = connection.execute(
            """
            WITH latest_evidence AS (
                SELECT e.*
                FROM contact_evidence_snapshots e
                JOIN (
                    SELECT contact_channel_id, MAX(id) AS latest_id
                    FROM contact_evidence_snapshots
                    GROUP BY contact_channel_id
                ) latest ON latest.latest_id = e.id
            )
            SELECT
                cc.id AS contact_id,
                c.canonical_name,
                cc.kind,
                cc.value,
                cc.decision AS predicted_decision,
                cc.purpose AS predicted_purpose,
                cc.confidence AS predicted_confidence,
                cc.evidence_url,
                cc.evidence_text,
                cc.evidence_signal,
                le.id AS latest_evidence_snapshot_id,
                le.content_sha256 AS evidence_content_sha256,
                le.captured_at AS evidence_captured_at
            FROM contact_channels cc
            JOIN companies c ON c.id = cc.company_id
            LEFT JOIN latest_evidence le ON le.contact_channel_id = cc.id
            ORDER BY
                CASE cc.decision
                    WHEN 'green' THEN 0
                    WHEN 'review' THEN 1
                    ELSE 2
                END,
                cc.confidence DESC,
                cc.id ASC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()

    fieldnames = [
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
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "contact_id": row["contact_id"],
                    "truth_decision": "",
                    "truth_purpose": "",
                    "canonical_name": row["canonical_name"],
                    "kind": row["kind"],
                    "value": row["value"],
                    "predicted_decision": row["predicted_decision"],
                    "predicted_purpose": row["predicted_purpose"],
                    "predicted_confidence": row["predicted_confidence"],
                    "evidence_url": row["evidence_url"],
                    "evidence_text": row["evidence_text"],
                    "evidence_signal": row["evidence_signal"],
                    "latest_evidence_snapshot_id": row["latest_evidence_snapshot_id"],
                    "evidence_content_sha256": row["evidence_content_sha256"],
                    "evidence_captured_at": row["evidence_captured_at"],
                }
            )
    return path


def evaluate_contact_classification(
    store: SQLiteStore,
    labels: list[ContactGroundTruthLabel],
) -> ContactEvaluation:
    store.init_schema()
    predictions: dict[int, tuple[Decision, ChannelPurpose, ChannelKind]] = {}
    with store.connect() as connection:
        for label in labels:
            row = connection.execute(
                "SELECT decision, purpose, kind FROM contact_channels WHERE id = ?",
                (label.contact_id,),
            ).fetchone()
            if row is not None:
                predictions[label.contact_id] = (
                    Decision(str(row["decision"])),
                    ChannelPurpose(str(row["purpose"])),
                    ChannelKind(str(row["kind"])),
                )

    decision_rows: list[tuple[Decision, Decision]] = []
    decision_rows_by_kind: dict[ChannelKind, list[tuple[Decision, Decision]]] = {}
    purpose_labeled_rows = 0
    purpose_correct = 0

    for label in labels:
        predicted = predictions.get(label.contact_id)
        if predicted is None:
            continue
        predicted_decision, predicted_purpose, channel_kind = predicted
        decision_row = (label.truth_decision, predicted_decision)
        decision_rows.append(decision_row)
        decision_rows_by_kind.setdefault(channel_kind, []).append(decision_row)

        if label.truth_purpose is not None:
            purpose_labeled_rows += 1
            if predicted_purpose == label.truth_purpose:
                purpose_correct += 1

    overall = _decision_slice_metrics(decision_rows)
    by_kind = {
        kind.value: _decision_slice_metrics(rows)
        for kind, rows in sorted(decision_rows_by_kind.items(), key=lambda item: item[0].value)
    }

    matched_rows = len(predictions)
    return ContactEvaluation(
        labeled_rows=len(labels),
        matched_rows=matched_rows,
        missing_rows=len(labels) - matched_rows,
        decision_accuracy=overall.decision_accuracy,
        decision_macro_f1=overall.decision_macro_f1,
        decision_confusion=overall.decision_confusion,
        decision_by_class=overall.decision_by_class,
        decision_by_kind=by_kind,
        purpose_labeled_rows=purpose_labeled_rows,
        purpose_accuracy=_safe_ratio(purpose_correct, purpose_labeled_rows),
    )


def evaluate_contact_classification_csv(
    store: SQLiteStore,
    path: str | Path,
) -> ContactEvaluation:
    return evaluate_contact_classification(store, load_contact_ground_truth_csv(path))


def _decision_slice_metrics(
    rows: list[tuple[Decision, Decision]],
) -> DecisionSliceMetrics:
    classes = [item.value for item in Decision]
    confusion = {
        truth: {predicted: 0 for predicted in classes}
        for truth in classes
    }
    correct = 0
    for truth, predicted in rows:
        confusion[truth.value][predicted.value] += 1
        if truth == predicted:
            correct += 1

    by_class: dict[str, ClassMetrics] = {}
    for class_name in classes:
        tp = confusion[class_name][class_name]
        fp = sum(
            confusion[truth][class_name]
            for truth in classes
            if truth != class_name
        )
        fn = sum(
            confusion[class_name][predicted]
            for predicted in classes
            if predicted != class_name
        )
        support = sum(confusion[class_name].values())
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        by_class[class_name] = ClassMetrics(
            precision=precision,
            recall=recall,
            f1=f1,
            support=support,
        )

    active_f1 = [metrics.f1 for metrics in by_class.values() if metrics.support > 0]
    macro_f1 = round(sum(active_f1) / len(active_f1), 4) if active_f1 else 0.0
    return DecisionSliceMetrics(
        matched_rows=len(rows),
        decision_accuracy=_safe_ratio(correct, len(rows)),
        decision_macro_f1=macro_f1,
        decision_confusion=confusion,
        decision_by_class=by_class,
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
