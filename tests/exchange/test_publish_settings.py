from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.db import Instance, InstanceRepository, connect, init_gui_database
from ig_orchestrator.exchange.publish import read_publish_settings, write_publish_settings

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_auto_publish_requires_a_local_worker_instance(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)

    assert read_publish_settings(conn) == (False, "MOVE")  # defaults

    write_publish_settings(conn, True, "COPY")
    assert read_publish_settings(conn) == (False, "COPY")  # no local instance yet

    repo = InstanceRepository(conn)
    main = repo.save(Instance(None, "pc1", "MAIN", is_local=True))
    assert read_publish_settings(conn)[0] is False  # a MAIN instance never auto-publishes

    repo.save(Instance(main, "pc1", "WORKER", is_local=True))
    assert read_publish_settings(conn) == (True, "COPY")

    write_publish_settings(conn, False, "bogus")
    assert read_publish_settings(conn) == (False, "MOVE")  # invalid mode falls back to MOVE
    conn.close()


def test_publish_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith(("publish.", "pull.pkg.")) or k in {
        "menu.batch.publish", "batches.elsewhere_warning", "settings.instances.auto_publish",
        "settings.instances.publish_mode", "settings.instances.publish_hint"}}
    assert len(keys) >= 20 and keys <= set(en)
