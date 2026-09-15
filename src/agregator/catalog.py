from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "source_catalog.tsv"

IMPLEMENTED_ADAPTERS: dict[int, str] = {
    1: "pracuj",
    4: "aplikuj",
    7: "olx",
    10: "justjoinit",
    11: "nofluffjobs",
    16: "rocketjobs",
    20: "epraca",
    21: "kprm",
    30: "jooble",
    32: "careerjet",
    48: "ngo",
    50: "karierawfinansach",
    53: "skillshot",
    56: "ofertypracyedu",
    79: "adzuna",
}


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    id: int
    name: str
    url: str
    priority: str
    type: str
    public_api: str
    integration: str

    @property
    def adapter(self) -> str | None:
        return IMPLEMENTED_ADAPTERS.get(self.id)

    @property
    def implemented(self) -> bool:
        return self.adapter is not None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = asdict(self)
        data["adapter"] = self.adapter
        data["implemented"] = self.implemented
        return data


def load_source_catalog(
    path: str | Path = DEFAULT_CATALOG_PATH,
) -> list[SourceCatalogEntry]:
    entries: list[SourceCatalogEntry] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            entries.append(
                SourceCatalogEntry(
                    id=int(row["id"]),
                    name=row["name"].strip(),
                    url=row["url"].strip(),
                    priority=row["priority"].strip(),
                    type=row["type"].strip(),
                    public_api=row["public_api"].strip(),
                    integration=row["integration"].strip(),
                )
            )
    return entries


def filter_catalog(
    entries: list[SourceCatalogEntry],
    *,
    priority: str | None = None,
    implemented: bool | None = None,
) -> list[SourceCatalogEntry]:
    result = entries
    if priority:
        normalized = priority.strip().upper()
        result = [entry for entry in result if entry.priority.upper() == normalized]
    if implemented is not None:
        result = [entry for entry in result if entry.implemented is implemented]
    return result


def catalog_summary(entries: list[SourceCatalogEntry]) -> dict[str, object]:
    priorities: dict[str, int] = {}
    for entry in entries:
        priorities[entry.priority] = priorities.get(entry.priority, 0) + 1

    implemented = [entry for entry in entries if entry.implemented]
    return {
        "total": len(entries),
        "implemented": len(implemented),
        "remaining": len(entries) - len(implemented),
        "priorities": dict(sorted(priorities.items())),
        "implemented_adapters": [entry.adapter for entry in implemented],
    }
