from __future__ import annotations

import json
from pathlib import Path

import typer

from .sources import default_registry
from .storage import SQLiteStore
from .validation import build_validation_report, render_validation_markdown

app = typer.Typer(help="Faro P10 real-source validation reports")


@app.command("report")
def report(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    output: str | None = typer.Option(None, "--output", help="Opcjonalny raport JSON"),
    markdown: str | None = typer.Option(
        None,
        "--markdown",
        help="Opcjonalny raport Markdown z tabelą per źródło",
    ),
) -> None:
    store = SQLiteStore(db)
    result = build_validation_report(store, default_registry())
    payload = result.to_dict()

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if markdown:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_validation_markdown(result),
            encoding="utf-8",
        )

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
