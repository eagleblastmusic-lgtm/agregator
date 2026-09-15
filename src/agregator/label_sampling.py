from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

Row = dict[str, str]
StratumFn = Callable[[Row], str]

DEFAULT_SAMPLING_SEED = "faro-ground-truth-v1"


@dataclass(frozen=True, slots=True)
class LabelSampleStats:
    name: str
    population_rows: int
    requested_limit: int
    sampled_rows: int
    strata_population: dict[str, int]
    strata_sample: dict[str, int]
    pairwise_anchor_companies: int = 0
    pairwise_anchor_rows: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LabelSamplingManifest:
    seed: str
    strategy: str
    files: tuple[LabelSampleStats, ...]
    schema_version: str = "1"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "strategy": self.strategy,
            "files": [item.to_dict() for item in self.files],
        }


def sample_quality_label_files(
    company_resolution_path: str | Path,
    website_resolution_path: str | Path,
    contact_classification_path: str | Path,
    *,
    job_limit: int,
    company_limit: int,
    contact_limit: int,
    seed: str = DEFAULT_SAMPLING_SEED,
) -> LabelSamplingManifest:
    if min(job_limit, company_limit, contact_limit) < 1:
        raise ValueError("label sampling limits must be >= 1")

    company_stats = _sample_csv(
        Path(company_resolution_path),
        name="company_resolution",
        limit=job_limit,
        seed=f"{seed}:company_resolution",
        key_fields=("source", "source_id"),
        stratum_fn=_company_resolution_stratum,
        preserve_resolution_pairs=True,
    )
    website_stats = _sample_csv(
        Path(website_resolution_path),
        name="website_resolution",
        limit=company_limit,
        seed=f"{seed}:website_resolution",
        key_fields=("company_id",),
        stratum_fn=_website_resolution_stratum,
    )
    contact_stats = _sample_csv(
        Path(contact_classification_path),
        name="contact_classification",
        limit=contact_limit,
        seed=f"{seed}:contact_classification",
        key_fields=("contact_id",),
        stratum_fn=_contact_classification_stratum,
    )

    return LabelSamplingManifest(
        seed=seed,
        strategy=(
            "deterministic stratified sampling with proportional residual allocation; "
            "company resolution additionally reserves predicted-company pair anchors"
        ),
        files=(company_stats, website_stats, contact_stats),
    )


def write_sampling_manifest(
    path: str | Path,
    manifest: LabelSamplingManifest,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def _sample_csv(
    path: Path,
    *,
    name: str,
    limit: int,
    seed: str,
    key_fields: tuple[str, ...],
    stratum_fn: StratumFn,
    preserve_resolution_pairs: bool = False,
) -> LabelSampleStats:
    fieldnames, rows = _read_csv(path)
    population = len(rows)
    strata_population = Counter(stratum_fn(row) for row in rows)

    pairwise_anchor_companies = 0
    pairwise_anchor_rows = 0
    if population <= limit:
        sampled = rows
    elif preserve_resolution_pairs:
        sampled, pairwise_anchor_companies, pairwise_anchor_rows = (
            _sample_company_resolution_rows(
                rows,
                limit=limit,
                seed=seed,
                key_fields=key_fields,
                stratum_fn=stratum_fn,
            )
        )
    else:
        sampled = _stratified_sample(
            rows,
            limit=limit,
            seed=seed,
            key_fields=key_fields,
            stratum_fn=stratum_fn,
        )

    sampled = sorted(
        sampled,
        key=lambda row: (
            _stable_digest(seed, "final", _row_key(row, key_fields)),
            _row_key(row, key_fields),
        ),
    )
    _write_csv(path, fieldnames, sampled)
    strata_sample = Counter(stratum_fn(row) for row in sampled)

    return LabelSampleStats(
        name=name,
        population_rows=population,
        requested_limit=limit,
        sampled_rows=len(sampled),
        strata_population=dict(sorted(strata_population.items())),
        strata_sample=dict(sorted(strata_sample.items())),
        pairwise_anchor_companies=pairwise_anchor_companies,
        pairwise_anchor_rows=pairwise_anchor_rows,
    )


def _sample_company_resolution_rows(
    rows: list[Row],
    *,
    limit: int,
    seed: str,
    key_fields: tuple[str, ...],
    stratum_fn: StratumFn,
) -> tuple[list[Row], int, int]:
    clusters: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        predicted_company_id = row.get("predicted_company_id", "").strip()
        if predicted_company_id:
            clusters[predicted_company_id].append(row)

    eligible = [
        (company_id, members)
        for company_id, members in clusters.items()
        if len(members) >= 2
    ]
    eligible.sort(
        key=lambda item: (
            _stable_digest(seed, "cluster", item[0]),
            item[0],
        )
    )

    max_anchor_companies = min(len(eligible), max(0, limit // 8))
    anchors: list[Row] = []
    for company_id, members in eligible[:max_anchor_companies]:
        ordered = sorted(
            members,
            key=lambda row: (
                _stable_digest(
                    seed,
                    f"cluster:{company_id}",
                    _row_key(row, key_fields),
                ),
                _row_key(row, key_fields),
            ),
        )
        anchors.extend(ordered[:2])

    anchor_keys = {_row_key(row, key_fields) for row in anchors}
    remaining_rows = [
        row for row in rows if _row_key(row, key_fields) not in anchor_keys
    ]
    remaining_limit = max(0, limit - len(anchors))
    remainder = _stratified_sample(
        remaining_rows,
        limit=remaining_limit,
        seed=f"{seed}:remainder",
        key_fields=key_fields,
        stratum_fn=stratum_fn,
    )
    return anchors + remainder, max_anchor_companies, len(anchors)


def _stratified_sample(
    rows: list[Row],
    *,
    limit: int,
    seed: str,
    key_fields: tuple[str, ...],
    stratum_fn: StratumFn,
) -> list[Row]:
    if limit <= 0:
        return []
    if len(rows) <= limit:
        return list(rows)

    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        groups[stratum_fn(row)].append(row)

    allocations = _allocate_strata(groups, limit=limit, seed=seed)
    sampled: list[Row] = []
    for stratum, allocation in allocations.items():
        if allocation <= 0:
            continue
        ordered = sorted(
            groups[stratum],
            key=lambda row: (
                _stable_digest(seed, stratum, _row_key(row, key_fields)),
                _row_key(row, key_fields),
            ),
        )
        sampled.extend(ordered[:allocation])
    return sampled


def _allocate_strata(
    groups: dict[str, list[Row]],
    *,
    limit: int,
    seed: str,
) -> dict[str, int]:
    strata = sorted(groups)
    if not strata or limit <= 0:
        return {}

    if limit < len(strata):
        chosen = sorted(
            strata,
            key=lambda key: (
                -len(groups[key]),
                _stable_digest(seed, "stratum", key),
                key,
            ),
        )[:limit]
        return {key: 1 for key in chosen}

    allocations = {key: 1 for key in strata}
    remaining = limit - len(strata)
    if remaining <= 0:
        return allocations

    capacities = {key: len(groups[key]) - 1 for key in strata}
    total_capacity = sum(capacities.values())
    if total_capacity <= 0:
        return allocations

    proportional_remaining = min(remaining, total_capacity)
    remainders: list[tuple[int, str]] = []
    allocated_extra = 0
    for key in strata:
        numerator = proportional_remaining * capacities[key]
        extra = numerator // total_capacity
        extra = min(extra, capacities[key])
        allocations[key] += extra
        allocated_extra += extra
        remainders.append((numerator % total_capacity, key))

    leftover = proportional_remaining - allocated_extra
    for _, key in sorted(
        remainders,
        key=lambda item: (
            -item[0],
            _stable_digest(seed, "remainder", item[1]),
            item[1],
        ),
    ):
        if leftover <= 0:
            break
        if allocations[key] >= len(groups[key]):
            continue
        allocations[key] += 1
        leftover -= 1

    return allocations


def _company_resolution_stratum(row: Row) -> str:
    return "|".join(
        (
            row.get("source", "").strip().lower() or "unknown_source",
            row.get("company_resolution_method", "").strip().lower()
            or "unknown_method",
            _confidence_band(row.get("company_resolution_confidence")),
        )
    )


def _website_resolution_stratum(row: Row) -> str:
    candidate_count = _safe_int(row.get("source_website_candidate_count"))
    candidate_group = "has_source_candidate" if candidate_count > 0 else "no_source_candidate"
    return "|".join(
        (
            row.get("predicted_resolution_origin", "").strip().lower()
            or "no_resolution_origin",
            row.get("verification_outcome", "").strip().lower() or "no_outcome",
            _confidence_band(row.get("website_confidence")),
            candidate_group,
        )
    )


def _contact_classification_stratum(row: Row) -> str:
    return "|".join(
        (
            row.get("kind", "").strip().lower() or "unknown_kind",
            row.get("predicted_decision", "").strip().lower() or "unknown_decision",
            _confidence_band(row.get("predicted_confidence")),
        )
    )


def _confidence_band(raw: str | None) -> str:
    try:
        value = float((raw or "").strip())
    except ValueError:
        return "unknown_confidence"
    if value < 0.50:
        return "0.00-0.49"
    if value < 0.80:
        return "0.50-0.79"
    if value < 0.95:
        return "0.80-0.94"
    return "0.95-1.00"


def _row_key(row: Row, key_fields: tuple[str, ...]) -> str:
    return "\x1f".join((row.get(field) or "").strip() for field in key_fields)


def _stable_digest(seed: str, namespace: str, value: str) -> str:
    payload = f"{seed}\x1f{namespace}\x1f{value}".encode()
    return hashlib.sha256(payload).hexdigest()


def _safe_int(raw: str | None) -> int:
    try:
        return int((raw or "0").strip())
    except ValueError:
        return 0


def _read_csv(path: Path) -> tuple[list[str], list[Row]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[Row]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
