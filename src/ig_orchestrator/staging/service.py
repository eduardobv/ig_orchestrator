"""Staging area ("almacen") for renamed accounts and the dump into the library.

Renamed folders can wait in a local staging root (``app_settings['staging.root']``) mirroring the library
structure (``category\\group\\folder``). Later, with the library online, :meth:`StagingService.dump`
merges them into place without overwriting. Every file is copied, size-verified and only then removed from
the staging area, so an interrupted dump can simply be run again.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ig_orchestrator.library.compat_lite import add_to_lite, lite_path_from_settings
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import parent_rel, to_rel
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming.mover import find_directory_merge_conflicts

STAGED, DUMPING, DUMPED, CONFLICT, FAILED = "STAGED", "DUMPING", "DUMPED", "CONFLICT", "FAILED"
OPEN_STATES = (STAGED, DUMPING, CONFLICT, FAILED)
NEW_TARGET, MERGE_TARGET = "NUEVA", "FUSIONAR"
ProgressCallback = Callable[[int, int, str], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def folder_stats(folder: str) -> tuple[int, int]:
    files = size = 0
    for current, _dirs, names in os.walk(folder):
        for name in names:
            files += 1
            try:
                size += os.path.getsize(os.path.join(current, name))
            except OSError:
                pass
    return files, size


@dataclass(slots=True)
class DumpItem:
    staged_id: int
    username: str
    staging_path: str
    target_path: str
    files: int = 0
    bytes: int = 0
    kind: str = NEW_TARGET  # NUEVA | FUSIONAR | CONFLICTO | FALTA
    conflicts: list[str] = field(default_factory=list)
    status: str = STAGED
    detail: str = ""

    @property
    def dumpable(self) -> bool:
        return self.kind in (NEW_TARGET, MERGE_TARGET)


@dataclass(slots=True)
class DumpOutcome:
    username: str
    status: str
    files: int = 0
    bytes: int = 0
    detail: str = ""


@dataclass(slots=True)
class DumpResult:
    run_id: int = 0
    outcomes: list[DumpOutcome] = field(default_factory=list)
    cancelled: bool = False

    @property
    def problems(self) -> list[DumpOutcome]:
        return [o for o in self.outcomes if o.status in (CONFLICT, FAILED)]

    def summary(self) -> str:
        done = [o for o in self.outcomes if o.status == DUMPED]
        return f"{len(done)} de {len(self.outcomes)} cuentas volcadas · {sum(o.files for o in done)} ficheros · {len(self.problems)} con problemas"


def move_file_verified(source: str, destination: str) -> None:
    """Move one file; across drives it is copied, size-checked and only then removed."""

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.splitdrive(os.path.abspath(source))[0].casefold() == os.path.splitdrive(os.path.abspath(destination))[0].casefold():
        os.replace(source, destination)
        return
    partial = destination + ".part"
    shutil.copy2(source, partial)
    if os.path.getsize(partial) != os.path.getsize(source):
        os.remove(partial)
        raise OSError(f"La copia no coincide en tamano: {os.path.basename(source)}")
    os.replace(partial, destination)
    os.remove(source)


def merge_verified(source: str, destination: str) -> int:
    """Merge ``source`` into ``destination`` file by file (no overwrite). Returns moved files."""

    moved = 0
    for current, _dirs, names in os.walk(source):
        rel = os.path.relpath(current, source)
        target_dir = destination if rel == "." else os.path.join(destination, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in names:
            move_file_verified(os.path.join(current, name), os.path.join(target_dir, name))
            moved += 1
    for current, _dirs, _names in os.walk(source, topdown=False):
        try:
            os.rmdir(current)
        except OSError:
            pass
    return moved


class StagingService:
    def __init__(self, conn: sqlite3.Connection, *, root: str | None = None) -> None:
        self.conn = conn
        self.fs = FsOperationService(conn, root=root)

    # ---------------------------------------------------------------- roots
    def staging_root(self) -> str:
        row = self.conn.execute("SELECT value FROM app_settings WHERE key = 'staging.root'").fetchone()
        value = str(row[0]).strip().rstrip("\\/") if row is not None and row[0] else ""
        if not value:
            raise ValueError("No hay almacen configurado: indicalo en Ajustes > Catalogo")
        return value

    def staging_path(self, rel: str) -> str:
        return os.path.join(self.staging_root(), *[p for p in rel.replace("/", "\\").split("\\") if p])

    # ------------------------------------------------------------ recording
    def record(self, account_id: int, staging_rel: str, target_rel: str, rename_run_id: int | None) -> None:
        files, size = folder_stats(self.staging_path(staging_rel))
        self.conn.execute(
            "INSERT INTO staged_accounts (catalog_account_id, staging_rel, target_rel, rename_run_id, files, bytes, status, staged_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'STAGED', ?)"
            " ON CONFLICT(catalog_account_id, staging_rel) DO UPDATE SET target_rel = excluded.target_rel,"
            " rename_run_id = excluded.rename_run_id, files = excluded.files, bytes = excluded.bytes,"
            " status = 'STAGED', staged_at = excluded.staged_at, dumped_at = NULL, error = NULL",
            (account_id, staging_rel, target_rel, rename_run_id, files, size, _now()),
        )
        self.conn.commit()

    # -------------------------------------------------------------- queries
    def pending_rows(self) -> list[sqlite3.Row]:
        marks = ",".join("?" for _ in OPEN_STATES)
        return self.conn.execute(
            f"SELECT s.*, a.username, a.rel_path AS account_rel FROM staged_accounts s"
            f" JOIN catalog_accounts a ON a.id = s.catalog_account_id WHERE s.status IN ({marks}) ORDER BY s.id",
            OPEN_STATES,
        ).fetchall()

    def summary(self) -> tuple[int, int, int]:
        """``(accounts, files, bytes)`` waiting in the staging area."""

        rows = self.pending_rows()
        return len(rows), sum(int(r["files"] or 0) for r in rows), sum(int(r["bytes"] or 0) for r in rows)

    def target_rel(self, row: sqlite3.Row) -> str:
        """Where the folder goes now: follows moves/renames of the account in the catalog."""

        if row["account_rel"]:
            parent = parent_rel(str(row["account_rel"]))
            leaf = str(row["staging_rel"]).replace("/", "\\").rstrip("\\").split("\\")[-1]
            return (parent + "\\" + leaf) if parent else leaf
        return str(row["target_rel"])

    def plan(self, ids: list[int] | None = None) -> list[DumpItem]:
        items = []
        for row in self.pending_rows():
            if ids is not None and int(row["id"]) not in ids:
                continue
            staging_path = self.staging_path(str(row["staging_rel"]))
            target_rel = self.target_rel(row)
            target = self.fs.abs(target_rel) if self.fs.is_online() else os.path.join(self.fs.root, target_rel)
            item = DumpItem(int(row["id"]), str(row["username"]), staging_path, target, status=str(row["status"]))
            if not os.path.isdir(staging_path):
                item.kind, item.detail = "FALTA", "La carpeta ya no esta en el almacen"
            else:
                item.files, item.bytes = folder_stats(staging_path)
                if os.path.isdir(target):
                    item.kind = MERGE_TARGET
                    item.conflicts = find_directory_merge_conflicts(staging_path, target)
                    if item.conflicts:
                        item.kind, item.detail = "CONFLICTO", f"{len(item.conflicts)} fichero(s) ya existen en el destino"
            items.append(item)
        return items

    # ----------------------------------------------------------------- dump
    def dump(
        self,
        ids: list[int] | None = None,
        *,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> DumpResult:
        if not self.fs.is_online():
            raise ValueError("La biblioteca no esta disponible: conecta la unidad e intentalo de nuevo")
        cancel = cancel_event or threading.Event()
        items = self.plan(ids)
        result = DumpResult()
        cursor = self.conn.execute("INSERT INTO dump_runs (started_at, status) VALUES (?, 'RUNNING')", (_now(),))
        result.run_id = int(cursor.lastrowid)
        self.conn.commit()
        for index, item in enumerate(items, start=1):
            if cancel.is_set():
                result.cancelled = True
                break
            if progress is not None:
                progress(index, len(items), item.username)
            result.outcomes.append(self._dump_one(item))
        files = sum(o.files for o in result.outcomes if o.status == DUMPED)
        size = sum(o.bytes for o in result.outcomes if o.status == DUMPED)
        self.conn.execute(
            "UPDATE dump_runs SET finished_at = ?, status = ?, accounts = ?, files = ?, bytes = ?, summary = ? WHERE id = ?",
            (_now(), "CANCELLED" if result.cancelled else ("OK" if not result.problems else "WITH_PROBLEMS"),
             sum(1 for o in result.outcomes if o.status == DUMPED), files, size, result.summary(), result.run_id),
        )
        self.conn.commit()
        return result

    def _set_status(self, staged_id: int, status: str, error: str = "") -> None:
        self.conn.execute(
            "UPDATE staged_accounts SET status = ?, error = ?, dumped_at = CASE WHEN ? = 'DUMPED' THEN ? ELSE dumped_at END WHERE id = ?",
            (status, error or None, status, _now(), staged_id),
        )
        self.conn.commit()

    def _dump_one(self, item: DumpItem) -> DumpOutcome:
        if item.kind == "FALTA":
            self._set_status(item.staged_id, FAILED, item.detail)
            return DumpOutcome(item.username, FAILED, detail=item.detail)
        if item.kind == "CONFLICTO":
            self._set_status(item.staged_id, CONFLICT, item.detail)
            return DumpOutcome(item.username, CONFLICT, detail=item.detail + ": " + ", ".join(os.path.basename(c) for c in item.conflicts[:5]))
        self._set_status(item.staged_id, DUMPING)
        try:
            moved = merge_verified(item.staging_path, item.target_path)
        except OSError as exc:
            self._set_status(item.staged_id, FAILED, str(exc))
            return DumpOutcome(item.username, FAILED, detail=str(exc))
        outcome = DumpOutcome(item.username, DUMPED, files=moved, bytes=item.bytes)
        try:
            self._after_dump(item, outcome)
        except Exception as exc:  # noqa: BLE001 - files are already in place; report only
            outcome.detail = f"Movida, pero la base de la app no se actualizo del todo: {exc}"
        self._set_status(item.staged_id, DUMPED)
        self._clean_empty_parents(item.staging_path)
        return outcome

    def _after_dump(self, item: DumpItem, outcome: DumpOutcome) -> None:
        row = self.conn.execute(
            "SELECT a.id, a.rel_path, a.start_init_date FROM staged_accounts s JOIN catalog_accounts a ON a.id = s.catalog_account_id"
            " WHERE s.id = ?", (item.staged_id,)
        ).fetchone()
        account_id = int(row["id"])
        if not row["rel_path"]:
            rel = to_rel(item.target_path, self.fs.root)
            if rel is not None:
                folder_id = self.fs.ensure_folder_rows(parent_rel(rel))
                self.conn.execute(
                    "UPDATE catalog_accounts SET rel_path = ?, folder_id = ?, disk_state = 'PRESENT', updated_at = ? WHERE id = ?",
                    (rel, folder_id, _now(), account_id),
                )
                self.conn.commit()
                lite = lite_path_from_settings(self.conn)
                if lite is not None:
                    try:
                        add_to_lite(self.conn, lite, account_id, self.fs.root, row["start_init_date"] or "")
                    except (sqlite3.Error, OSError) as exc:
                        outcome.detail = f"accounts_lite no actualizada: {exc}"
        LibraryScanner(self.conn, root=self.fs.root).scan(ACCOUNT, account_id=account_id)

    def _clean_empty_parents(self, path: str) -> None:
        root = os.path.normcase(os.path.abspath(self.staging_root()))
        current = os.path.dirname(os.path.abspath(path))
        while os.path.normcase(current) != root and os.path.normcase(current).startswith(root):
            try:
                os.rmdir(current)
            except OSError:
                break
            current = os.path.dirname(current)

    def forget_dumped(self) -> int:
        cursor = self.conn.execute("DELETE FROM staged_accounts WHERE status = 'DUMPED'")
        self.conn.commit()
        return cursor.rowcount
