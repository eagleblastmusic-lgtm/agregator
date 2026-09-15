from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .base import JobSource

SourceFactory = Callable[[], JobSource]


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    name: str
    factory: SourceFactory
    access_mode: str = "unspecified"
    experimental: bool = False
    notes: str | None = None
    required_env: tuple[str, ...] = ()
    configuration_env: tuple[str, ...] = ()


class SourceRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, SourceRegistration] = {}

    def register(
        self,
        name: str,
        factory: SourceFactory,
        *,
        access_mode: str = "unspecified",
        experimental: bool = False,
        notes: str | None = None,
        required_env: Iterable[str] = (),
        configuration_env: Iterable[str] = (),
    ) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("source name cannot be empty")
        self._registrations[normalized] = SourceRegistration(
            name=normalized,
            factory=factory,
            access_mode=access_mode.strip() or "unspecified",
            experimental=experimental,
            notes=notes.strip() if notes else None,
            required_env=_normalize_env_names(required_env),
            configuration_env=_normalize_env_names(configuration_env),
        )

    def create(self, name: str) -> JobSource:
        return self.describe(name).factory()

    def describe(self, name: str) -> SourceRegistration:
        normalized = name.strip().lower()
        try:
            return self._registrations[normalized]
        except KeyError as exc:
            known = ", ".join(sorted(self._registrations)) or "none"
            raise KeyError(f"unknown source: {name}; registered: {known}") from exc

    def names(self) -> list[str]:
        return sorted(self._registrations)

    def registrations(self) -> list[SourceRegistration]:
        return [self._registrations[name] for name in self.names()]


def _normalize_env_names(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = value.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)
