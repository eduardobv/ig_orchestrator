from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ig_orchestrator.db import AccountHistoryRepository, connect, init_gui_database
from ig_orchestrator.library.filenames import parse_media_name
from ig_orchestrator.library.import_bdsc1 import LibraryImportError, import_from_bdsc1
from ig_orchestrator.library.paths import parent_rel, rel_key, to_abs, to_rel
from ig_orchestrator.models import AccountHistoryStatus

ROOT = r"G:\4K Stogram"


def _name(day: str, media_id: int, owner: int, suffix: str = "", ext: str = "jpg") -> str:
    return f"{day} 10.00.00 {media_id}_{owner}{suffix}.{ext}"


def _make_lite(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE accounts_dir (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT,"
            " ownerId TEXT, path TEXT UNIQUE, last_modified TEXT, created_at TEXT, modified_at TEXT)"
        )
        conn.executemany("INSERT INTO accounts_dir (username, ownerId, path) VALUES (?,?,?)", rows)


def _make_complete(path: Path, rows: list[tuple], media: list[tuple[int, str, str]]) -> None:
    """rows: (username, ownerId, path, posts, reels, story, highlights, last_modified)."""

    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ownerId TEXT,"
            " path TEXT UNIQUE, posts INT, reels INT, story INT, highlights INT, last_modified TEXT)"
        )
        conn.execute("CREATE TABLE media (id INTEGER PRIMARY KEY AUTOINCREMENT, id_accounts INT,"
                     " username TEXT, filename TEXT, path TEXT, type TEXT)")
        conn.executemany(
            "INSERT INTO accounts (username, ownerId, path, posts, reels, story, highlights, last_modified)"
            " VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO media (id_accounts, username, filename, path, type) VALUES (?,?,?,?,?)",
            [(aid, "", fn, "", typ) for aid, fn, typ in media],
        )


@pytest.fixture()
def app(tmp_path: Path):
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    connection = connect(db)
    now = "2026-01-01T00:00:00"
    connection.execute(
        "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at)"
        f" VALUES (NULL, 'root', '{ROOT}', 0, '{now}', '{now}')"
    )
    connection.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (ROOT,))
    connection.commit()
    yield connection
    connection.close()


def _add_managed(app, username: str, owner: str | None, status: str, favorite: int = 0) -> int:
    now = "2026-01-01T00:00:00"
    cursor = app.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, status_id, is_favorite,"
        " start_init_date, created_at, updated_at)"
        " SELECT ?, ?, id, ?, '2026-03-01', ?, ? FROM catalog_account_statuses WHERE code = ?",
        (username, owner, favorite, now, now, status),
    )
    app.commit()
    return int(cursor.lastrowid)


def _sources(tmp_path: Path):
    lite = tmp_path / "lite.sqlite"
    complete = tmp_path / "complete.sqlite"
    _make_lite(
        lite,
        [
            ("alice", "1", ROOT + r"\00.FAVORITES\Alice\alice"),
            ("bob", "2", ROOT + r"\00.MODELS\bob"),
            ("carol", "3", ROOT + r"\00.MODELS\carol"),
            ("carol", "3", ROOT + r"\09.DELETED\carol"),  # same username elsewhere
            ("dave", "2", ROOT + r"\00.MODELS\dave"),  # same owner as bob
            ("eve", "5", r"D:\elsewhere\eve"),  # outside the library
        ],
    )
    _make_complete(
        complete,
        [
            ("alice", "1", ROOT + r"\00.FAVORITES\Alice\alice", 3, 2, 1, 0, "2026-02-01 10:00:00"),
            ("bob", "2", ROOT + r"\00.MODELS\bob", 1, 0, 0, 0, "2026-01-01 10:00:00"),
        ],
        [
            (1, _name("2026-02-01", 3001, 1), "POST"),
            (1, _name("2026-02-01", 3002, 1, "_manual", "mp4"), "REELS"),
            (1, _name("2026-02-02", 3003, 1, ext="jpeg"), "STORY"),
            (2, _name("2026-01-01", 4001, 2), "POST"),
            (2, "not-a-media-name.jpg", "POST"),
        ],
    )
    return lite, complete


def test_paths_and_filenames() -> None:
    assert to_rel(ROOT + r"\00.A\bob", ROOT) == r"00.A\bob"
    assert to_rel(r"g:\4k stogram\00.A", ROOT) == "00.A"
    assert to_rel(r"D:\other", ROOT) is None
    assert to_abs(r"00.A\bob", ROOT) == ROOT + r"\00.A\bob"
    assert parent_rel(r"00.A\bob") == "00.A" and parent_rel("00.A") == ""
    assert rel_key("00.A/Bob") == rel_key(r"00.a\bob")
    parsed = parse_media_name("2025-04-24 12.54.01 3660601494631376286_70238983807_manual.mp4")
    assert (parsed.media_id, parsed.owner_id, parsed.suffix, parsed.ext) == (
        3660601494631376286, 70238983807, "_manual", 2)
    assert parse_media_name("x.jpg") is None
    assert parse_media_name("2025-04-24 12.54.01 1_2.png") is None


def test_import_creates_archived_and_updates_existing(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    alice = _add_managed(app, "Alice", None, "ENABLED", favorite=1)

    report = import_from_bdsc1(app, lite, complete)

    rows = {
        r["username"].casefold(): r
        for r in app.execute(
            "SELECT a.*, s.code AS status FROM catalog_accounts a"
            " JOIN catalog_account_statuses s ON s.id = a.status_id"
        )
    }
    assert rows["alice"]["id"] == alice  # same primary key
    assert rows["alice"]["status"] == "ENABLED" and rows["alice"]["is_favorite"] == 1
    assert rows["alice"]["start_init_date"] == "2026-03-01"
    assert rows["alice"]["instagram_user_id"] == "1"  # filled because it was empty
    assert rows["alice"]["rel_path"] == r"00.FAVORITES\Alice\alice"
    assert (rows["alice"]["posts_count"], rows["alice"]["reels_count"]) == (3, 2)
    assert rows["alice"]["last_media_at"] == "2026-02-01 10:00:00"
    assert rows["bob"]["status"] == "ARCHIVED"
    assert rows["carol"]["rel_path"] == r"00.MODELS\carol"  # active category wins
    assert rows["eve"]["rel_path"] is None
    assert report.accounts_created == 4 and report.accounts_updated == 1
    assert report.issues["USERNAME_DUP"] == 1
    assert report.issues["OWNER_DUP"] == 1  # bob + dave
    assert report.issues["OUTSIDE_ROOT"] == 1
    kinds = {r["kind"] for r in app.execute("SELECT kind FROM library_import_issues")}
    assert {"USERNAME_DUP", "OWNER_DUP", "OUTSIDE_ROOT"} <= kinds


def test_import_builds_folder_tree_and_backfills_kind(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)

    import_from_bdsc1(app, lite, complete)

    folders = {r["rel_path"]: r for r in app.execute("SELECT * FROM catalog_folders")}
    assert folders[""]["parent_id"] is None
    assert folders["00.MODELS"]["kind"] == "CATEGORY"
    assert folders[r"00.FAVORITES\Alice"]["kind"] == "GROUP"
    assert folders[r"00.FAVORITES\Alice"]["parent_id"] == folders["00.FAVORITES"]["id"]
    assert folders["00.MODELS"]["full_path"] == ROOT + r"\00.MODELS"


def test_import_media_index_keyed_by_account_id(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)

    report = import_from_bdsc1(app, lite, complete)

    alice_id = app.execute("SELECT id FROM catalog_accounts WHERE username = 'alice'").fetchone()[0]
    rows = app.execute(
        "SELECT kind, media_id, owner_id, ext, suffix FROM media_index WHERE account_id = ?"
        " ORDER BY media_id",
        (alice_id,),
    ).fetchall()
    assert [tuple(r) for r in rows] == [(0, 3001, 1, 0, ""), (1, 3002, 1, 2, "_manual"), (2, 3003, 1, 1, "")]
    assert report.media_rows == 4 and report.media_unparsed == 1
    assert report.issues["PARSE_ERROR"] == 1
    columns = {r["name"] for r in app.execute("PRAGMA table_info(media_index)")}
    assert not columns & {"username", "path", "filename", "created_at", "modified_at"}


def test_import_is_idempotent(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    import_from_bdsc1(app, lite, complete)

    second = import_from_bdsc1(app, lite, complete)

    assert (second.accounts_created, second.accounts_updated, second.folders_created) == (0, 0, 0)
    assert second.media_accounts == 0 and second.media_accounts_unchanged == 2
    assert app.execute("SELECT COUNT(*) FROM media_index").fetchone()[0] == 4


def test_media_reindexed_when_complete_changes(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    import_from_bdsc1(app, lite, complete)
    with sqlite3.connect(complete) as conn:
        conn.execute(
            "INSERT INTO media (id_accounts, username, filename, path, type) VALUES (2, '', ?, '', 'POST')",
            (_name("2026-01-05", 4002, 2),),
        )

    report = import_from_bdsc1(app, lite, complete)

    assert report.media_accounts == 1
    bob = app.execute("SELECT id FROM catalog_accounts WHERE username = 'bob'").fetchone()[0]
    assert app.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (bob,)).fetchone()[0] == 2


def test_dry_run_writes_nothing(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    before = app.execute("SELECT COUNT(*) FROM catalog_accounts").fetchone()[0]

    report = import_from_bdsc1(app, lite, complete, dry_run=True)

    assert report.dry_run and report.accounts_created == 5
    assert app.execute("SELECT COUNT(*) FROM catalog_accounts").fetchone()[0] == before
    assert app.execute("SELECT COUNT(*) FROM media_index").fetchone()[0] == 0
    assert app.execute("SELECT COUNT(*) FROM catalog_folders").fetchone()[0] == 1
    assert app.execute("SELECT COUNT(*) FROM library_import_issues").fetchone()[0] == 0


def test_owner_mismatch_is_reported_not_overwritten(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    _add_managed(app, "bob", "999", "ENABLED")

    report = import_from_bdsc1(app, lite, complete)

    assert report.issues["OWNER_MISMATCH"] == 1
    assert app.execute(
        "SELECT instagram_user_id FROM catalog_accounts WHERE username = 'bob'"
    ).fetchone()[0] == "999"


def test_stale_complete_warns(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)

    report = import_from_bdsc1(app, lite, complete, dry_run=True)

    assert any("desfasado" in w for w in report.warnings)


def test_missing_sources_raise(app, tmp_path: Path) -> None:
    with pytest.raises(LibraryImportError):
        import_from_bdsc1(app, tmp_path / "nope.sqlite", None)
    with pytest.raises(LibraryImportError):
        import_from_bdsc1(app, None, None)


def test_archived_hidden_from_catalog_until_used(app, tmp_path: Path) -> None:
    lite, complete = _sources(tmp_path)
    import_from_bdsc1(app, lite, complete)
    repo = AccountHistoryRepository(app)

    assert "bob" not in {a.user_name.casefold() for a in repo.list_all()}
    assert "bob" in {a.user_name.casefold() for a in repo.list_all(include_archived=True)}
    assert "bob" not in {a.user_name.casefold() for a in repo.list_enabled()}

    used = repo.create_or_get("bob")  # using it in the editor/batch promotes it

    assert used.status is AccountHistoryStatus.ENABLED
    assert "bob" in {a.user_name.casefold() for a in repo.list_all()}
