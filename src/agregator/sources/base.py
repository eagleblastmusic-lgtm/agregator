from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import JobPosting


@dataclass(slots=True)
class SourceBatch:
    jobs: list[JobPosting]
    next_cursor: str | None = None


class JobSource(Protocol):
    name: str

    async def collect(self, cursor: str | None = None) -> SourceBatch: ...
