from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .reporting import build_benchmark_report
from .source_health import build_source_health
from .sources.registry import SourceRegistry
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class SourceValidation:
    source: str
    state: str
    access_mode: str
    experimental: bool
    required_env: list[str]
    missing_required_env: list[str]
    current_jobs: int
    current_companies: int
    linked_companies_with_website: int
    linked_company_website_rate: float
    linked_companies_with_green: int
    linked_green_company_rate: float
    source_verified_websites: int
    source_health: dict[str, Any]
    identity_metrics: dict[str, Any]
    provenance_metrics: dict[str, Any]
    website_attempt_metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    implemented_sources: int
    exercised_sources: int
    sources_with_current_jobs: int
    healthy_sources: list[str]
    empty_sources: list[str]
    failing_sources: list[str]
    access_blocked_sources: list[str]
    not_configured_sources: list[str]
    unexercised_sources: list[str]
    sources_without_current_jobs: list[str]
    jobs_total: int
    companies_total: int
    enriched_companies: int
    websites_found: int
    green_channels: int
    green_company_rate: float
    sources: list[SourceValidation]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_validation_report(
    store: SQLiteStore,
    registry: SourceRegistry,
    *,
    environment: Mapping[str, str] | None = None,
) -> ValidationReport:
    """Build a factual P10 validation view for every implemented adapter.

    Downstream company website/GREEN counts are linked-company diagnostics. A company can
    appear in more than one source, so those per-source counts intentionally overlap.
    """

    store.init_schema()
    env = os.environ if environment is None else environment
    names = registry.names()
    benchmark = build_benchmark_report(store)
    health_items = build_source_health(store, names)
    health = {item.source: item.to_dict() for item in health_items}
    downstream = _downstream_by_source(store)

    source_rows: list[SourceValidation] = []
    for name in names:
        registration = registry.describe(name)
        row = downstream.get(name, {})
        current_companies = int(row.get("current_companies", 0))
        websites = int(row.get("linked_companies_with_website", 0))
        green = int(row.get("linked_companies_with_green", 0))
        source_health = dict(
            health.get(name, {"source": name, "state": "unexercised", "runs": 0})
        )
        missing_required = [
            env_name
            for env_name in registration.required_env
            if not str(env.get(env_name, "")).strip()
        ]
        state = str(source_health.get("state", "unexercised"))
        if state == "unexercised" and missing_required:
            state = "not_configured"
            source_health["state"] = state
            source_health["missing_required_env"] = missing_required

        source_rows.append(
            SourceValidation(
                source=name,
                state=state,
                access_mode=registration.access_mode,
                experimental=registration.experimental,
                required_env=list(registration.required_env),
                missing_required_env=missing_required,
                current_jobs=int(row.get("current_jobs", 0)),
                current_companies=current_companies,
                linked_companies_with_website=websites,
                linked_company_website_rate=_ratio(websites, current_companies),
                linked_companies_with_green=green,
                linked_green_company_rate=_ratio(green, current_companies),
                source_verified_websites=int(
                    benchmark.source_verified_website_counts.get(name, 0)
                ),
                source_health=source_health,
                identity_metrics=benchmark.source_identity_metrics.get(name, {}),
                provenance_metrics=benchmark.source_provenance_metrics.get(name, {}),
                website_attempt_metrics=benchmark.source_website_attempt_metrics.get(name, {}),
            )
        )

    healthy = [item.source for item in source_rows if item.state == "healthy"]
    empty = [item.source for item in source_rows if item.state == "empty"]
    failing = [item.source for item in source_rows if item.state == "failing"]
    access_blocked = [
        item.source for item in source_rows if item.state == "access_blocked"
    ]
    not_configured = [
        item.source for item in source_rows if item.state == "not_configured"
    ]
    unexercised = [
        item.source for item in source_rows if item.state == "unexercised"
    ]
    without_jobs = [item.source for item in source_rows if item.current_jobs == 0]
    exercised = sum(
        1 for item in source_rows if int(item.source_health.get("runs", 0) or 0) > 0
    )

    return ValidationReport(
        implemented_sources=len(names),
        exercised_sources=exercised,
        sources_with_current_jobs=len(names) - len(without_jobs),
        healthy_sources=healthy,
        empty_sources=empty,
        failing_sources=failing,
        access_blocked_sources=access_blocked,
        not_configured_sources=not_configured,
        unexercised_sources=unexercised,
        sources_without_current_jobs=without_jobs,
        jobs_total=benchmark.jobs_total,
        companies_total=benchmark.companies_total,
        enriched_companies=benchmark.enriched_companies,
        websites_found=benchmark.websites_found,
        green_channels=benchmark.green_channels,
        green_company_rate=benchmark.green_company_rate,
        sources=source_rows,
    )


def render_validation_markdown(report: ValidationReport) -> str:
    lines = [
        "# Faro — P10 validation report",
        "",
        "## Podsumowanie",
        "",
        f"- Zaimplementowane źródła: **{report.implemented_sources}**",
        f"- Źródła z historią uruchomień: **{report.exercised_sources}**",
        f"- Źródła z rekordami w current state: **{report.sources_with_current_jobs}**",
        f"- Oferty: **{report.jobs_total}**",
        f"- Firmy: **{report.companies_total}**",
        f"- Firmy wzbogacone: **{report.enriched_companies}**",
        f"- Zweryfikowane WWW: **{report.websites_found}**",
        f"- Kanały GREEN: **{report.green_channels}**",
        f"- GREEN company rate: **{report.green_company_rate:.1%}**",
        "",
        "## Source health",
        "",
        f"- Healthy: `{', '.join(report.healthy_sources) or 'none'}`",
        f"- Empty (run OK, 0 ofert): `{', '.join(report.empty_sources) or 'none'}`",
        f"- Failing: `{', '.join(report.failing_sources) or 'none'}`",
        f"- Access blocked: `{', '.join(report.access_blocked_sources) or 'none'}`",
        f"- Not configured: `{', '.join(report.not_configured_sources) or 'none'}`",
        f"- Unexercised: `{', '.join(report.unexercised_sources) or 'none'}`",
        (
            "- Bez rekordów w current state: `"
            + (", ".join(report.sources_without_current_jobs) or "none")
            + "`"
        ),
        "",
        "## Źródła",
        "",
        (
            "| Source | Health | Runs | Jobs | Companies | WWW linked | GREEN linked | "
            "Name conf. | Resolution conf. | Access |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for item in report.sources:
        health = item.source_health
        identity = item.identity_metrics
        lines.append(
            "| {source} | {state} | {runs} | {jobs} | {companies} | "
            "{websites} ({website_rate:.1%}) | {green} ({green_rate:.1%}) | "
            "{name_conf:.3f} | {resolution_conf:.3f} | {access} |".format(
                source=item.source,
                state=item.state,
                runs=int(health.get("runs", 0) or 0),
                jobs=item.current_jobs,
                companies=item.current_companies,
                websites=item.linked_companies_with_website,
                website_rate=item.linked_company_website_rate,
                green=item.linked_companies_with_green,
                green_rate=item.linked_green_company_rate,
                name_conf=float(identity.get("avg_company_name_confidence", 0.0) or 0.0),
                resolution_conf=float(
                    identity.get("avg_company_resolution_confidence", 0.0) or 0.0
                ),
                access=item.access_mode,
            )
        )

    lines.extend(
        [
            "",
            "> `empty` oznacza udany technicznie przebieg z 0 ofertami; nie przesądza, "
            "czy źródło faktycznie było puste, czy parser wymaga ponownej walidacji.",
            "",
            "> Per-source WWW/GREEN to diagnostyka powiązanych firm. Ta sama firma może być "
            "obecna w kilku źródłach, więc wartości między wierszami mogą się nakładać.",
            "",
        ]
    )
    return "\n".join(lines)


def _downstream_by_source(store: SQLiteStore) -> dict[str, dict[str, int]]:
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                j.source,
                COUNT(DISTINCT j.id) AS current_jobs,
                COUNT(DISTINCT j.company_id) AS current_companies,
                COUNT(
                    DISTINCT CASE WHEN c.website_url IS NOT NULL THEN j.company_id END
                ) AS linked_companies_with_website,
                COUNT(
                    DISTINCT CASE WHEN cc.decision = 'green' THEN j.company_id END
                ) AS linked_companies_with_green
            FROM job_postings j
            JOIN companies c ON c.id = j.company_id
            LEFT JOIN contact_channels cc ON cc.company_id = j.company_id
            GROUP BY j.source
            ORDER BY j.source
            """
        ).fetchall()
    return {
        str(row["source"]): {
            "current_jobs": int(row["current_jobs"] or 0),
            "current_companies": int(row["current_companies"] or 0),
            "linked_companies_with_website": int(
                row["linked_companies_with_website"] or 0
            ),
            "linked_companies_with_green": int(row["linked_companies_with_green"] or 0),
        }
        for row in rows
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
