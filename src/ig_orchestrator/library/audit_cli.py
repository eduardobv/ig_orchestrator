"""CLI glue for ``audit-library``: resolves default paths and writes reports."""

from __future__ import annotations

import os
from pathlib import Path

from ig_orchestrator.db import connect_readonly
from ig_orchestrator.library.audit import run_audit
from ig_orchestrator.library.audit_report import render_csv, render_markdown
from ig_orchestrator.settings import SettingsError, load_settings

STORIES_DB_SETTING = "stories.accounts_db_path"


def native_path_text(value: str) -> str:
    """Path text as the OS writes it (backslashes on Windows); '' stays ''."""

    text = value.strip()
    return os.path.normpath(text) if text else ""


def default_complete_path(lite_path: Path) -> Path:
    return lite_path.with_name("accounts_complete.sqlite")


def run_audit_cli(
    lite: Path | None,
    complete: Path | None,
    md_path: Path | None,
    csv_path: Path | None,
    no_disk: bool,
) -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot run audit: {exc}")
        return 2
    gui_path = settings.sqlite_gui_db_path
    if not gui_path.exists():
        print(f"bdapp not found: {gui_path}")
        return 2
    connection = connect_readonly(gui_path)
    try:
        if lite is None:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?", (STORIES_DB_SETTING,)
            ).fetchone()
            if row is None or not row[0]:
                print("No --lite given and 'stories.accounts_db_path' is not configured.")
                return 2
            lite = Path(native_path_text(row[0]))
        if complete is None:
            complete = default_complete_path(lite)
        report = run_audit(connection, lite, complete, check_disk=not no_disk)
    finally:
        connection.close()

    for note in report.notes:
        print(f"! {note}")
    for code, count in report.summary().items():
        print(f"{code:22} {count}")
    if md_path is not None:
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Markdown: {md_path}")
    if csv_path is not None:
        csv_path.write_text(render_csv(report), encoding="utf-8")
        print(f"CSV: {csv_path}")
    return 0
