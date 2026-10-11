"""CLI glue for ``import-bdsc1``: resolves defaults, backs up and runs the import."""

from __future__ import annotations

from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.db.gui_migrations import backup_database
from ig_orchestrator.library.audit_cli import default_complete_path, native_path_text
from ig_orchestrator.library.import_bdsc1 import LibraryImportError, import_from_bdsc1
from ig_orchestrator.settings import SettingsError, load_settings

STORIES_DB_SETTING = "stories.accounts_db_path"


def run_import_cli(
    lite: Path | None,
    complete: Path | None,
    root: str | None,
    dry_run: bool,
    include_media: bool,
) -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot import: {exc}")
        return 2
    gui_path = settings.sqlite_gui_db_path
    init_gui_database(gui_path)
    connection = connect(gui_path)
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
            candidate = default_complete_path(lite)
            complete = candidate if candidate.is_file() else None
        if not dry_run:
            backup = backup_database(connection, "pre_import")
            if backup is not None:
                print(f"Backup: {backup}")
        try:
            report = import_from_bdsc1(
                connection,
                lite,
                complete,
                dry_run=dry_run,
                include_media=include_media,
                library_root=root,
            )
        except LibraryImportError as exc:
            print(f"Import failed: {exc}")
            return 2
    finally:
        connection.close()
    print(report.render())
    return 0
