from __future__ import annotations

import json

import typer

from .lead_export import export_company_leads_xlsx
from .storage import SQLiteStore

app = typer.Typer(help="Faro final company lead database exporter")


@app.command("export")
def export(
    output: str = typer.Option("export/faro_firmy_kontakt.xlsx", "--output"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
) -> None:
    result = export_company_leads_xlsx(SQLiteStore(db), output)
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
