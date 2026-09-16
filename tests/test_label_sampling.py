import csv
import json
from pathlib import Path

from agregator.label_sampling import sample_quality_label_files, write_sampling_manifest
from agregator.models import JobPosting
from agregator.quality_labels import export_quality_label_bundle
from agregator.storage import SQLiteStore


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _seed_label_files(directory: Path) -> tuple[Path, Path, Path]:
    company_path = directory / "company_resolution_truth.csv"
    website_path = directory / "website_resolution_truth.csv"
    contact_path = directory / "contact_classification_truth.csv"

    company_rows: list[dict[str, object]] = []
    for index in range(16):
        company_rows.append(
            {
                "source": "olx" if index % 2 == 0 else "jooble",
                "source_id": f"job-{index}",
                "truth_company_id": "",
                "company_name_raw": f"Firma {index // 2}",
                "city": "Gdańsk",
                "url": f"https://jobs.test/{index}",
                "predicted_company_id": str(index // 2),
                "company_resolution_method": (
                    "exact_name_city" if index % 4 < 2 else "new_company"
                ),
                "company_resolution_confidence": (
                    "0.97" if index % 4 < 2 else "0.72"
                ),
            }
        )
    _write_csv(
        company_path,
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
        company_rows,
    )

    website_rows: list[dict[str, object]] = []
    website_strata = [
        ("source_candidate", "verified", "0.98", 1),
        ("search", "verified", "0.86", 0),
        ("", "no_verified_website", "0.00", 0),
    ]
    for index in range(12):
        origin, outcome, confidence, source_candidates = website_strata[index % 3]
        website_rows.append(
            {
                "company_id": str(index + 1),
                "truth_domain": "",
                "canonical_name": f"Firma {index + 1}",
                "city": "Gdynia",
                "predicted_website_url": "https://firma.test" if origin else "",
                "predicted_domain": "firma.test" if origin else "",
                "website_confidence": confidence,
                "latest_verification_id": str(index + 100),
                "verification_outcome": outcome,
                "predicted_resolution_origin": origin,
                "predicted_resolution_source": "fixture",
                "source_website_candidate_count": str(source_candidates),
                "verification_signals_json": "[]",
                "job_count": "1",
                "sources": "fixture",
            }
        )
    _write_csv(
        website_path,
        list(website_rows[0].keys()),
        website_rows,
    )

    contact_rows: list[dict[str, object]] = []
    contact_strata = [
        ("email", "green", "0.98"),
        ("email", "review", "0.72"),
        ("form", "ignore", "0.35"),
    ]
    for index in range(12):
        kind, decision, confidence = contact_strata[index % 3]
        contact_rows.append(
            {
                "contact_id": str(index + 1),
                "truth_decision": "",
                "truth_purpose": "",
                "canonical_name": f"Firma {index + 1}",
                "kind": kind,
                "value": f"kontakt-{index}@firma.test",
                "predicted_decision": decision,
                "predicted_purpose": "generic",
                "predicted_confidence": confidence,
                "evidence_url": "https://firma.test/kontakt",
                "evidence_text": "Kontakt",
                "evidence_signal": "kontakt",
                "latest_evidence_snapshot_id": str(index + 1),
                "evidence_content_sha256": "a" * 64,
                "evidence_captured_at": "2026-09-15 10:00:00",
            }
        )
    _write_csv(contact_path, list(contact_rows[0].keys()), contact_rows)
    return company_path, website_path, contact_path


def test_sampling_is_deterministic_stratified_and_preserves_resolution_pairs(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_paths = _seed_label_files(first_dir)
    second_paths = _seed_label_files(second_dir)

    first = sample_quality_label_files(
        *first_paths,
        job_limit=8,
        company_limit=6,
        contact_limit=6,
        seed="fixture-seed",
    )
    second = sample_quality_label_files(
        *second_paths,
        job_limit=8,
        company_limit=6,
        contact_limit=6,
        seed="fixture-seed",
    )

    assert first.to_dict() == second.to_dict()
    assert _read_csv(first_paths[0]) == _read_csv(second_paths[0])
    assert _read_csv(first_paths[1]) == _read_csv(second_paths[1])
    assert _read_csv(first_paths[2]) == _read_csv(second_paths[2])

    company_stats = first.files[0]
    assert company_stats.population_rows == 16
    assert company_stats.sampled_rows == 8
    assert company_stats.pairwise_anchor_companies == 1
    assert company_stats.pairwise_anchor_rows == 2

    sampled_company_rows = _read_csv(first_paths[0])
    predicted_counts: dict[str, int] = {}
    for row in sampled_company_rows:
        predicted_counts[row["predicted_company_id"]] = (
            predicted_counts.get(row["predicted_company_id"], 0) + 1
        )
    assert any(count >= 2 for count in predicted_counts.values())

    website_stats = first.files[1]
    contact_stats = first.files[2]
    assert website_stats.sampled_rows == 6
    assert contact_stats.sampled_rows == 6
    assert len(website_stats.strata_sample) == 3
    assert len(contact_stats.strata_sample) == 3
    assert all(count == 2 for count in website_stats.strata_sample.values())
    assert all(count == 2 for count in contact_stats.strata_sample.values())


def test_sampling_manifest_is_machine_readable(tmp_path: Path) -> None:
    paths = _seed_label_files(tmp_path)
    manifest = sample_quality_label_files(
        *paths,
        job_limit=8,
        company_limit=6,
        contact_limit=6,
        seed="manifest-seed",
    )
    output = write_sampling_manifest(tmp_path / "sampling_manifest.json", manifest)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1"
    assert payload["seed"] == "manifest-seed"
    assert [item["sampled_rows"] for item in payload["files"]] == [8, 6, 6]


def test_quality_label_bundle_samples_full_candidate_population(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "labels.sqlite3")
    store.init_schema()
    jobs = [
        JobPosting(
            source="fixture-a" if index % 2 == 0 else "fixture-b",
            source_id=str(index),
            url=f"https://jobs.test/{index}",
            title="Pracownik",
            company_name=f"Firma {index}",
            company_name_source="fixture.company",
            company_name_confidence=0.95,
            city="Gdańsk",
        )
        for index in range(20)
    ]
    store.upsert_jobs(jobs)

    bundle = export_quality_label_bundle(
        store,
        tmp_path / "bundle",
        job_limit=7,
        company_limit=5,
        contact_limit=3,
        sampling_seed="bundle-seed",
    )

    company_rows = _read_csv(bundle.company_resolution_path)
    website_rows = _read_csv(bundle.website_resolution_path)
    sampling_manifest = json.loads(
        bundle.sampling_manifest_path.read_text(encoding="utf-8")
    )

    assert len(company_rows) == 7
    assert len(website_rows) == 5
    assert _read_csv(bundle.contact_classification_path) == []
    assert sampling_manifest["files"][0]["population_rows"] == 20
    assert sampling_manifest["files"][1]["population_rows"] == 20
    assert sampling_manifest["files"][2]["population_rows"] == 0
