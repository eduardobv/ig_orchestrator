"""Import the sc1 databases (accounts_complete + accounts_lite) into bdapp.

``accounts_complete`` is the main source (counters, last content date, media
index); ``accounts_lite`` is the authority for paths when both differ.
Nothing is written to the sc1 databases or to disk. Idempotent: running it
twice without changes reports "0 created, 0 updated".
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.library.filenames import KIND_CODES, parse_media_name
from ig_orchestrator.library.paths import parent_rel, rel_key, to_abs, to_rel

INACTIVE_CATEGORIES = ("06.EXCLUDED", "09.DELETED", "10.TEMP", "11.DISCARTED")
STALE_DAYS = 2
ProgressCallback = Callable[[str, int, int], None]


class LibraryImportError(ValueError):
    """The import cannot start (missing database, no library root...)."""


@dataclass(slots=True)
class ImportReport:
    dry_run: bool = False
    library_root: str = ""
    source_accounts: int = 0
    accounts_created: int = 0
    accounts_updated: int = 0
    accounts_unchanged: int = 0
    folders_created: int = 0
    media_accounts: int = 0
    media_accounts_unchanged: int = 0
    media_rows: int = 0
    media_unparsed: int = 0
    issues: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    issue_rows: list[tuple] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(
            self.accounts_created
            or self.accounts_updated
            or self.folders_created
            or self.media_accounts
        )

    def render(self) -> str:
        lines = [
            ("SIMULACION (no se escribio nada)" if self.dry_run else "IMPORTACION APLICADA"),
            f"Raiz de la biblioteca: {self.library_root}",
            f"Cuentas en origen: {self.source_accounts}",
            f"Cuentas creadas: {self.accounts_created} · actualizadas: {self.accounts_updated}"
            f" · sin cambios: {self.accounts_unchanged}",
            f"Carpetas creadas: {self.folders_created}",
            f"Indice de ficheros: {self.media_accounts} cuentas reindexadas"
            f" ({self.media_rows} ficheros), {self.media_accounts_unchanged} sin cambios,"
            f" {self.media_unparsed} nombres no reconocidos",
        ]
        if self.issues:
            lines.append("Incidencias: " + ", ".join(f"{k} {v}" for k, v in sorted(self.issues.items())))
        lines.extend(f"AVISO: {w}" for w in self.warnings)
        return "\n".join(lines)


@dataclass(slots=True)
class _Source:
    username: str
    owner_id: str
    rel_path: str | None
    abs_path: str
    complete_id: int | None = None
    lite_id: int | None = None
    posts: int | None = None
    reels: int | None = None
    story: int | None = None
    highlights: int | None = None
    last_media_at: str | None = None
    from_lite: bool = False


def _connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _clean_owner(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return "" if text.casefold() in {"", "unknown", "none", "null"} else text


def _is_active(rel: str | None) -> bool:
    if not rel:
        return False
    category = rel.split("\\", 1)[0].upper()
    return not any(category.startswith(prefix) for prefix in INACTIVE_CATEGORIES)


def _resolve_root(app: sqlite3.Connection, library_root: str | None) -> str:
    if library_root and library_root.strip():
        return library_root.strip().rstrip("\\/")
    row = app.execute("SELECT path FROM path_roots WHERE code = 'LIBRARY'").fetchone()
    if row is not None and str(row[0]).strip():
        return str(row[0]).strip().rstrip("\\/")
    row = app.execute(
        "SELECT full_path FROM catalog_folders WHERE parent_id IS NULL ORDER BY id LIMIT 1"
    ).fetchone()
    if row is not None and str(row[0]).strip():
        return str(row[0]).strip().rstrip("\\/")
    raise LibraryImportError("No hay raiz de biblioteca (path_roots.LIBRARY): indicala con --root.")


def _read_sources(
    lite_path: Path | None,
    complete_path: Path | None,
    root: str,
    report: ImportReport,
) -> tuple[list[_Source], dict[int, str]]:
    """Return canonical source records and ``complete account id -> username``."""

    candidates: dict[str, list[_Source]] = defaultdict(list)
    complete_names: dict[int, str] = {}
    complete_by_key: dict[str, _Source] = {}

    if complete_path is not None:
        connection = _connect_ro(complete_path)
        try:
            for row in connection.execute(
                "SELECT id, username, ownerId, path, posts, reels, story, highlights, "
                "last_modified FROM accounts"
            ):
                path = str(row["path"] or "")
                rel = to_rel(path, root)
                source = _Source(
                    username=str(row["username"]),
                    owner_id=_clean_owner(row["ownerId"]),
                    rel_path=rel,
                    abs_path=path,
                    complete_id=int(row["id"]),
                    posts=int(row["posts"] or 0),
                    reels=int(row["reels"] or 0),
                    story=int(row["story"] or 0),
                    highlights=int(row["highlights"] or 0),
                    last_media_at=str(row["last_modified"]) if row["last_modified"] else None,
                )
                complete_names[source.complete_id] = source.username
                complete_by_key[rel_key(rel) if rel else path.casefold()] = source
                candidates[source.username.casefold()].append(source)
        finally:
            connection.close()

    lite_keys: set[str] = set()
    if lite_path is not None:
        connection = _connect_ro(lite_path)
        try:
            for row in connection.execute(
                "SELECT id, username, ownerId, path FROM accounts_dir"
            ):
                path = str(row["path"] or "")
                rel = to_rel(path, root)
                key = rel_key(rel) if rel else path.casefold()
                lite_keys.add(key)
                username = str(row["username"])
                twin = complete_by_key.get(key)
                if twin is not None:
                    twin.lite_id = int(row["id"])
                    twin.from_lite = True
                    if not twin.owner_id:
                        twin.owner_id = _clean_owner(row["ownerId"])
                    continue
                # Same username in complete but another path: lite is the path authority.
                same_user = [c for c in candidates[username.casefold()] if c.complete_id is not None]
                source = _Source(
                    username=username,
                    owner_id=_clean_owner(row["ownerId"]),
                    rel_path=rel,
                    abs_path=path,
                    lite_id=int(row["id"]),
                    from_lite=True,
                )
                if len(same_user) == 1 and not same_user[0].from_lite:
                    stale = same_user[0]
                    source.complete_id = stale.complete_id
                    source.posts, source.reels = stale.posts, stale.reels
                    source.story, source.highlights = stale.story, stale.highlights
                    source.last_media_at = stale.last_media_at
                    if not source.owner_id:
                        source.owner_id = stale.owner_id
                    candidates[username.casefold()].remove(stale)
                candidates[username.casefold()].append(source)
        finally:
            connection.close()

    if complete_path is not None and lite_path is not None:
        complete_keys = set(complete_by_key)
        only_lite = len(lite_keys - complete_keys)
        only_complete = len(complete_keys - lite_keys)
        if only_lite or only_complete:
            report.warnings.append(
                f"accounts_complete desfasado respecto a lite: {only_lite} rutas solo en lite,"
                f" {only_complete} solo en complete. Ejecuta sc1 --lite y --update (paso 0)."
            )
        age = abs(os.path.getmtime(lite_path) - os.path.getmtime(complete_path)) / 86400
        if age > STALE_DAYS:
            report.warnings.append(
                f"complete y lite se modificaron con {age:.0f} dias de diferencia."
            )

    canonical: list[_Source] = []
    for group in candidates.values():
        distinct: dict[str, _Source] = {}
        for item in group:
            distinct.setdefault(rel_key(item.rel_path) if item.rel_path else item.abs_path.casefold(), item)
        ordered = sorted(
            distinct.values(),
            key=lambda s: (_is_active(s.rel_path), s.last_media_at or "", s.from_lite),
            reverse=True,
        )
        canonical.append(ordered[0])
        for other in ordered[1:]:
            report.issues["USERNAME_DUP"] += 1
            report.issue_rows.append(
                ("USERNAME_DUP", other.username, other.owner_id, other.rel_path,
                 f"mismo username que {ordered[0].rel_path}")
            )
    # Only canonical rows own media; duplicate usernames must not overwrite each other.
    owned = {c.complete_id: c.username for c in canonical if c.complete_id is not None}
    return canonical, owned


def import_from_bdsc1(
    app_conn: sqlite3.Connection,
    lite_path: Path | None,
    complete_path: Path | None = None,
    *,
    dry_run: bool = False,
    include_media: bool = True,
    library_root: str | None = None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    if lite_path is None and complete_path is None:
        raise LibraryImportError("Indica accounts_lite y/o accounts_complete.")
    for path in (lite_path, complete_path):
        if path is not None and not path.is_file():
            raise LibraryImportError(f"No existe la base de datos: {path}")

    report = ImportReport(dry_run=dry_run)
    root = _resolve_root(app_conn, library_root)
    report.library_root = root
    sources, complete_names = _read_sources(lite_path, complete_path, root, report)
    report.source_accounts = len(sources)

    app_conn.execute("SAVEPOINT import_bdsc1")
    try:
        _apply(app_conn, sources, root, report, progress)
        if include_media and complete_path is not None:
            _import_media(app_conn, complete_path, complete_names, report, progress)
        _store_issues(app_conn, report)
    except BaseException:
        app_conn.execute("ROLLBACK TO import_bdsc1")
        app_conn.execute("RELEASE import_bdsc1")
        raise
    if dry_run:
        app_conn.execute("ROLLBACK TO import_bdsc1")
        app_conn.execute("RELEASE import_bdsc1")
    else:
        app_conn.execute("RELEASE import_bdsc1")
        app_conn.commit()
    return report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_folders(
    conn: sqlite3.Connection,
    root: str,
    folders: dict[str, int],
    rel: str,
    report: ImportReport,
) -> int:
    """Folder id for relative path *rel* (creating missing ancestors)."""

    key = rel_key(rel)
    if key in folders:
        return folders[key]
    parent_id = _ensure_folders(conn, root, folders, parent_rel(rel), report) if rel else None
    depth = len([p for p in rel.split("\\") if p])
    absolute = to_abs(rel, root)
    name = rel.rsplit("\\", 1)[-1] if rel else absolute
    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO catalog_folders
            (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (parent_id, name, absolute, depth, now, now, rel, "CATEGORY" if depth == 1 else "GROUP"),
    )
    report.folders_created += 1
    folders[key] = int(cursor.lastrowid)
    return folders[key]


def _apply(
    conn: sqlite3.Connection,
    sources: list[_Source],
    root: str,
    report: ImportReport,
    progress: ProgressCallback | None,
) -> None:
    # Existing folders indexed by relative path; backfill rel_path/kind.
    folders: dict[str, int] = {}
    for row in conn.execute("SELECT id, full_path, rel_path, kind, depth FROM catalog_folders"):
        rel = to_rel(str(row["full_path"]), root)
        if rel is None:
            continue
        folders[rel_key(rel)] = int(row["id"])
        depth = len([p for p in rel.split("\\") if p])
        kind = "CATEGORY" if depth == 1 else "GROUP"
        if row["rel_path"] != rel or row["kind"] != kind:
            conn.execute(
                "UPDATE catalog_folders SET rel_path = ?, kind = ? WHERE id = ?",
                (rel, kind, row["id"]),
            )

    archived_id = int(
        conn.execute("SELECT id FROM catalog_account_statuses WHERE code = 'ARCHIVED'").fetchone()[0]
    )
    existing: dict[str, sqlite3.Row] = {}
    by_rel: dict[str, int] = {}
    for row in conn.execute(
        """
        SELECT a.id, a.username, a.instagram_user_id, a.folder_id, a.rel_path,
               a.posts_count, a.reels_count, a.story_count, a.highlights_count,
               a.last_media_at, a.legacy_lite_id, f.full_path AS folder_path
        FROM catalog_accounts a LEFT JOIN catalog_folders f ON f.id = a.folder_id
        """
    ):
        existing[str(row["username"]).casefold()] = row
        if row["rel_path"]:
            by_rel[rel_key(str(row["rel_path"]))] = int(row["id"])

    seen_usernames: set[str] = set()
    owners: dict[str, list[_Source]] = defaultdict(list)
    total = len(sources)
    for index, source in enumerate(sorted(sources, key=lambda s: s.username.casefold()), start=1):
        seen_usernames.add(source.username.casefold())
        if source.owner_id:
            owners[source.owner_id].append(source)
        rel = source.rel_path
        row = existing.get(source.username.casefold())
        if rel is None:
            report.issues["OUTSIDE_ROOT"] += 1
            report.issue_rows.append(("OUTSIDE_ROOT", source.username, source.owner_id, None, source.abs_path))
        elif rel_key(rel) in by_rel and (row is None or by_rel[rel_key(rel)] != int(row["id"])):
            report.issues["PATH_CLASH"] += 1
            report.issue_rows.append(("PATH_CLASH", source.username, source.owner_id, rel, "otra cuenta ya usa esta ruta"))
            rel = None

        if row is None:
            folder_id = _ensure_folders(conn, root, folders, parent_rel(rel), report) if rel else None
            now = _now()
            conn.execute(
                """
                INSERT INTO catalog_accounts
                    (username, instagram_user_id, folder_id, status_id, is_favorite, created_at,
                     updated_at, rel_path, posts_count, reels_count, story_count, highlights_count,
                     last_media_at, legacy_lite_id)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.username, source.owner_id or None, folder_id, archived_id, now, now, rel,
                    source.posts, source.reels, source.story, source.highlights,
                    source.last_media_at, source.lite_id,
                ),
            )
            report.accounts_created += 1
        else:
            changes: dict[str, object] = {}
            if rel is not None and row["rel_path"] != rel:
                changes["rel_path"] = rel
            for column, value in (
                ("posts_count", source.posts),
                ("reels_count", source.reels),
                ("story_count", source.story),
                ("highlights_count", source.highlights),
                ("last_media_at", source.last_media_at),
            ):
                if value is not None and row[column] != value:
                    changes[column] = value
            if source.lite_id is not None and row["legacy_lite_id"] != source.lite_id:
                changes["legacy_lite_id"] = source.lite_id
            current_owner = str(row["instagram_user_id"] or "").strip()
            if source.owner_id and not current_owner:
                changes["instagram_user_id"] = source.owner_id
            elif source.owner_id and current_owner != source.owner_id:
                report.issues["OWNER_MISMATCH"] += 1
                report.issue_rows.append(
                    ("OWNER_MISMATCH", source.username, source.owner_id, rel,
                     f"bdapp={current_owner} origen={source.owner_id}")
                )
            if rel is not None and row["folder_id"] is None:
                changes["folder_id"] = _ensure_folders(conn, root, folders, parent_rel(rel), report)
            elif rel is not None and row["folder_path"]:
                folder_rel = to_rel(str(row["folder_path"]), root)
                if folder_rel is not None and rel_key(folder_rel) not in {
                    rel_key(rel), rel_key(parent_rel(rel))
                }:
                    report.issues["FOLDER_MISMATCH"] += 1
                    report.issue_rows.append(
                        ("FOLDER_MISMATCH", source.username, source.owner_id, rel,
                         f"bdapp={folder_rel}")
                    )
            if changes:
                assignments = ", ".join(f"{column} = ?" for column in changes)
                conn.execute(
                    f"UPDATE catalog_accounts SET {assignments}, updated_at = ? WHERE id = ?",
                    (*changes.values(), _now(), row["id"]),
                )
                report.accounts_updated += 1
            else:
                report.accounts_unchanged += 1
        if progress is not None and index % 100 == 0:
            progress("accounts", index, total)

    for group in owners.values():
        if len(group) > 1:
            report.issues["OWNER_DUP"] += 1
            report.issue_rows.append(
                ("OWNER_DUP", ", ".join(sorted(s.username for s in group)), group[0].owner_id,
                 None, " | ".join(s.rel_path or s.abs_path for s in group))
            )
    for username, row in existing.items():
        if username not in seen_usernames:
            report.issues["ONLY_IN_APP"] += 1
            report.issue_rows.append(("ONLY_IN_APP", str(row["username"]), None, row["rel_path"], None))


def _import_media(
    conn: sqlite3.Connection,
    complete_path: Path,
    complete_names: dict[int, str],
    report: ImportReport,
    progress: ProgressCallback | None,
) -> None:
    app_ids = {
        str(row["username"]).casefold(): int(row["id"])
        for row in conn.execute("SELECT id, username FROM catalog_accounts")
    }
    source = _connect_ro(complete_path)
    try:
        total_accounts = len(complete_names)
        done = 0
        current_id: int | None = None
        batch: list[tuple[str, int]] = []

        def flush() -> None:
            nonlocal done
            if current_id is None or not batch:
                return
            username = complete_names.get(current_id)
            account_id = app_ids.get(username.casefold()) if username else None
            if account_id is not None:
                _index_account(conn, account_id, batch, report)
            done += 1
            if progress is not None and done % 50 == 0:
                progress("media", done, total_accounts)

        for row in source.execute(
            "SELECT id_accounts, filename, type FROM media ORDER BY id_accounts"
        ):
            if row["id_accounts"] != current_id:
                flush()
                current_id = int(row["id_accounts"])
                batch = []
            batch.append((str(row["filename"]), KIND_CODES.get(str(row["type"]), -1)))
        flush()
    finally:
        source.close()


def _index_account(
    conn: sqlite3.Connection,
    account_id: int,
    files: list[tuple[str, int]],
    report: ImportReport,
) -> None:
    rows: list[tuple[int, int, int, int, int, int, str]] = []
    skipped = 0
    for filename, kind in files:
        parsed = parse_media_name(filename) if kind >= 0 else None
        if parsed is None:
            skipped += 1
            continue
        rows.append(
            (account_id, kind, parsed.media_id, parsed.taken_at, parsed.owner_id, parsed.ext, parsed.suffix)
        )
    report.media_unparsed += skipped
    if skipped:
        report.issues["PARSE_ERROR"] += 1
        report.issue_rows.append(("PARSE_ERROR", None, None, None, f"{skipped} nombres no reconocidos (cuenta {account_id})"))

    fingerprint: dict[int, tuple[int, int]] = {}
    for _a, kind, media_id, *_rest in rows:
        items, top = fingerprint.get(kind, (0, 0))
        fingerprint[kind] = (items + 1, max(top, media_id))
    stored = {
        int(r["kind"]): (int(r["items"]), int(r["max_media_id"] or 0))
        for r in conn.execute(
            "SELECT kind, items, max_media_id FROM media_index_state WHERE account_id = ?",
            (account_id,),
        )
    }
    if stored == fingerprint:
        report.media_accounts_unchanged += 1
        return
    conn.execute("DELETE FROM media_index WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM media_index_state WHERE account_id = ?", (account_id,))
    conn.executemany(
        "INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    now = _now()
    conn.executemany(
        "INSERT INTO media_index_state (account_id, kind, items, max_media_id, indexed_at, source)"
        " VALUES (?, ?, ?, ?, ?, 'accounts_complete')",
        [(account_id, kind, items, top, now) for kind, (items, top) in fingerprint.items()],
    )
    report.media_accounts += 1
    report.media_rows += len(rows)


def _store_issues(conn: sqlite3.Connection, report: ImportReport) -> None:
    conn.execute("DELETE FROM library_import_issues")
    now = _now()
    conn.executemany(
        "INSERT INTO library_import_issues (kind, username, owner_id, rel_path, detail, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(*issue, now) for issue in report.issue_rows],
    )
