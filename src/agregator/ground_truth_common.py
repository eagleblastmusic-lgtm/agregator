from __future__ import annotations

import csv
from pathlib import Path

EXCLUDE_LABEL = "__exclude__"


def count_excluded_labels(path: str | Path, label_field: str) -> int:
    """Count rows explicitly excluded from benchmark scoring.

    `__exclude__` is a deliberate human-label outcome for cases where reliable truth
    cannot be established from available evidence. Excluded rows remain visible in
    labeling progress but must never be interpreted as a real class/entity label.
    """

    count = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if label_field not in set(reader.fieldnames or []):
            return 0
        for row in reader:
            if (row.get(label_field) or "").strip().lower() == EXCLUDE_LABEL:
                count += 1
    return count
