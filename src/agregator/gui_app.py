from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from .gui import (
    CREDENTIAL_SOURCES,
    HOLD_SOURCES,
    SOURCE_LABELS,
    VERIFIED_SOURCES,
    CollectionConfig,
    ContactConfig,
    build_collection_command,
    build_contact_command,
)


def selectable_sources() -> tuple[str, ...]:
    """Sources that the desktop GUI may actively run in Etap 1."""

    return VERIFIED_SOURCES + CREDENTIAL_SOURCES


def _quote_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    project_root = Path.cwd()
    default_output_dir = project_root / "wyniki"

    class FaroGui:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title("Faro Emaile — 2 etapy")
            self.root.geometry("1240x930")
            self.root.minsize(1060, 810)

            self.process: subprocess.Popen[str] | None = None
            self.active_stage: str | None = None
            self.events: queue.Queue[tuple[str, object]] = queue.Queue()

            all_sources = VERIFIED_SOURCES + HOLD_SOURCES + CREDENTIAL_SOURCES
            self.source_vars = {
                source: tk.BooleanVar(value=source in VERIFIED_SOURCES)
                for source in all_sources
            }

            self.pages_var = tk.IntVar(value=5)
            self.fresh_var = tk.BooleanVar(value=True)
            self.collection_strict_var = tk.BooleanVar(value=True)
            self.database_var = tk.StringVar(
                value=str(default_output_dir / "faro_oferty.sqlite3")
            )
            self.output_var = tk.StringVar(
                value=str(default_output_dir / "Faro_Firmy_Kontakt.xlsx")
            )
            self.enrichment_var = tk.IntVar(value=300)
            self.refresh_var = tk.BooleanVar(value=False)
            self.contact_strict_var = tk.BooleanVar(value=True)
            self.brave_key_var = tk.StringVar(value=os.getenv("BRAVE_SEARCH_API_KEY", ""))
            self.status_var = tk.StringVar(value="Gotowy — wybierz etap")

            self._configure_style()
            self._build_ui()
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.after(100, self._poll_events)

        def _configure_style(self) -> None:
            style = ttk.Style()
            with contextlib.suppress(tk.TclError):
                style.theme_use("vista")
            style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
            style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
            style.configure("Step.TLabel", font=("Segoe UI", 15, "bold"))
            style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 9))

        def _build_ui(self) -> None:
            outer = ttk.Frame(self.root, padding=18)
            outer.pack(fill="both", expand=True)

            ttk.Label(outer, text="Faro Emaile", style="Title.TLabel").pack(anchor="w")
            ttk.Label(
                outer,
                text=(
                    "Etap 1 zbiera wyłącznie oferty. Etap 2 pracuje na zapisanej bazie "
                    "i wyszukuje właściwe kontakty biznesowe."
                ),
                style="Subtitle.TLabel",
            ).pack(anchor="w", pady=(2, 12))

            notebook = ttk.Notebook(outer)
            notebook.pack(fill="both", expand=True)
            collect_tab = ttk.Frame(notebook, padding=14)
            contact_tab = ttk.Frame(notebook, padding=14)
            notebook.add(collect_tab, text="1. Scraping ofert")
            notebook.add(contact_tab, text="2. Wyszukiwanie maili / kontaktów")

            self._build_collection_tab(collect_tab)
            self._build_contact_tab(contact_tab)
            self._build_log_panel(outer)

        def _source_group(
            self,
            parent: object,
            *,
            row: int,
            title: str,
            sources: tuple[str, ...],
            disabled: bool = False,
        ) -> int:
            ttk.Label(parent, text=title, font=("Segoe UI", 9, "bold")).grid(
                row=row,
                column=0,
                columnspan=4,
                sticky="w",
                pady=(0, 4),
            )
            start = row + 1
            for index, source in enumerate(sources):
                check = ttk.Checkbutton(
                    parent,
                    text=SOURCE_LABELS[source],
                    variable=self.source_vars[source],
                )
                if disabled:
                    self.source_vars[source].set(False)
                    check.configure(state="disabled")
                check.grid(
                    row=start + index // 4,
                    column=index % 4,
                    sticky="w",
                    padx=(0, 14),
                    pady=2,
                )
            return start + (len(sources) + 3) // 4

        def _build_collection_tab(self, parent: object) -> None:
            parent.columnconfigure(0, weight=1)
            ttk.Label(
                parent,
                text="Etap 1 — tylko pobieranie ofert",
                style="Step.TLabel",
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                parent,
                text=(
                    "Ten etap nie szuka stron firm, nie analizuje maili i nie tworzy "
                    "Excela kontaktowego. Wynikiem jest baza SQLite z ofertami i firmami."
                ),
                wraplength=1050,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(3, 10))

            frame = ttk.LabelFrame(
                parent,
                text="Źródła ofert",
                padding=12,
                style="Section.TLabelframe",
            )
            frame.grid(row=2, column=0, sticky="ew")
            for column in range(4):
                frame.columnconfigure(column, weight=1)

            row = self._source_group(
                frame,
                row=0,
                title="Zweryfikowane live / produkcyjnie",
                sources=VERIFIED_SOURCES,
            )
            ttk.Separator(frame).grid(
                row=row,
                column=0,
                columnspan=4,
                sticky="ew",
                pady=(7, 7),
            )
            row = self._source_group(
                frame,
                row=row + 1,
                title="HOLD — zablokowane; nie można uruchomić",
                sources=HOLD_SOURCES,
                disabled=True,
            )
            ttk.Label(
                frame,
                text=(
                    "Pracuj.pl / OLX / theprotocol / Bulldogjob pozostają widoczne, "
                    "ale są wyłączone do czasu pozytywnej ponownej weryfikacji dostępu."
                ),
                wraplength=1000,
                justify="left",
            ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(3, 0))
            row += 1
            ttk.Separator(frame).grid(
                row=row,
                column=0,
                columnspan=4,
                sticky="ew",
                pady=(7, 7),
            )
            row = self._source_group(
                frame,
                row=row + 1,
                title="Partner/API — wymagają danych dostępowych",
                sources=CREDENTIAL_SOURCES,
            )

            buttons = ttk.Frame(frame)
            buttons.grid(row=row, column=0, columnspan=4, sticky="w", pady=(10, 0))
            ttk.Button(buttons, text="Tylko zweryfikowane", command=self._select_verified).pack(
                side="left"
            )
            ttk.Button(buttons, text="Zaznacz dostępne", command=self._select_available).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(buttons, text="Wyczyść", command=self._clear_all).pack(
                side="left", padx=(6, 0)
            )

            options = ttk.LabelFrame(
                parent,
                text="Ustawienia Etapu 1",
                padding=12,
                style="Section.TLabelframe",
            )
            options.grid(row=3, column=0, sticky="ew", pady=(10, 0))
            options.columnconfigure(1, weight=1)
            ttk.Label(options, text="Strony / batche na źródło:").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Spinbox(
                options,
                from_=1,
                to=1000,
                textvariable=self.pages_var,
                width=9,
            ).grid(row=0, column=1, sticky="w", padx=(10, 20))
            ttk.Checkbutton(
                options,
                text="Zacznij źródła od początku",
                variable=self.fresh_var,
            ).grid(row=0, column=2, sticky="w")
            ttk.Checkbutton(
                options,
                text="Strict — błąd aktywnego źródła kończy etap kodem błędu",
                variable=self.collection_strict_var,
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
            self._database_row(options, row=2, label="Baza ofert / firm:")

            actions = ttk.Frame(parent)
            actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
            self.collect_button = ttk.Button(
                actions,
                text="▶  ETAP 1 — POBIERZ OFERTY",
                command=self._start_collection,
                style="Primary.TButton",
            )
            self.collect_button.pack(side="left", fill="x", expand=True)
            ttk.Button(
                actions,
                text="Kopiuj polecenie",
                command=self._copy_collection_command,
            ).pack(side="left", padx=(8, 0))

        def _build_contact_tab(self, parent: object) -> None:
            parent.columnconfigure(0, weight=1)
            ttk.Label(
                parent,
                text="Etap 2 — wyszukiwanie kontaktów biznesowych",
                style="Step.TLabel",
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                parent,
                text=(
                    "Ten etap nie pobiera nowych ofert. Otwiera bazę z Etapu 1, "
                    "identyfikuje oficjalne strony firm, klasyfikuje kanały "
                    "GREEN / REVIEW / IGNORE i tworzy Excel."
                ),
                wraplength=1050,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(3, 12))

            settings = ttk.LabelFrame(
                parent,
                text="Ustawienia Etapu 2",
                padding=12,
                style="Section.TLabelframe",
            )
            settings.grid(row=2, column=0, sticky="ew")
            settings.columnconfigure(1, weight=1)
            self._database_row(settings, row=0, label="Baza z Etapu 1:")

            ttk.Label(settings, text="Końcowy Excel:").grid(
                row=1, column=0, sticky="w", pady=(8, 0)
            )
            output_row = ttk.Frame(settings)
            output_row.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 0))
            output_row.columnconfigure(0, weight=1)
            ttk.Entry(output_row, textvariable=self.output_var).grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Button(output_row, text="…", width=3, command=self._choose_output).grid(
                row=0, column=1, padx=(5, 0)
            )

            ttk.Label(settings, text="Limit firm w jednym przebiegu:").grid(
                row=2, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Spinbox(
                settings,
                from_=1,
                to=500,
                textvariable=self.enrichment_var,
                width=9,
            ).grid(row=2, column=1, sticky="w", pady=(8, 0))
            ttk.Checkbutton(
                settings,
                text="Odśwież także firmy analizowane wcześniej",
                variable=self.refresh_var,
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Checkbutton(
                settings,
                text="Strict — błąd enrichmentu kończy etap kodem błędu",
                variable=self.contact_strict_var,
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))
            ttk.Label(settings, text="Brave Search API key (opcjonalny):").grid(
                row=5, column=0, sticky="w", pady=(10, 0)
            )
            ttk.Entry(settings, textvariable=self.brave_key_var, show="•").grid(
                row=5, column=1, sticky="ew", pady=(10, 0)
            )
            ttk.Label(
                settings,
                text=(
                    "Bez klucza system nadal sprawdza strony WWW podane przez źródła; "
                    "klucz włącza fallback wyszukiwania oficjalnej strony firmy."
                ),
                wraplength=800,
                justify="left",
            ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))

            actions = ttk.Frame(parent)
            actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
            self.contact_button = ttk.Button(
                actions,
                text="▶  ETAP 2 — ZNAJDŹ KONTAKTY I UTWÓRZ EXCEL",
                command=self._start_contacts,
                style="Primary.TButton",
            )
            self.contact_button.pack(side="left", fill="x", expand=True)
            ttk.Button(
                actions,
                text="Kopiuj polecenie",
                command=self._copy_contact_command,
            ).pack(side="left", padx=(8, 0))
            ttk.Button(
                actions,
                text="Otwórz folder wyników",
                command=self._open_output_folder,
            ).pack(side="left", padx=(8, 0))

        def _database_row(self, parent: object, *, row: int, label: str) -> None:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(8, 0))
            db_row = ttk.Frame(parent)
            db_row.grid(row=row, column=1, columnspan=2, sticky="ew", pady=(8, 0))
            db_row.columnconfigure(0, weight=1)
            ttk.Entry(db_row, textvariable=self.database_var).grid(row=0, column=0, sticky="ew")
            ttk.Button(db_row, text="…", width=3, command=self._choose_database).grid(
                row=0, column=1, padx=(5, 0)
            )

        def _build_log_panel(self, parent: object) -> None:
            status_frame = ttk.Frame(parent)
            status_frame.pack(fill="x", pady=(12, 6))
            ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")
            self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=190)
            self.progress.pack(side="right")

            log_frame = ttk.LabelFrame(
                parent,
                text="Log bieżącego etapu",
                padding=8,
                style="Section.TLabelframe",
            )
            log_frame.pack(fill="both", expand=False)
            self.log = tk.Text(
                log_frame,
                height=11,
                wrap="word",
                state="disabled",
                font=("Consolas", 9),
                padx=8,
                pady=8,
            )
            scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
            self.log.configure(yscrollcommand=scrollbar.set)
            self.log.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            controls = ttk.Frame(parent)
            controls.pack(fill="x", pady=(6, 0))
            self.stop_button = ttk.Button(
                controls,
                text="■  Zatrzymaj bieżący etap",
                command=self._stop,
                state="disabled",
            )
            self.stop_button.pack(side="left")
            ttk.Button(controls, text="Wyczyść log", command=self._clear_log).pack(
                side="left", padx=(6, 0)
            )
            self._append_log(
                "Gotowy. HOLD są zablokowane w GUI i dodatkowo pomijane w backendzie. "
                "Najpierw uruchom Etap 1.\n"
            )

        def _select_verified(self) -> None:
            for source, variable in self.source_vars.items():
                variable.set(source in VERIFIED_SOURCES)

        def _select_available(self) -> None:
            available = set(selectable_sources())
            for source, variable in self.source_vars.items():
                variable.set(source in available)

        def _clear_all(self) -> None:
            for variable in self.source_vars.values():
                variable.set(False)

        def _selected_sources(self) -> tuple[str, ...]:
            allowed = set(selectable_sources())
            return tuple(
                source
                for source in VERIFIED_SOURCES + CREDENTIAL_SOURCES
                if source in allowed and self.source_vars[source].get()
            )

        def _collection_config(self) -> CollectionConfig:
            return CollectionConfig(
                sources=self._selected_sources(),
                pages_per_source=int(self.pages_var.get()),
                database_path=Path(self.database_var.get()).expanduser(),
                fresh_sources=self.fresh_var.get(),
                strict=self.collection_strict_var.get(),
            )

        def _contact_config(self) -> ContactConfig:
            return ContactConfig(
                database_path=Path(self.database_var.get()).expanduser(),
                output_path=Path(self.output_var.get()).expanduser(),
                enrichment_limit=int(self.enrichment_var.get()),
                refresh_enrichment=self.refresh_var.get(),
                strict=self.contact_strict_var.get(),
            )

        def _choose_database(self) -> None:
            selected = filedialog.asksaveasfilename(
                initialfile=Path(self.database_var.get()).name,
                initialdir=str(Path(self.database_var.get()).parent),
                defaultextension=".sqlite3",
                filetypes=[("SQLite", "*.sqlite3 *.sqlite *.db"), ("Wszystkie", "*.*")],
            )
            if selected:
                self.database_var.set(selected)

        def _choose_output(self) -> None:
            selected = filedialog.asksaveasfilename(
                initialfile=Path(self.output_var.get()).name,
                initialdir=str(Path(self.output_var.get()).parent),
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
            )
            if selected:
                self.output_var.set(selected)

        def _start_collection(self) -> None:
            if self.process is not None:
                return
            try:
                config = self._collection_config()
                command = build_collection_command(config)
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja Etapu 1", str(exc))
                return
            config.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._start_process(command, "Etap 1 — scraping ofert")

        def _start_contacts(self) -> None:
            if self.process is not None:
                return
            try:
                config = self._contact_config()
                command = build_contact_command(config)
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja Etapu 2", str(exc))
                return
            if not config.database_path.exists():
                messagebox.showerror(
                    "Brak bazy",
                    "Nie znaleziono bazy z Etapu 1. Najpierw pobierz oferty.",
                )
                return
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            env: dict[str, str] = {}
            brave_key = self.brave_key_var.get().strip()
            if brave_key:
                env["BRAVE_SEARCH_API_KEY"] = brave_key
            self._start_process(command, "Etap 2 — wyszukiwanie kontaktów", extra_env=env)

        def _start_process(
            self,
            command: list[str],
            stage_label: str,
            *,
            extra_env: dict[str, str] | None = None,
        ) -> None:
            self._append_log(f"\n=== {stage_label.upper()} ===\n")
            self._append_log(_quote_command(command) + "\n\n")
            self.status_var.set(stage_label + " — w toku…")
            self.active_stage = stage_label
            self.collect_button.configure(state="disabled")
            self.contact_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.progress.start(12)

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process_env = os.environ.copy()
            if extra_env:
                process_env.update(extra_env)
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                    env=process_env,
                )
            except OSError as exc:
                self.process = None
                self._finish_run(1, f"Nie udało się uruchomić procesu: {exc}")
                return
            threading.Thread(target=self._read_process_output, daemon=True).start()

        def _read_process_output(self) -> None:
            process = self.process
            if process is None:
                return
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(("log", line))
            self.events.put(("exit", process.wait()))

        def _poll_events(self) -> None:
            while True:
                try:
                    kind, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "exit":
                    self._finish_run(int(payload))
            self.root.after(100, self._poll_events)

        def _finish_run(self, code: int, detail: str | None = None) -> None:
            stage = self.active_stage or "Etap"
            self.progress.stop()
            self.collect_button.configure(state="normal")
            self.contact_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.process = None
            self.active_stage = None
            if detail:
                self._append_log(detail + "\n")
            if code == 0:
                self.status_var.set(stage + " — zakończony sukcesem")
                self._append_log("\n=== GOTOWE ===\n")
            else:
                self.status_var.set(f"{stage} — kod {code}")
                self._append_log(f"\n=== ZAKOŃCZONO KODEM {code} ===\n")

        def _stop(self) -> None:
            if self.process is None:
                return
            self.status_var.set("Zatrzymywanie…")
            with contextlib.suppress(OSError):
                self.process.terminate()

        def _copy_collection_command(self) -> None:
            try:
                command = build_collection_command(self._collection_config())
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja Etapu 1", str(exc))
                return
            self._copy_to_clipboard(_quote_command(command), "Polecenie Etapu 1 skopiowane")

        def _copy_contact_command(self) -> None:
            try:
                command = build_contact_command(self._contact_config())
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja Etapu 2", str(exc))
                return
            self._copy_to_clipboard(_quote_command(command), "Polecenie Etapu 2 skopiowane")

        def _copy_to_clipboard(self, text: str, status: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_var.set(status)

        def _open_output_folder(self) -> None:
            folder = Path(self.output_var.get()).expanduser().parent
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])

        def _append_log(self, text: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")

        def _clear_log(self) -> None:
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")

        def _on_close(self) -> None:
            if self.process is not None:
                if not messagebox.askyesno(
                    "Proces trwa",
                    "Bieżący etap nadal trwa. Zatrzymać go i zamknąć program?",
                ):
                    return
                with contextlib.suppress(OSError):
                    self.process.terminate()
            self.root.destroy()

    root = tk.Tk()
    FaroGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
