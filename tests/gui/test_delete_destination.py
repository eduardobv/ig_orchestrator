from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.library.delete_destination_dialog import destination_rows
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.fsops import FsOperationService

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_destination_rows_show_suggestion_and_reason(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    (lib / "00.FAVORITES/Group/alice").mkdir(parents=True)
    (lib / "00.FAVORITES/Group-Deleted").mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.FAVORITES\\Group-Deleted")
    account = conn.execute(
        "INSERT INTO catalog_accounts (username, status_id, created_at, updated_at, rel_path)"
        " VALUES ('alice', 1, 'x', 'x', '00.FAVORITES\\Group\\alice')"
    ).lastrowid
    conn.commit()
    service = AccountLifecycleService(conn)

    suggested = destination_rows(service, [account], service.plan_mark_deleted([account]))
    custom = destination_rows(
        service, [account], service.plan_mark_deleted([account], dest_overrides={account: "09.DELETED"})
    )

    assert suggested[0][3] == "00.FAVORITES\\Group-Deleted" and "-Deleted" in suggested[0][4]
    assert custom[0][3] == "09.DELETED"
    conn.close()


def test_destination_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith(("life.dest", "life.reason.", "picker."))}
    assert len(keys) >= 14 and keys <= set(en)
