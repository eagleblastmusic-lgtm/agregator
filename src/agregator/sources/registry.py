from __future__ import annotations

from collections.abc import Callable

from .base import JobSource

SourceFactory = Callable[[], JobSource]


class SourceRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, SourceFactory] = {}

    def register(self, name: str, factory: SourceFactory) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("source name cannot be empty")
        self._factories[normalized] = factory

    def create(self, name: str) -> JobSource:
        normalized = name.strip().lower()
        try:
            factory = self._factories[normalized]
        except KeyError as exc:
            known = ", ".join(sorted(self._factories)) or "none"
            raise KeyError(f"unknown source: {name}; registered: {known}") from exc
        return factory()

    def names(self) -> list[str]:
        return sorted(self._factories)
