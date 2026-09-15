from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xlsxwriter

from .company_identifiers import init_company_identifier_schema
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class LeadExportResult:
    path: Path
    companies: int

    def to_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "companies": self.companies}


def build_company_lead_rows(store: SQLiteStore) -> list[dict[str, Any]]:
    """Build one export row per company that has at least one GREEN contact channel.

    Source job records remain untouched and non-deduplicated. This function only creates
    the final company-level view used for human review/export.
    """

    store.init_schema()
    init_company_identifier_schema(store)

    with store.connect() as connection:
        companies = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.canonical_name,
                c.city,
                c.website_url,
                COUNT(DISTINCT j.id) AS job_count,
                GROUP_CONCAT(DISTINCT j.source) AS job_sources
            FROM companies c
            JOIN contact_channels cc
              ON cc.company_id = c.id
             AND cc.decision = 'green'
            LEFT JOIN job_postings j ON j.company_id = c.id
            GROUP BY c.id
            ORDER BY c.canonical_name COLLATE NOCASE ASC, c.id ASC
            """
        ).fetchall()

        contacts = connection.execute(
            """
            SELECT
                company_id,
                kind,
                value,
                purpose,
                confidence,
                evidence_url,
                evidence_text,
                evidence_signal,
                verified_at
            FROM contact_channels
            WHERE decision = 'green'
            ORDER BY company_id ASC, confidence DESC, kind ASC, value ASC
            """
        ).fetchall()

        identifiers = connection.execute(
            """
            SELECT company_id, kind, value, confidence
            FROM company_identifiers
            ORDER BY company_id ASC, confidence DESC, kind ASC, value ASC
            """
        ).fetchall()

    contacts_by_company: dict[int, list[dict[str, Any]]] = {}
    for row in contacts:
        contacts_by_company.setdefault(int(row["company_id"]), []).append(dict(row))

    identifiers_by_company: dict[int, dict[str, list[str]]] = {}
    for row in identifiers:
        company_id = int(row["company_id"])
        kind = str(row["kind"]).strip().lower()
        value = str(row["value"]).strip()
        if not value:
            continue
        values = identifiers_by_company.setdefault(company_id, {}).setdefault(kind, [])
        if value not in values:
            values.append(value)

    output: list[dict[str, Any]] = []
    for company_row in companies:
        company_id = int(company_row["company_id"])
        company_contacts = contacts_by_company.get(company_id, [])
        if not company_contacts:
            continue

        primary = company_contacts[0]
        all_contacts = _unique_preserve_order(
            [f"{item['kind']}: {item['value']}" for item in company_contacts]
        )
        all_evidence = _unique_preserve_order(
            [str(item["evidence_text"]).strip() for item in company_contacts if item["evidence_text"]]
        )
        all_evidence_urls = _unique_preserve_order(
            [str(item["evidence_url"]).strip() for item in company_contacts if item["evidence_url"]]
        )
        kinds = identifiers_by_company.get(company_id, {})

        output.append(
            {
                "company_id": company_id,
                "company_name": company_row["canonical_name"],
                "city": company_row["city"],
                "website": company_row["website_url"],
                "status": "GREEN",
                "primary_contact": primary["value"],
                "primary_contact_kind": primary["kind"],
                "primary_purpose": primary["purpose"],
                "contact_confidence": float(primary["confidence"]),
                "all_contacts": "\n".join(all_contacts),
                "evidence_text": str(primary["evidence_text"] or ""),
                "evidence_signal": str(primary["evidence_signal"] or ""),
                "evidence_url": str(primary["evidence_url"] or ""),
                "all_evidence": "\n---\n".join(all_evidence),
                "all_evidence_urls": "\n".join(all_evidence_urls),
                "nip": " | ".join(kinds.get("nip", [])),
                "regon": " | ".join(kinds.get("regon", [])),
                "krs": " | ".join(kinds.get("krs", [])),
                "job_count": int(company_row["job_count"] or 0),
                "job_sources": str(company_row["job_sources"] or ""),
                "verified_at": primary["verified_at"],
            }
        )

    return output


def export_company_leads_xlsx(
    store: SQLiteStore,
    output: str | Path,
) -> LeadExportResult:
    """Export the final one-company-per-row GREEN contact database to Excel."""

    path = Path(output)
    if path.suffix.lower() != ".xlsx":
        path = path.with_suffix(".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = build_company_lead_rows(store)
    workbook = xlsxwriter.Workbook(path)
    try:
        _write_leads_sheet(workbook, rows)
        _write_legend_sheet(workbook)
    finally:
        workbook.close()

    return LeadExportResult(path=path, companies=len(rows))


def _write_leads_sheet(workbook: xlsxwriter.Workbook, rows: list[dict[str, Any]]) -> None:
    sheet = workbook.add_worksheet("Firmy kontakt")
    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#183B56",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
    confidence = workbook.add_format({"num_format": "0%", "valign": "top"})
    link = workbook.add_format({"font_color": "#0563C1", "underline": 1, "valign": "top"})

    columns = [
        ("Firma", "company_name"),
        ("Miasto", "city"),
        ("WWW", "website"),
        ("Status", "status"),
        ("Kontakt główny", "primary_contact"),
        ("Typ kontaktu", "primary_contact_kind"),
        ("Cel kontaktu", "primary_purpose"),
        ("Pewność", "contact_confidence"),
        ("Wszystkie kontakty GREEN", "all_contacts"),
        ("Dowód / kontekst", "evidence_text"),
        ("Sygnał", "evidence_signal"),
        ("URL dowodu", "evidence_url"),
        ("NIP", "nip"),
        ("REGON", "regon"),
        ("KRS", "krs"),
        ("Liczba ofert", "job_count"),
        ("Portale źródłowe", "job_sources"),
        ("Data weryfikacji", "verified_at"),
    ]

    for col, (title, _) in enumerate(columns):
        sheet.write(0, col, title, header)

    for row_index, row in enumerate(rows, start=1):
        for col, (_, key) in enumerate(columns):
            value = row.get(key)
            if key == "contact_confidence":
                sheet.write_number(row_index, col, float(value or 0), confidence)
            elif key in {"website", "evidence_url"} and isinstance(value, str) and value.startswith(("http://", "https://")):
                sheet.write_url(row_index, col, value, link, string=value)
            elif isinstance(value, int):
                sheet.write_number(row_index, col, value)
            else:
                sheet.write(row_index, col, "" if value is None else str(value), wrap)

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(0, len(rows)), len(columns) - 1)
    widths = [32, 18, 30, 10, 30, 14, 22, 10, 38, 48, 24, 36, 16, 16, 16, 12, 28, 20]
    for idx, width in enumerate(widths):
        sheet.set_column(idx, idx, width)
    sheet.set_row(0, 26)


def _write_legend_sheet(workbook: xlsxwriter.Workbook) -> None:
    sheet = workbook.add_worksheet("Legenda")
    title = workbook.add_format({"bold": True, "font_size": 14})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    sheet.write("A1", "Znaczenie eksportu", title)
    sheet.write(
        "A3",
        (
            "Jedna firma występuje w tym arkuszu tylko raz. Surowe rekordy ofert z różnych "
            "portali pozostają zachowane osobno w bazie wejściowej i nie są deduplikowane."
        ),
        wrap,
    )
    sheet.write(
        "A5",
        (
            "GREEN oznacza publiczny, istotny sygnał współpracy/partnerstwa/ofert handlowych "
            "wykryty przez system wraz z zachowanym dowodem. Nie jest to automatyczne stwierdzenie "
            "zgody prawnej na dowolny marketing; przed outreach należy ocenić konkretny kanał i kontekst."
        ),
        wrap,
    )
    sheet.set_column("A:A", 110)
    sheet.set_row(2, 55)
    sheet.set_row(4, 75)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output
