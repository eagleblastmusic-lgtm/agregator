from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import init_audit_schema
from .audit_export import WebsiteSnapshotExportResult, export_website_page_snapshots
from .company_identifiers import init_company_identifier_schema
from .company_websites import init_company_website_candidate_schema
from .employer_score import rank_companies
from .storage import SQLiteStore

EXPORT_SCHEMA_VERSION = "7"


@dataclass(frozen=True, slots=True)
class DatasetExportResult:
    output_dir: Path
    companies_path: Path
    jobs_path: Path
    identifiers_path: Path
    website_candidates_path: Path
    contacts_path: Path
    website_verifications_path: Path
    evidence_snapshots_path: Path
    evidence_observations_path: Path
    website_snapshots: WebsiteSnapshotExportResult
    manifest_path: Path
    companies: int
    jobs: int
    identifiers: int
    website_candidates: int
    contacts: int
    website_verifications: int
    evidence_snapshots: int
    evidence_observations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "companies_path": str(self.companies_path),
            "jobs_path": str(self.jobs_path),
            "identifiers_path": str(self.identifiers_path),
            "website_candidates_path": str(self.website_candidates_path),
            "contacts_path": str(self.contacts_path),
            "website_verifications_path": str(self.website_verifications_path),
            "evidence_snapshots_path": str(self.evidence_snapshots_path),
            "evidence_observations_path": str(self.evidence_observations_path),
            "website_snapshots": self.website_snapshots.to_dict(),
            "manifest_path": str(self.manifest_path),
            "companies": self.companies,
            "jobs": self.jobs,
            "identifiers": self.identifiers,
            "website_candidates": self.website_candidates,
            "contacts": self.contacts,
            "website_verifications": self.website_verifications,
            "evidence_snapshots": self.evidence_snapshots,
            "evidence_observations": self.evidence_observations,
            "schema_version": EXPORT_SCHEMA_VERSION,
        }


def export_dataset_bundle(
    store: SQLiteStore,
    output_dir: str | Path,
) -> DatasetExportResult:
    """Export normalized current state plus immutable audit evidence for Faro."""

    store.init_schema()
    init_audit_schema(store)
    init_company_identifier_schema(store)
    init_company_website_candidate_schema(store)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    companies_path = directory / "companies.csv"
    jobs_path = directory / "job_postings.csv"
    identifiers_path = directory / "company_identifiers.csv"
    website_candidates_path = directory / "company_website_candidates.csv"
    contacts_path = directory / "contact_channels.csv"
    website_verifications_path = directory / "website_verification_runs.csv"
    evidence_snapshots_path = directory / "contact_evidence_snapshots.csv"
    evidence_observations_path = directory / "contact_evidence_observations.csv"
    website_snapshots_path = directory / "website_page_snapshots.csv"
    manifest_path = directory / "manifest.json"

    score_by_company = {
        item.company_id: item for item in rank_companies(store, min_score=0, limit=1_000_000)
    }

    with store.connect() as connection:
        companies = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    c.id AS company_id,
                    c.canonical_name,
                    c.normalized_name,
                    c.city AS primary_city,
                    c.normalized_city AS primary_normalized_city,
                    c.identity_source,
                    c.identity_confidence,
                    c.website_url,
                    c.website_confidence,
                    c.enriched_at,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT GROUP_CONCAT(alias, ' | ')
                        FROM company_aliases ca
                        WHERE ca.company_id = c.id
                    ) AS aliases,
                    (
                        SELECT GROUP_CONCAT(city, ' | ')
                        FROM company_locations cl
                        WHERE cl.company_id = c.id
                    ) AS locations,
                    COUNT(DISTINCT j.id) AS job_count,
                    GROUP_CONCAT(DISTINCT j.source) AS job_sources
                FROM companies c
                LEFT JOIN job_postings j ON j.company_id = c.id
                GROUP BY c.id
                ORDER BY c.id ASC
                """
            ).fetchall()
        ]
        jobs = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    j.id AS job_id,
                    j.source,
                    j.source_id,
                    j.url,
                    j.title,
                    j.company_id,
                    j.company_name_raw,
                    j.company_name_source,
                    j.company_name_confidence,
                    j.company_resolution_method,
                    j.company_resolution_confidence,
                    j.city,
                    j.description,
                    j.published_at,
                    j.refreshed_at,
                    j.first_seen_at,
                    j.last_seen_at
                FROM job_postings j
                ORDER BY j.id ASC
                """
            ).fetchall()
        ]
        identifiers = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    ci.id AS identifier_id,
                    ci.company_id,
                    c.canonical_name,
                    ci.kind,
                    ci.value,
                    ci.source,
                    ci.confidence,
                    ci.observation_count,
                    ci.first_seen_at,
                    ci.last_seen_at
                FROM company_identifiers ci
                JOIN companies c ON c.id = ci.company_id
                ORDER BY ci.id ASC
                """
            ).fetchall()
        ]
        website_candidates = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    cwc.id AS website_candidate_id,
                    cwc.company_id,
                    c.canonical_name,
                    cwc.url,
                    cwc.host,
                    cwc.source,
                    cwc.confidence,
                    cwc.observation_count,
                    cwc.first_seen_at,
                    cwc.last_seen_at
                FROM company_website_candidates cwc
                JOIN companies c ON c.id = cwc.company_id
                ORDER BY cwc.id ASC
                """
            ).fetchall()
        ]
        contacts = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    cc.id AS contact_id,
                    cc.company_id,
                    c.canonical_name,
                    cc.kind,
                    cc.value,
                    cc.purpose,
                    cc.decision,
                    cc.confidence,
                    cc.evidence_url,
                    cc.evidence_text,
                    cc.evidence_signal,
                    cc.verified_at
                FROM contact_channels cc
                JOIN companies c ON c.id = cc.company_id
                ORDER BY cc.id ASC
                """
            ).fetchall()
        ]
        website_verifications = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    w.id AS verification_id,
                    w.company_id,
                    c.canonical_name,
                    w.outcome,
                    w.website_url,
                    w.website_confidence,
                    w.resolution_origin,
                    w.resolution_source,
                    w.verification_signals_json,
                    w.search_candidates_json,
                    w.website_attempts_json,
                    w.scanned_pages_json,
                    w.captured_at
                FROM website_verification_runs w
                JOIN companies c ON c.id = w.company_id
                ORDER BY w.id ASC
                """
            ).fetchall()
        ]
        evidence_snapshots = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    e.id AS snapshot_id,
                    e.contact_channel_id,
                    e.company_id,
                    c.canonical_name,
                    e.evidence_url,
                    e.evidence_text,
                    e.evidence_signal,
                    e.content_sha256,
                    e.captured_at
                FROM contact_evidence_snapshots e
                JOIN companies c ON c.id = e.company_id
                ORDER BY e.id ASC
                """
            ).fetchall()
        ]
        evidence_observations = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    o.id AS observation_id,
                    o.website_verification_run_id,
                    o.contact_channel_id,
                    o.company_id,
                    c.canonical_name,
                    o.snapshot_id,
                    s.content_sha256,
                    o.decision,
                    o.purpose,
                    o.confidence,
                    o.evidence_url,
                    o.evidence_signal,
                    o.snapshot_changed,
                    o.captured_at
                FROM contact_evidence_observations o
                JOIN companies c ON c.id = o.company_id
                JOIN contact_evidence_snapshots s ON s.id = o.snapshot_id
                ORDER BY o.id ASC
                """
            ).fetchall()
        ]

    for company in companies:
        score = score_by_company.get(int(company["company_id"]))
        company["employer_discovery_score"] = score.score if score else 0
        company["employer_discovery_signals"] = (
            " | ".join(score.signals) if score else ""
        )

    _write_csv(companies_path, companies, _company_fields())
    _write_csv(jobs_path, jobs, _job_fields())
    _write_csv(identifiers_path, identifiers, _identifier_fields())
    _write_csv(
        website_candidates_path,
        website_candidates,
        _website_candidate_fields(),
    )
    _write_csv(contacts_path, contacts, _contact_fields())
    _write_csv(
        website_verifications_path,
        website_verifications,
        _website_verification_fields(),
    )
    _write_csv(
        evidence_snapshots_path,
        evidence_snapshots,
        _evidence_snapshot_fields(),
    )
    _write_csv(
        evidence_observations_path,
        evidence_observations,
        _evidence_observation_fields(),
    )
    website_snapshots = export_website_page_snapshots(store, website_snapshots_path)

    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "files": {
            "companies": companies_path.name,
            "job_postings": jobs_path.name,
            "company_identifiers": identifiers_path.name,
            "company_website_candidates": website_candidates_path.name,
            "contact_channels": contacts_path.name,
            "website_verification_runs": website_verifications_path.name,
            "contact_evidence_snapshots": evidence_snapshots_path.name,
            "contact_evidence_observations": evidence_observations_path.name,
            "website_page_snapshots": website_snapshots.path.name,
        },
        "counts": {
            "companies": len(companies),
            "job_postings": len(jobs),
            "company_identifiers": len(identifiers),
            "company_website_candidates": len(website_candidates),
            "contact_channels": len(contacts),
            "website_verification_runs": len(website_verifications),
            "contact_evidence_snapshots": len(evidence_snapshots),
            "contact_evidence_observations": len(evidence_observations),
            "website_page_snapshots": website_snapshots.rows,
            "website_page_snapshot_parse_errors": website_snapshots.parse_errors,
        },
        "notes": {
            "company_resolution": (
                "company_resolution_method/confidence describe automatic identity resolution"
            ),
            "company_identifiers": (
                "explicit source-provided business identifiers; conflicts never auto-merge"
            ),
            "company_website_candidates": (
                "source-provided website leads with provenance; each requires identity verification"
            ),
            "website_resolution_origin": (
                "structured final origin: source_candidate, search or known_url with provenance"
            ),
            "employer_discovery_score": (
                "0-100 prioritization score; separate from identity/contact confidence"
            ),
            "contact_decision": "green/review/ignore is preserved with evidence provenance",
            "contact_evidence_observations": (
                "append-only per-run timeline linking classification to immutable snapshots; "
                "snapshot_changed marks evidence-content transitions"
            ),
            "website_audit": (
                "website_verification_runs keeps ranked candidates and per-candidate attempts"
            ),
            "website_page_snapshots": (
                "flattened immutable attempt/final page evidence for offline domain review"
            ),
            "evidence_hash": (
                "contact and page snapshots preserve SHA-256 evidence hashes"
            ),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return DatasetExportResult(
        output_dir=directory,
        companies_path=companies_path,
        jobs_path=jobs_path,
        identifiers_path=identifiers_path,
        website_candidates_path=website_candidates_path,
        contacts_path=contacts_path,
        website_verifications_path=website_verifications_path,
        evidence_snapshots_path=evidence_snapshots_path,
        evidence_observations_path=evidence_observations_path,
        website_snapshots=website_snapshots,
        manifest_path=manifest_path,
        companies=len(companies),
        jobs=len(jobs),
        identifiers=len(identifiers),
        website_candidates=len(website_candidates),
        contacts=len(contacts),
        website_verifications=len(website_verifications),
        evidence_snapshots=len(evidence_snapshots),
        evidence_observations=len(evidence_observations),
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _company_fields() -> list[str]:
    return [
        "company_id",
        "canonical_name",
        "normalized_name",
        "primary_city",
        "primary_normalized_city",
        "aliases",
        "locations",
        "identity_source",
        "identity_confidence",
        "website_url",
        "website_confidence",
        "employer_discovery_score",
        "employer_discovery_signals",
        "job_count",
        "job_sources",
        "enriched_at",
        "created_at",
        "updated_at",
    ]


def _job_fields() -> list[str]:
    return [
        "job_id",
        "source",
        "source_id",
        "url",
        "title",
        "company_id",
        "company_name_raw",
        "company_name_source",
        "company_name_confidence",
        "company_resolution_method",
        "company_resolution_confidence",
        "city",
        "description",
        "published_at",
        "refreshed_at",
        "first_seen_at",
        "last_seen_at",
    ]


def _identifier_fields() -> list[str]:
    return [
        "identifier_id",
        "company_id",
        "canonical_name",
        "kind",
        "value",
        "source",
        "confidence",
        "observation_count",
        "first_seen_at",
        "last_seen_at",
    ]


def _website_candidate_fields() -> list[str]:
    return [
        "website_candidate_id",
        "company_id",
        "canonical_name",
        "url",
        "host",
        "source",
        "confidence",
        "observation_count",
        "first_seen_at",
        "last_seen_at",
    ]


def _contact_fields() -> list[str]:
    return [
        "contact_id",
        "company_id",
        "canonical_name",
        "kind",
        "value",
        "purpose",
        "decision",
        "confidence",
        "evidence_url",
        "evidence_text",
        "evidence_signal",
        "verified_at",
    ]


def _website_verification_fields() -> list[str]:
    return [
        "verification_id",
        "company_id",
        "canonical_name",
        "outcome",
        "website_url",
        "website_confidence",
        "resolution_origin",
        "resolution_source",
        "verification_signals_json",
        "search_candidates_json",
        "website_attempts_json",
        "scanned_pages_json",
        "captured_at",
    ]


def _evidence_snapshot_fields() -> list[str]:
    return [
        "snapshot_id",
        "contact_channel_id",
        "company_id",
        "canonical_name",
        "evidence_url",
        "evidence_text",
        "evidence_signal",
        "content_sha256",
        "captured_at",
    ]


def _evidence_observation_fields() -> list[str]:
    return [
        "observation_id",
        "website_verification_run_id",
        "contact_channel_id",
        "company_id",
        "canonical_name",
        "snapshot_id",
        "content_sha256",
        "decision",
        "purpose",
        "confidence",
        "evidence_url",
        "evidence_signal",
        "snapshot_changed",
        "captured_at",
    ]
