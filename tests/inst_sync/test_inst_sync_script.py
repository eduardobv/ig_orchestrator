"""inst_sync/sync.py: mirror with protected instance data, SQL once, changes manifest."""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

SYNC = Path(__file__).resolve().parents[2] / "inst_sync" / "sync.py"
spec = importlib.util.spec_from_file_location("inst_sync_script", SYNC)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def _write(root: Path, rel: str, text: str = "x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def pair(tmp_path):
    source, target = tmp_path / "pc1", tmp_path / "inst1"
    for root in (source, target):
        _write(root, "src/ig_orchestrator/__init__.py", '__version__ = "1.0.0"\n')
    return source, target


def test_plan_copies_changed_and_new_and_deletes_removed(pair):
    source, target = pair
    _write(source, "src/ig_orchestrator/__init__.py", '__version__ = "1.1.0"\n')
    _write(source, "src/ig_orchestrator/new.py")
    _write(target, "src/ig_orchestrator/old.py")
    plan = sync.plan_mirror(source, target)
    assert Path("src/ig_orchestrator/new.py") in plan["copy"]
    assert Path("src/ig_orchestrator/__init__.py") in plan["copy"]
    assert plan["delete"] == [Path("src/ig_orchestrator/old.py")]
    sync.apply_mirror(source, target, plan)
    assert sync.installed_version(target) == "1.1.0"
    assert not (target / "src/ig_orchestrator/old.py").exists()
    assert sync.plan_mirror(source, target) == {"copy": [], "delete": []}


def test_instance_owned_data_is_never_touched(pair):
    source, target = pair
    for rel in (".env", "data/orchestrator_gui.sqlite", "telegram_user_session.session", "logs/a.log"):
        _write(target, rel, "mine")
    _write(source, ".env", "other")
    _write(target, "inst_sync/origen.txt", "mine")
    _write(target, "inst_sync/estado.json", "{}")
    _write(target, "inst_sync/bkp/src_old/a.py")
    _write(source, "inst_sync/sincronizar.bat", "new launcher")
    plan = sync.plan_mirror(source, target)
    sync.apply_mirror(source, target, plan)
    assert (target / ".env").read_text() == "mine"
    assert (target / "data/orchestrator_gui.sqlite").exists()
    assert (target / "inst_sync/origen.txt").read_text() == "mine"
    assert (target / "inst_sync/estado.json").exists()
    assert (target / "inst_sync/bkp/src_old/a.py").exists()
    assert not (target / "inst_sync/sincronizar.bat").exists()


def test_pycache_ignored_and_empty_dirs_removed(pair):
    source, target = pair
    _write(source, "src/ig_orchestrator/__pycache__/m.pyc")
    _write(target, "src/ig_orchestrator/gone/a.py")
    plan = sync.plan_mirror(source, target)
    assert all("__pycache__" not in str(p) for p in plan["copy"])
    sync.apply_mirror(source, target, plan)
    assert not (target / "src/ig_orchestrator/gone").exists()


def test_backup_keeps_only_latest_three(pair):
    _, target = pair
    for i in range(5):
        sync.backup_code(target, "1.0.0", datetime(2026, 1, 1, 0, 0, i))
    kept = sorted(p.name for p in (target / "inst_sync/bkp").iterdir())
    assert len(kept) == 3 and kept[-1].endswith("000004")


def test_pending_changes_only_newer_versions():
    text = "# t\n\n## v4.18.0 · a\nuno\n\n## v4.17.0 · b\ndos\n\n## v4.4.0 · c\ntres\n"
    got = sync.pending_changes(text, "4.17.0")
    assert [v for v, _ in got] == ["4.18.0"]
    assert [v for v, _ in sync.pending_changes(text, "4.4.0")] == ["4.18.0", "4.17.0"]
    assert sync.pending_changes(text, "4.18.0") == []


def test_sql_applied_once(tmp_path):
    sql_dir = tmp_path / "sql"
    _write(tmp_path, "sql/001_t.sql", "CREATE TABLE t(a);")
    _write(tmp_path, "sql/002_i.sql", "INSERT INTO t VALUES (1);")
    db = tmp_path / "d.sqlite"
    sqlite3.connect(db).close()
    scripts = sync.pending_sql(sql_dir, [])
    done = sync.apply_sql(db, scripts)
    assert done == ["001_t.sql", "002_i.sql"]
    assert sync.pending_sql(sql_dir, done) == []
    assert sqlite3.connect(db).execute("select a from t").fetchall() == [(1,)]


def test_source_from_file_and_missing(tmp_path):
    (tmp_path / "origen.txt").write_text("# c" + chr(10) + "X:/pc1/proj" + chr(10), encoding="utf-8")
    assert sync.read_source(tmp_path, None) == Path("X:/pc1/proj")
    assert sync.read_source(tmp_path, "X:/p") == Path("X:/p")
    empty = tmp_path / "e"
    empty.mkdir()
    with pytest.raises(SystemExit):
        sync.read_source(empty, None)


def test_main_simulation_changes_nothing(pair, capsys):
    source, target = pair
    _write(source, "src/ig_orchestrator/__init__.py", '__version__ = "1.2.0"\n')
    _write(source, "src/ig_orchestrator/x.py")
    code = sync.main(["--origen", str(source), "--destino", str(target), "--simular"])
    assert code == 0
    assert sync.installed_version(target) == "1.0.0"
    assert "Simulación" in capsys.readouterr().out
