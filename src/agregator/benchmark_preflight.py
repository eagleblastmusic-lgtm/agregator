from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .sources.registry import SourceRegistry


@dataclass(frozen=True, slots=True)
class SourcePreflight:
    name: str
    ready: bool
    access_mode: str = "unspecified"
    experimental: bool = False
    error: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkPreflight:
    search_provider_ready: bool
    sources: tuple[SourcePreflight, ...]
    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_provider_ready": self.search_provider_ready,
            "sources": [item.to_dict() for item in self.sources],
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def build_benchmark_preflight(
    registry: SourceRegistry,
    source_names: list[str],
    *,
    search_provider_ready: bool,
    allow_experimental_sources: bool = False,
) -> BenchmarkPreflight:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in source_names:
        name = raw_name.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)

    source_results: list[SourcePreflight] = []
    blockers: list[str] = []
    warnings: list[str] = []
    if not search_provider_ready:
        blockers.append("missing_search_provider_configuration")

    if not normalized:
        blockers.append("no_sources_requested")

    for name in normalized:
        try:
            registration = registry.describe(name)
        except KeyError as exc:
            error = str(exc)
            source_results.append(
                SourcePreflight(
                    name=name,
                    ready=False,
                    error=error,
                )
            )
            blockers.append(f"source_not_ready:{name}")
            continue

        warning = registration.notes if registration.experimental else None
        if registration.experimental and not allow_experimental_sources:
            source_results.append(
                SourcePreflight(
                    name=name,
                    ready=False,
                    access_mode=registration.access_mode,
                    experimental=True,
                    error="experimental_source_requires_explicit_acknowledgement",
                    warning=warning,
                )
            )
            blockers.append(f"experimental_source_not_acknowledged:{name}")
            if warning:
                warnings.append(f"{name}:{warning}")
            continue

        try:
            registry.create(name)
        except (KeyError, ValueError) as exc:
            error = str(exc)
            source_results.append(
                SourcePreflight(
                    name=name,
                    ready=False,
                    access_mode=registration.access_mode,
                    experimental=registration.experimental,
                    error=error,
                    warning=warning,
                )
            )
            blockers.append(f"source_not_ready:{name}")
        else:
            source_results.append(
                SourcePreflight(
                    name=name,
                    ready=True,
                    access_mode=registration.access_mode,
                    experimental=registration.experimental,
                    warning=warning,
                )
            )
        if warning:
            warnings.append(f"{name}:{warning}")

    return BenchmarkPreflight(
        search_provider_ready=search_provider_ready,
        sources=tuple(source_results),
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
