from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCES = (
    "aplikuj",
    "justjoinit",
    "karierawfinansach",
    "manpower",
    "ngo",
    "nofluffjobs",
    "ofertypracyedu",
    "rocketjobs",
    "skillshot",
)


@dataclass(frozen=True)
class RunConfig:
    sources: tuple[str, ...]
    pages_per_source: int
    enrichment_limit: int
    database_path: Path
    output_path: Path
    fresh_sources: bool = True
    refresh_enrichment: bool = False
    strict: bool = True


def validate_run_config(config: RunConfig) -> None:
    if not config.sources:
        raise ValueError("Wybierz co najmniej jedno źródło.")
    if not 1 <= config.pages_per_source <= 1000:
        raise ValueError("Liczba stron na źródło musi być w zakresie 1–1000.")
    if not 1 <= config.enrichment_limit <= 500:
        raise ValueError("Limit enrichmentu musi być w zakresie 1–500.")
    if config.output_path.suffix.lower() != ".xlsx":
        raise ValueError("Plik wynikowy musi mieć rozszerzenie .xlsx.")
    if config.database_path.suffix.lower() not in {".sqlite3", ".sqlite", ".db"}:
        raise ValueError("Baza powinna mieć rozszerzenie .sqlite3, .sqlite albo .db.")


def _default_runner_python() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        console_python = executable.with_name("python.exe")
        if console_python.exists():
            return str(console_python)
    return str(executable)


def build_run_command(
    config: RunConfig,
    *,
    python_executable: str | None = None,
) -> list[str]:
    validate_run_config(config)
    executable = python_executable or _default_runner_python()
    command = [
        executable,
        "-m",
        "agregator.workflow_cli",
        "run",
        "--sources",
        ",".join(config.sources),
        "--pages-per-source",
        str(config.pages_per_source),
        "--enrichment-limit",
        str(config.enrichment_limit),
        "--db",
        str(config.database_path),
        "--output",
        str(config.output_path),
    ]
    if config.fresh_sources:
        command.append("--fresh-sources")
    if config.refresh_enrichment:
        command.append("--refresh-enrichment")
    if config.strict:
        command.append("--strict")
    return command


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
            self.root.title("Faro Emaile — Employer Discovery")
            self.root.geometry("1100x760")
            self.root.minsize(920, 680)

            self.process: subprocess.Popen[str] | None = None
            self.events: queue.Queue[tuple[str, object]] = queue.Queue()

            self.source_vars = {
                source: tk.BooleanVar(value=True) for source in DEFAULT_SOURCES
            }
            self.pages_var = tk.IntVar(value=5)
            self.enrichment_var = tk.IntVar(value=300)
            self.output_dir_var = tk.StringVar(value=str(default_output_dir))
            self.xlsx_name_var = tk.StringVar(value="Faro_Firmy_Kontakt.xlsx")
            self.db_name_var = tk.StringVar(value="production.sqlite3")
            self.fresh_var = tk.BooleanVar(value=True)
            self.refresh_var = tk.BooleanVar(value=False)
            self.strict_var = tk.BooleanVar(value=True)
            self.status_var = tk.StringVar(value="Gotowy")

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
            style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            style.configure(
                "Primary.TButton",
                font=("Segoe UI", 10, "bold"),
                padding=(14, 8),
            )

        def _build_ui(self) -> None:
            outer = ttk.Frame(self.root, padding=18)
            outer.pack(fill="both", expand=True)

            ttk.Label(outer, text="Faro Emaile", style="Title.TLabel").pack(anchor="w")
            ttk.Label(
                outer,
                text=(
                    "Zbieranie ofert → rozpoznanie firm → oficjalne WWW → "
                    "kontakty biznesowe → Excel"
                ),
                style="Subtitle.TLabel",
            ).pack(anchor="w", pady=(2, 14))

            body = ttk.Frame(outer)
            body.pack(fill="both", expand=True)
            body.columnconfigure(0, weight=0)
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)

            left = ttk.Frame(body)
            left.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
            right = ttk.Frame(body)
            right.grid(row=0, column=1, sticky="nsew")
            right.rowconfigure(1, weight=1)
            right.columnconfigure(0, weight=1)

            sources_frame = ttk.LabelFrame(
                left,
                text="Źródła",
                padding=12,
                style="Section.TLabelframe",
            )
            sources_frame.pack(fill="x")
            for index, source in enumerate(DEFAULT_SOURCES):
                row = index // 2
                column = index % 2
                ttk.Checkbutton(
                    sources_frame,
                    text=source,
                    variable=self.source_vars[source],
                ).grid(row=row, column=column, sticky="w", padx=(0, 14), pady=3)

            source_buttons = ttk.Frame(sources_frame)
            source_buttons.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Button(source_buttons, text="Zaznacz wszystkie", command=self._select_all).pack(
                side="left"
            )
            ttk.Button(source_buttons, text="Wyczyść", command=self._clear_all).pack(
                side="left", padx=(6, 0)
            )

            settings = ttk.LabelFrame(
                left,
                text="Zakres skanowania",
                padding=12,
                style="Section.TLabelframe",
            )
            settings.pack(fill="x", pady=(12, 0))
            ttk.Label(settings, text="Strony / batche na źródło:").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Spinbox(
                settings,
                from_=1,
                to=1000,
                textvariable=self.pages_var,
                width=9,
            ).grid(row=0, column=1, sticky="e", padx=(12, 0))
            ttk.Label(settings, text="Limit firm do enrichmentu:").grid(
                row=1, column=0, sticky="w", pady=(8, 0)
            )
            ttk.Spinbox(
                settings,
                from_=1,
                to=500,
                textvariable=self.enrichment_var,
                width=9,
            ).grid(row=1, column=1, sticky="e", padx=(12, 0), pady=(8, 0))

            ttk.Checkbutton(
                settings,
                text="Zacznij źródła od początku",
                variable=self.fresh_var,
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
            ttk.Checkbutton(
                settings,
                text="Odśwież wcześniej wzbogacone firmy",
                variable=self.refresh_var,
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
            ttk.Checkbutton(
                settings,
                text="Tryb strict — błąd źródła = błąd runu",
                variable=self.strict_var,
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

            output = ttk.LabelFrame(
                left,
                text="Wyniki",
                padding=12,
                style="Section.TLabelframe",
            )
            output.pack(fill="x", pady=(12, 0))
            ttk.Label(output, text="Folder:").grid(row=0, column=0, sticky="w")
            folder_row = ttk.Frame(output)
            folder_row.grid(row=1, column=0, sticky="ew", pady=(3, 8))
            ttk.Entry(folder_row, textvariable=self.output_dir_var, width=37).pack(
                side="left", fill="x", expand=True
            )
            ttk.Button(
                folder_row,
                text="…",
                width=3,
                command=self._choose_folder,
            ).pack(side="left", padx=(5, 0))

            ttk.Label(output, text="Excel:").grid(row=2, column=0, sticky="w")
            ttk.Entry(output, textvariable=self.xlsx_name_var, width=42).grid(
                row=3, column=0, sticky="ew", pady=(3, 8)
            )
            ttk.Label(output, text="Baza SQLite:").grid(row=4, column=0, sticky="w")
            ttk.Entry(output, textvariable=self.db_name_var, width=42).grid(
                row=5, column=0, sticky="ew", pady=(3, 0)
            )

            actions = ttk.Frame(left)
            actions.pack(fill="x", pady=(14, 0))
            self.start_button = ttk.Button(
                actions,
                text="▶  Uruchom skanowanie",
                command=self._start,
                style="Primary.TButton",
            )
            self.start_button.pack(fill="x")
            self.stop_button = ttk.Button(
                actions,
                text="■  Zatrzymaj",
                command=self._stop,
                state="disabled",
            )
            self.stop_button.pack(fill="x", pady=(6, 0))
            ttk.Button(
                actions,
                text="Otwórz folder wyników",
                command=self._open_output_folder,
            ).pack(fill="x", pady=(6, 0))
            ttk.Button(
                actions,
                text="Kopiuj polecenie",
                command=self._copy_command,
            ).pack(fill="x", pady=(6, 0))

            status_frame = ttk.Frame(right)
            status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            status_frame.columnconfigure(0, weight=1)
            ttk.Label(status_frame, textvariable=self.status_var).grid(
                row=0, column=0, sticky="w"
            )
            self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=180)
            self.progress.grid(row=0, column=1, sticky="e")

            log_frame = ttk.LabelFrame(
                right,
                text="Log",
                padding=8,
                style="Section.TLabelframe",
            )
            log_frame.grid(row=1, column=0, sticky="nsew")
            log_frame.rowconfigure(0, weight=1)
            log_frame.columnconfigure(0, weight=1)

            self.log = tk.Text(
                log_frame,
                wrap="word",
                state="disabled",
                font=("Consolas", 9),
                padx=8,
                pady=8,
            )
            scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
            self.log.configure(yscrollcommand=scrollbar.set)
            self.log.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")

            self._append_log(
                "Gotowy. Domyślnie wybrane jest 9 zweryfikowanych źródeł produkcyjnych.\n"
            )

        def _select_all(self) -> None:
            for variable in self.source_vars.values():
                variable.set(True)

        def _clear_all(self) -> None:
            for variable in self.source_vars.values():
                variable.set(False)

        def _choose_folder(self) -> None:
            selected = filedialog.askdirectory(
                initialdir=self.output_dir_var.get() or str(Path.cwd())
            )
            if selected:
                self.output_dir_var.set(selected)

        def _selected_sources(self) -> tuple[str, ...]:
            return tuple(
                source for source in DEFAULT_SOURCES if self.source_vars[source].get()
            )

        def _current_config(self) -> RunConfig:
            output_dir = Path(self.output_dir_var.get()).expanduser()
            return RunConfig(
                sources=self._selected_sources(),
                pages_per_source=int(self.pages_var.get()),
                enrichment_limit=int(self.enrichment_var.get()),
                database_path=output_dir / self.db_name_var.get().strip(),
                output_path=output_dir / self.xlsx_name_var.get().strip(),
                fresh_sources=self.fresh_var.get(),
                refresh_enrichment=self.refresh_var.get(),
                strict=self.strict_var.get(),
            )

        def _start(self) -> None:
            if self.process is not None:
                return
            try:
                config = self._current_config()
                command = build_run_command(config)
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja", str(exc))
                return

            config.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._append_log("\n=== NOWY RUN ===\n")
            self._append_log(_quote_command(command) + "\n\n")
            self.status_var.set("Skanowanie w toku…")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.progress.start(12)

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

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
            code = process.wait()
            self.events.put(("exit", code))

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
            self.progress.stop()
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.process = None
            if detail:
                self._append_log(detail + "\n")
            if code == 0:
                self.status_var.set("Gotowe — run zakończony sukcesem")
                self._append_log("\n=== GOTOWE ===\n")
            else:
                self.status_var.set(f"Run zakończony kodem {code}")
                self._append_log(f"\n=== ZAKOŃCZONO KODEM {code} ===\n")

        def _stop(self) -> None:
            process = self.process
            if process is None:
                return
            self.status_var.set("Zatrzymywanie…")
            self._append_log("\nŻądanie zatrzymania procesu…\n")
            try:
                process.terminate()
            except OSError as exc:
                self._append_log(f"Nie udało się zatrzymać procesu: {exc}\n")

        def _open_output_folder(self) -> None:
            folder = Path(self.output_dir_var.get()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])

        def _copy_command(self) -> None:
            try:
                command = build_run_command(self._current_config())
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Nieprawidłowa konfiguracja", str(exc))
                return
            text = _quote_command(command)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_var.set("Polecenie skopiowane do schowka")

        def _append_log(self, text: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")

        def _on_close(self) -> None:
            if self.process is not None:
                if not messagebox.askyesno(
                    "Skanowanie trwa",
                    "Skanowanie nadal trwa. Zatrzymać je i zamknąć program?",
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
