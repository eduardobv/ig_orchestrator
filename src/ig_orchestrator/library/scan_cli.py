"""CLI glue for ``scan``: opens bdapp, runs the scanner and prints the result."""

from __future__ import annotations

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.scanner import ACCOUNT, ALL, CATEGORY, LibraryScanner, ScanError
from ig_orchestrator.settings import SettingsError, load_settings


def run_scan_cli(scope: str, path: str, account: str, deep: bool) -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot scan: {exc}")
        return 2
    init_gui_database(settings.sqlite_gui_db_path)
    connection = connect(settings.sqlite_gui_db_path)
    try:
        scanner = LibraryScanner(connection)
        kwargs: dict = {"deep": deep}
        if scope == "category":
            if not path:
                print("--scope category needs --path REL (e.g. 00.FAVORITES)")
                return 2
            kwargs.update(scope=CATEGORY, rel_scope=path.strip("\\/"))
        elif scope == "account":
            row = connection.execute(
                "SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (account,)
            ).fetchone()
            if row is None:
                print(f"Account not found: {account!r}")
                return 2
            kwargs.update(scope=ACCOUNT, account_id=int(row[0]))
        else:
            kwargs.update(scope=ALL)
        scope_arg = kwargs.pop("scope")
        try:
            report = scanner.scan(scope_arg, **kwargs)
        except ScanError as exc:
            print(f"Scan failed: {exc}")
            return 2
    finally:
        connection.close()
    print(report.summary())
    for finding in report.findings[:200]:
        print(f"  {finding.kind:15} {finding.rel_path}  {finding.detail}")
    return 0
