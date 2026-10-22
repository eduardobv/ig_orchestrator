"""Incremental disk -> bdapp synchronisation (replaces ``sc1``).

Idea: re-read as little as possible. The modification time of a folder changes when entries are
created, removed or renamed directly inside it, so a ``stat`` per account folder and per media
sub-folder (root, ``reels``, ``story``, ``highlights``) tells which ones to list again.
The algorithm for counters, owner id and last content date is the one of ``generatedirmap.py``.

* Never runs by itself; the caller decides (menu, CLI).
* Writes only counters/state/index of ``bdapp``; **never touches the disk** and never deletes accounts.
* Differences that need a human decision are stored as ``scan_findings``.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ig_orchestrator.library.filenames import parse_instagram_filename, parse_media_name
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import parent_rel, rel_key, to_rel
from ig_orchestrator.library.rules import LibraryRules

ALL, CATEGORY, ACCOUNT, DEEP = "ALL", "CATEGORY", "ACCOUNT", "DEEP"
# (sub-folder, media_index kind, mtime column, counter column)
LOCATIONS = (
    ("", 0, "dir_mtime_root", "posts_count"),
    ("reels", 1, "dir_mtime_reels", "reels_count"),
    ("story", 2, "dir_mtime_story", "story_count"),
    ("highlights", 3, "dir_mtime_highlights", "highlights_count"),
)
OWNER_PRIORITY = ("story", "highlights", "reels", "")
COMMIT_EVERY = 50
ProgressCallback = Callable[[str, int, int], None]

_SCAN_LOCK = threading.Lock()


class ScanError(RuntimeError):
    """The scan cannot run (library offline, another scan running...)."""


@dataclass(slots=True)
class Finding:
    kind: str
    rel_path: str
    detail: str = ""
    account_id: int | None = None


@dataclass(slots=True)
class ScanReport:
    scope: str
    rel_scope: str = ""
    run_id: int = 0
    dirs_stat: int = 0
    dirs_listed: int = 0
    files_seen: int = 0
    baselined: int = 0
    accounts_checked: int = 0
    accounts_changed: int = 0
    accounts_new: int = 0
    accounts_missing: int = 0
    errors: int = 0
    seconds: float = 0.0
    cancelled: bool = False
    findings: list[Finding] = field(default_factory=list)

    def summary(self) -> str:
        text = (
            f"{self.accounts_checked} cuentas revisadas · {self.dirs_stat} carpetas consultadas · "
            f"{self.dirs_listed} listadas · {self.baselined} tomadas como base · "
            f"{self.accounts_changed} con cambios · {self.accounts_new} nuevas · {self.accounts_missing} ausentes · "
            f"{len(self.findings)} hallazgos · {self.errors} errores · {self.seconds:.1f} s"
        )
        return text + (" (CANCELADO)" if self.cancelled else "")


@dataclass(slots=True)
class _Location:
    exists: bool = False
    mtime: float | None = None
    listed: bool = False
    count: int = 0
    newest: datetime | None = None
    owners: Counter = field(default_factory=Counter)
    first_seen: dict = field(default_factory=dict)
    media: list = field(default_factory=list)  # (media_id, taken_at, owner_id, ext, suffix)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_dir(path: str, report: ScanReport) -> tuple[list[os.DirEntry], list[os.DirEntry]]:
    files, folders = [], []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_file(follow_symlinks=False):
                        files.append(entry)
                    elif entry.is_dir(follow_symlinks=False):
                        folders.append(entry)
                except OSError:
                    report.errors += 1
    except OSError:
        report.errors += 1
    report.dirs_listed += 1
    return files, folders


def is_account_folder(path: str, files, folders, rules: LibraryRules, report: ScanReport) -> bool:
    """sc1 rule: direct multimedia files, or a known media sub-folder with direct multimedia files."""

    if any(rules.is_multimedia(e.name) for e in files):
        return True
    for folder in folders:
        if folder.name.lower() in rules.media_subfolders:
            sub_files, _ = _read_dir(folder.path, report)
            if any(rules.is_multimedia(e.name) for e in sub_files):
                return True
    return False


def _owner_of_folder(path: str, rules: LibraryRules, report: ScanReport) -> str | None:
    """Owner id exactly as sc1 (first priority folder that has parsable names, most frequent id)."""

    for sub in OWNER_PRIORITY:
        folder = os.path.join(path, sub) if sub else path
        if not os.path.isdir(folder):
            continue
        files, _ = _read_dir(folder, report)
        counts: Counter = Counter()
        first: dict = {}
        for entry in files:
            if not rules.is_multimedia(entry.name):
                continue
            parsed = parse_instagram_filename(entry.name)
            if parsed is None:
                continue
            counts[parsed.owner_id] += 1
            first.setdefault(parsed.owner_id, len(first))
        if counts:
            return max(counts, key=lambda owner: (counts[owner], -first[owner]))
    return None


def _inspect(path: str, stored: dict[str, float | None], rules: LibraryRules, report: ScanReport,
             *, force: bool, baseline: bool) -> dict[int, _Location]:
    """stat the four locations; list the ones whose mtime differs (or all when *force*)."""

    now = time.time()
    result: dict[int, _Location] = {}
    for sub, kind, column, _counter in LOCATIONS:
        location = _Location()
        folder = os.path.join(path, sub) if sub else path
        try:
            stat = os.stat(folder)
            location.exists, location.mtime = True, stat.st_mtime
        except OSError:
            location.exists = False
        report.dirs_stat += 1
        result[kind] = location
        if not location.exists or baseline:
            continue
        previous = stored.get(column)
        suspicious = location.mtime is None or location.mtime <= 0 or location.mtime > now + 86400
        if not (force or previous is None or suspicious or abs(previous - location.mtime) > 1e-6):
            continue
        files, _folders = _read_dir(folder, report)
        location.listed = True
        for entry in files:
            report.files_seen += 1
            if not rules.is_multimedia(entry.name):
                continue
            location.count += 1
            parsed = parse_instagram_filename(entry.name)
            if parsed is None:
                continue
            if location.newest is None or parsed.timestamp > location.newest:
                location.newest = parsed.timestamp
            location.owners[parsed.owner_id] += 1
            location.first_seen.setdefault(parsed.owner_id, len(location.first_seen))
            indexed = parse_media_name(entry.name)  # same parser/columns as the import of accounts_complete
            if indexed is not None:
                location.media.append(
                    (indexed.media_id, indexed.taken_at, indexed.owner_id, indexed.ext, indexed.suffix)
                )
    return result


def _owner_from(locations: dict[int, _Location]) -> str | None:
    """Owner by sc1 priority using only listed locations (None if the deciding folder is not listed)."""

    kind_of = {"story": 2, "highlights": 3, "reels": 1, "": 0}
    for sub in OWNER_PRIORITY:
        location = locations[kind_of[sub]]
        if not location.exists:
            continue
        if not location.listed:
            return None  # cannot decide without listing it
        if location.owners:
            return max(location.owners, key=lambda o: (location.owners[o], -location.first_seen[o]))
    return None


class LibraryScanner:
    def __init__(self, conn: sqlite3.Connection, *, root: str | None = None, rules: LibraryRules | None = None) -> None:
        self.conn = conn
        self.fs = FsOperationService(conn, root=root)
        self.rules = rules or LibraryRules.load(conn)

    @property
    def root(self) -> str:
        return self.fs.root

    # ----------------------------------------------------------------- entry
    def scan(
        self,
        scope: str = ALL,
        *,
        rel_scope: str = "",
        account_id: int | None = None,
        deep: bool = False,
        cancel_event: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> ScanReport:
        if not self.fs.is_online():
            raise ScanError("La biblioteca (G:) no esta disponible: no se puede sincronizar")
        if not _SCAN_LOCK.acquire(blocking=False):
            raise ScanError("Ya hay una sincronizacion en curso")
        started = time.time()
        cancel = cancel_event or threading.Event()
        report = ScanReport(DEEP if deep else scope, rel_scope)
        try:
            run_id = int(self.conn.execute(
                "INSERT INTO scan_runs (scope, rel_scope, started_at) VALUES (?, ?, ?)",
                (report.scope, rel_scope or None, _now()),
            ).lastrowid)
            report.run_id = run_id
            self.conn.commit()
            known = self._known_accounts(scope, rel_scope, account_id)
            discovered: set[str] = set()
            if scope in (ALL, CATEGORY):
                base_rel = rel_scope if scope == CATEGORY else ""
                self._discover(base_rel, known, discovered, report, cancel)
            self._check_known(known, deep, report, cancel, progress)
            if not cancel.is_set() and report.errors == 0:
                self._mark_missing(known, discovered, report)
            report.cancelled = cancel.is_set()
        finally:
            report.seconds = time.time() - started
            self._finish(report)
            _SCAN_LOCK.release()
        return report

    # --------------------------------------------------------------- helpers
    def _known_accounts(self, scope: str, rel_scope: str, account_id: int | None) -> dict[str, sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT a.*, s.code AS status FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
            " WHERE a.rel_path IS NOT NULL"
        ).fetchall()
        known: dict[str, sqlite3.Row] = {}
        prefix = rel_key(rel_scope) if rel_scope else ""
        for row in rows:
            key = rel_key(str(row["rel_path"]))
            if scope == ACCOUNT and int(row["id"]) != account_id:
                continue
            if scope == CATEGORY and prefix and not (key == prefix or key.startswith(prefix + "\\")):
                continue
            known[key] = row
        return known

    def _discover(self, base_rel: str, known, discovered: set[str], report: ScanReport, cancel) -> None:
        """Breadth-first walk like sc1, but known account folders are not evaluated again."""

        queue = deque([(self.fs.abs(base_rel) if base_rel else self.root, len([p for p in base_rel.split("\\") if p]))])
        known_keys = set(known)
        new_paths: list[str] = []
        while queue and not cancel.is_set():
            path, depth = queue.popleft()
            rel = to_rel(path, self.root) or ""
            key = rel_key(rel)
            if depth > 0 and key in known_keys:
                discovered.add(key)
                continue
            files, folders = _read_dir(path, report)
            name = os.path.basename(path).casefold()
            if depth > 0 and name not in self.rules.non_account_names and is_account_folder(path, files, folders, self.rules, report):
                new_paths.append(path)
                continue
            if depth < self.rules.max_depth:
                queue.extend((f.path, depth + 1) for f in folders)
        for path in new_paths:
            self._register_new(path, known, report)

    def _register_new(self, path: str, known, report: ScanReport) -> None:
        rel = to_rel(path, self.root) or ""
        username = os.path.basename(path)
        existing = self.conn.execute(
            "SELECT id, rel_path, instagram_user_id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        owner = _owner_of_folder(path, self.rules, report)
        report.accounts_new += 1
        if existing is not None:
            old_rel = existing["rel_path"]
            if old_rel and not os.path.isdir(self.fs.abs(old_rel)):
                report.findings.append(Finding("MOVED_FOLDER", rel, f"@{username} estaba en {old_rel}", int(existing["id"])))
            else:
                report.findings.append(Finding("USERNAME_DUP", rel, f"@{username} ya existe en {old_rel or 'otra ruta'}", int(existing["id"])))
            return
        moved_from = None
        if owner:
            for row in self.conn.execute(
                "SELECT id, username, rel_path FROM catalog_accounts WHERE instagram_user_id = ? AND rel_path IS NOT NULL",
                (owner,),
            ):
                if not os.path.isdir(self.fs.abs(str(row["rel_path"]))):
                    moved_from = row
                    break
        if moved_from is not None:
            report.findings.append(
                Finding("MOVED_FOLDER", rel, f"mismo id de Instagram ({owner}) que @{moved_from['username']}, antes en {moved_from['rel_path']}",
                        int(moved_from["id"]))
            )
        else:
            report.findings.append(Finding("NEW_FOLDER", rel, f"@{username}" + (f" · id {owner}" if owner else "")))

    def _mark_missing(self, known, discovered: set[str], report: ScanReport) -> None:
        moved_accounts = {f.account_id for f in report.findings if f.kind == "MOVED_FOLDER"}
        for key, row in known.items():
            if key in discovered:
                continue
            if os.path.isdir(self.fs.abs(str(row["rel_path"]))):
                continue  # known folder that BFS did not reach (depth) but exists
            self.conn.execute(
                "UPDATE catalog_accounts SET disk_state = 'MISSING', scan_state = 'MISSING', last_scan_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            report.accounts_missing += 1
            if int(row["id"]) not in moved_accounts:  # a MOVED_FOLDER finding already explains it
                report.findings.append(Finding("MISSING_FOLDER", str(row["rel_path"]), f"@{row['username']}", int(row["id"])))
        self.conn.commit()

    def _check_known(self, known, deep: bool, report: ScanReport, cancel, progress) -> None:
        total = len(known)
        for index, (key, row) in enumerate(sorted(known.items()), start=1):
            if cancel.is_set():
                break
            self._check_account(row, deep, report)
            report.accounts_checked += 1
            if index % COMMIT_EVERY == 0:
                self.conn.commit()
                if progress is not None:
                    progress("accounts", index, total)
        self.conn.commit()
        if progress is not None:
            progress("accounts", total, total)

    def _check_account(self, row: sqlite3.Row, deep: bool, report: ScanReport) -> None:
        rel = str(row["rel_path"])
        path = self.fs.abs(rel)
        if not os.path.isdir(path):
            return  # handled by _mark_missing (needs a complete walk to be safe)
        stored = {column: row[column] for _s, _k, column, _c in LOCATIONS}
        never_scanned = all(v is None for v in stored.values())
        has_import_data = row["last_media_at"] is not None or row["posts_count"] is not None
        owner_empty = not str(row["instagram_user_id"] or "").strip()
        # first scan after the import: trust the imported data, only record the folder times
        baseline = never_scanned and has_import_data and not deep and not owner_empty
        locations = _inspect(path, stored, self.rules, report, force=deep or owner_empty, baseline=baseline)
        updates: dict[str, object] = {}
        changed = False
        for sub, kind, column, counter in LOCATIONS:
            location = locations[kind]
            if location.exists:
                updates[column] = location.mtime
            if location.listed:
                if row[counter] != location.count:
                    changed = True
                updates[counter] = location.count
                self._refresh_index(int(row["id"]), kind, location)
            elif not location.exists and row[counter] != 0:
                updates[counter] = 0  # sc1 stores 0 for a missing sub-folder
                changed = changed or bool(row[counter])
        if baseline:
            report.baselined += 1
        listed_any = any(loc.listed for loc in locations.values())
        # last content date: deep recomputes, incremental keeps the maximum
        if listed_any:
            newest = max((loc.newest for loc in locations.values() if loc.newest), default=None)
            stored_last = str(row["last_media_at"] or "")
            if newest is not None:
                text = newest.strftime("%Y-%m-%d %H:%M:%S")
                if deep or text > stored_last:
                    if text != stored_last:
                        updates["last_media_at"] = text
                        changed = True
        owner = _owner_from(locations) if listed_any else None
        current = str(row["instagram_user_id"] or "").strip()
        if owner and not current:
            updates["instagram_user_id"] = owner
            changed = True
        elif owner and current and owner != current:
            report.findings.append(Finding("OWNER_CHANGED", str(row["rel_path"]), f"@{row['username']}: app {current}, disco {owner}", int(row["id"])))
        updates["disk_state"] = "PRESENT"
        updates["scan_state"] = "CHANGED" if changed else "OK"
        updates["last_scan_at"] = _now()
        if changed:
            report.accounts_changed += 1
        assignments = ", ".join(f"{c} = ?" for c in updates)
        self.conn.execute(f"UPDATE catalog_accounts SET {assignments} WHERE id = ?", (*updates.values(), row["id"]))

    def _refresh_index(self, account_id: int, kind: int, location: _Location) -> None:
        """Replace the file index rows of one (account, kind) after re-listing its folder."""

        self.conn.execute("DELETE FROM media_index WHERE account_id = ? AND kind = ?", (account_id, kind))
        self.conn.executemany(
            "INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(account_id, kind, *item) for item in location.media],
        )
        self.conn.execute("DELETE FROM media_index_state WHERE account_id = ? AND kind = ?", (account_id, kind))
        if location.media:
            self.conn.execute(
                "INSERT INTO media_index_state (account_id, kind, items, max_media_id, indexed_at, source)"
                " VALUES (?, ?, ?, ?, ?, 'scanner')",
                (account_id, kind, len(location.media), max(m[0] for m in location.media), _now()),
            )

    def _finish(self, report: ScanReport) -> None:
        if not report.run_id:
            return
        self.conn.execute(
            "UPDATE scan_runs SET finished_at = ?, dirs_stat = ?, dirs_listed = ?, files_seen = ?, accounts_changed = ?,"
            " accounts_new = ?, accounts_missing = ?, errors = ?, seconds = ? WHERE id = ?",
            (_now(), report.dirs_stat, report.dirs_listed, report.files_seen, report.accounts_changed,
             report.accounts_new, report.accounts_missing, report.errors, report.seconds, report.run_id),
        )
        self.conn.executemany(
            "INSERT INTO scan_findings (scan_run_id, kind, account_id, rel_path, detail) VALUES (?, ?, ?, ?, ?)",
            [(report.run_id, f.kind, f.account_id, f.rel_path, f.detail) for f in report.findings],
        )
        self.conn.commit()


# ------------------------------------------------------------------ findings
def list_findings(conn: sqlite3.Connection, *, include_resolved: bool = False) -> list[sqlite3.Row]:
    where = "" if include_resolved else " WHERE f.resolved = 0"
    return conn.execute(
        "SELECT f.*, a.username FROM scan_findings f LEFT JOIN catalog_accounts a ON a.id = f.account_id"
        + where + " ORDER BY f.id DESC LIMIT 1000"
    ).fetchall()


def accept_finding(conn: sqlite3.Connection, finding_id: int, *, root: str | None = None) -> str:
    """Make bdapp follow the disk for one finding. Returns a short description of what was done."""

    row = conn.execute("SELECT * FROM scan_findings WHERE id = ?", (finding_id,)).fetchone()
    if row is None:
        raise ScanError(f"Hallazgo no encontrado: {finding_id}")
    fs = FsOperationService(conn, root=root)
    kind, rel, account_id = str(row["kind"]), str(row["rel_path"] or ""), row["account_id"]
    message = "Sin cambios"
    if kind == "NEW_FOLDER":
        folder_id = fs.ensure_folder_rows(parent_rel(rel))
        status = conn.execute("SELECT id FROM catalog_account_statuses WHERE code = 'ARCHIVED'").fetchone()[0]
        username = rel.rsplit("\\", 1)[-1]
        now = _now()
        conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, is_favorite, created_at, updated_at, rel_path,"
            " disk_state) VALUES (?, ?, ?, 0, ?, ?, ?, 'PRESENT')",
            (username, folder_id, status, now, now, rel),
        )
        message = f"Cuenta @{username} creada (archivada); se leera en la proxima sincronizacion"
    elif kind == "MOVED_FOLDER" and account_id is not None:
        folder_id = fs.ensure_folder_rows(parent_rel(rel))
        conn.execute(
            "UPDATE catalog_accounts SET rel_path = ?, folder_id = ?, disk_state = 'PRESENT', scan_state = 'UNKNOWN',"
            " dir_mtime_root = NULL, dir_mtime_story = NULL, dir_mtime_reels = NULL, dir_mtime_highlights = NULL,"
            " updated_at = ? WHERE id = ?",
            (rel, folder_id, _now(), account_id),
        )
        message = f"Ruta de la cuenta actualizada a {rel}"
    elif kind == "OWNER_CHANGED" and account_id is not None:
        owner = str(row["detail"]).rsplit("disco", 1)[-1].strip()
        conn.execute("UPDATE catalog_accounts SET instagram_user_id = ?, updated_at = ? WHERE id = ?", (owner, _now(), account_id))
        message = f"Id de Instagram actualizado a {owner}"
    conn.execute("UPDATE scan_findings SET resolved = 1 WHERE id = ?", (finding_id,))
    conn.commit()
    return message


def ignore_finding(conn: sqlite3.Connection, finding_id: int) -> None:
    conn.execute("UPDATE scan_findings SET resolved = 1 WHERE id = ?", (finding_id,))
    conn.commit()


def last_scan_age_days(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT finished_at FROM scan_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(row[0]))).total_seconds() / 86400
    except ValueError:
        return None

