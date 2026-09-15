from __future__ import annotations

from collections.abc import Callable
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
