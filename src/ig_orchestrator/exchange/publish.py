"""WORKER side: publish finished batches as an atomic package in the shared folder.

Layout: ``<exchange>/<instance>_<batch>_<ts>/{manifest.json, data/<username>/...}``.
The package is built in ``<name>.partial``; ``manifest.json`` is written last and only
then the folder is renamed, so a cut during publishing never leaves a valid-looking package.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.db.instances_repository import InstanceRepository
from ig_orchestrator.exchange.inbox_scan import iter_files, long_path
from ig_orchestrator.exchange.manifest import (
    MANIFEST_NAME,
    PARTIAL_SUFFIX,
    AccountStats,
    build_manifest,
    new_package_id,
    write_manifest,
)
from ig_orchestrator.exchange.pull import _copy_verified, _prune_empty_dirs

PUBLISHABLE_STATUSES = ("AWAITING_RENAME", "COMPLETED", "PARTIAL")
ProgressCallback = Callable[[int, int], None]


@dataclass(slots=True)
class PublishResult:
    ok: bool = False
    package_id: str = ""
    path: Path | None = None
    accounts: int = 0
    files: int = 0
    bytes: int = 0
    missing_accounts: list[str] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "pkg"


def local_exchange_root(conn: sqlite3.Connection) -> Path | None:
    """Shared folder as seen from this instance (``exchange_local_path``)."""

    local = InstanceRepository(conn).get_local()
    if local is None:
        return None
    text = local.exchange_local_path or local.exchange_path
    return Path(text) if text else None


AUTO_PUBLISH_SETTING = "exchange.auto_publish"
PUBLISH_MODE_SETTING = "exchange.publish_mode"


def read_publish_settings(conn: sqlite3.Connection) -> tuple[bool, str]:
    """``(auto_publish, mode)``; auto-publish only counts on a local WORKER instance."""

    def value(key: str, default: str) -> str:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]).strip() if row is not None and str(row[0]).strip() else default

    local = InstanceRepository(conn).get_local()
    auto = value(AUTO_PUBLISH_SETTING, "0").lower() in {"1", "true", "yes"}
    mode = value(PUBLISH_MODE_SETTING, "MOVE").upper()
    return auto and local is not None and local.role == "WORKER", mode if mode in {"MOVE", "COPY"} else "MOVE"


def write_publish_settings(conn: sqlite3.Connection, auto: bool, mode: str) -> None:
    for key, value, kind in (
        (AUTO_PUBLISH_SETTING, "1" if auto else "0", "BOOLEAN"),
        (PUBLISH_MODE_SETTING, mode if mode in {"MOVE", "COPY"} else "MOVE", "TEXT"),
    ):
        conn.execute(
            "INSERT INTO app_settings (key, value, value_type, updated_at) VALUES (?, ?, ?, datetime('now'))"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, kind),
        )
    conn.commit()


def unpublished_batches(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Finished batches that are not part of a PUBLISHED package yet (newest first)."""

    published: set[int] = set()
    for row in conn.execute("SELECT batch_ids FROM exchange_publications WHERE status = 'PUBLISHED'"):
        try:
            published.update(int(i) for i in json.loads(row[0]))
        except (ValueError, TypeError):
            continue
    marks = ",".join("?" for _ in PUBLISHABLE_STATUSES)
    rows = conn.execute(
        f"SELECT b.id, b.name, bs.code FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id"
        f" WHERE bs.code IN ({marks}) ORDER BY b.id DESC LIMIT 100",
        PUBLISHABLE_STATUSES,
    ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows if int(r[0]) not in published]


def _account_folders(working: Path) -> dict[str, Path]:
    try:
        return {e.name.casefold(): Path(e.path) for e in os.scandir(working) if e.is_dir()}
    except OSError:
        return {}


def cleanup_partials(root: Path, instance: str, *, older_than_hours: float = 24.0) -> int:
    """Remove stale ``.partial`` folders of this instance that never got a manifest."""

    removed = 0
    prefix = _safe(instance) + "_"
    try:
        entries = list(os.scandir(root))
    except OSError:
        return 0
    for entry in entries:
        if not (entry.is_dir() and entry.name.endswith(PARTIAL_SUFFIX) and entry.name.startswith(prefix)):
            continue
        if (Path(entry.path) / MANIFEST_NAME).is_file():
            continue
        if time.time() - entry.stat().st_mtime > older_than_hours * 3600:
            shutil.rmtree(entry.path, ignore_errors=True)
            removed += 1
    return removed


def _record(conn: sqlite3.Connection, package_id: str, batch_ids: list[int], status: str, *,
            path: str | None = None, files: int = 0, size: int = 0, error: str | None = None) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO exchange_publications (package_id, batch_ids, status, path, files, bytes, error,
                                           created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(package_id) DO UPDATE SET status = excluded.status, path = excluded.path,
            files = excluded.files, bytes = excluded.bytes, error = excluded.error,
            updated_at = excluded.updated_at
        """,
        (package_id, json.dumps(batch_ids), status, path, files, size, error, now, now),
    )
    conn.commit()


def publish_batches(
    conn: sqlite3.Connection,
    batch_ids: list[int],
    working_folder: Path,
    exchange_root: Path,
    *,
    instance: str,
    mode: str = "MOVE",
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> PublishResult:
    """Copy the batches' account folders into a new package. ``mode`` is ``MOVE`` or ``COPY``."""

    result = PublishResult(package_id=new_package_id())
    cancel = cancel_event or threading.Event()
    if not batch_ids:
        result.error = "No hay lotes que publicar"
        return result
    if not os.path.isdir(exchange_root):
        result.error = f"La carpeta compartida no esta disponible: {exchange_root}"
        _record(conn, result.package_id, batch_ids, "PENDING", error=result.error)
        return result

    marks = ",".join("?" for _ in batch_ids)
    usernames = [
        str(r[0])
        for r in conn.execute(
            f"SELECT DISTINCT a.username FROM batch_accounts ba JOIN catalog_accounts a"
            f" ON a.id = ba.catalog_account_id WHERE ba.batch_id IN ({marks}) ORDER BY a.username COLLATE NOCASE",
            batch_ids,
        )
    ]
    folders = _account_folders(working_folder)
    plan: list[tuple[str, Path, list[tuple[Path, int, float]]]] = []
    for username in usernames:
        folder = folders.get(username.casefold())
        if folder is None:
            result.missing_accounts.append(username)
            continue
        plan.append((username, folder, list(iter_files(folder))))
    total_files = sum(len(files) for _u, _f, files in plan)
    total_bytes = sum(size for _u, _f, files in plan for _p, size, _m in files)

    try:
        free = shutil.disk_usage(exchange_root).free
    except OSError:
        free = None
    if free is not None and free < total_bytes:
        result.error = f"Espacio insuficiente en la compartida: {total_bytes} B necesarios, {free} B libres"
        _record(conn, result.package_id, batch_ids, "FAILED", error=result.error)
        return result

    first_batch = conn.execute("SELECT name FROM batches WHERE id = ?", (batch_ids[0],)).fetchone()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = _safe(f"{instance}_{first_batch[0] if first_batch else 'batch'}_{stamp}")
    final_dir = exchange_root / name
    partial_dir = exchange_root / (name + PARTIAL_SUFFIX)
    cleanup_partials(exchange_root, instance)
    stats: dict[str, AccountStats] = {}
    manifest_files: list[dict] = []
    copied: list[tuple[Path, Path]] = []
    done = 0
    try:
        os.makedirs(long_path(partial_dir / "data"), exist_ok=False)
        for username, folder, files in plan:
            account_stats = AccountStats(folder=f"data/{username}")
            stats[username.casefold()] = account_stats
            for rel, size, _mtime in files:
                if cancel.is_set():
                    result.cancelled = True
                    break
                destination = partial_dir / "data" / username / rel
                _copy_verified(folder / rel, destination, size)
                copied.append((folder / rel, destination))
                account_stats.count += 1
                account_stats.bytes += size
                manifest_files.append({"path": f"data/{username}/{rel.as_posix()}", "size": size})
                done += 1
                if progress is not None:
                    progress(done, total_files)
            if result.cancelled:
                break
        if result.cancelled:
            shutil.rmtree(partial_dir, ignore_errors=True)
            result.error = "Cancelado"
            return result
        manifest = build_manifest(
            conn, batch_ids, package_id=result.package_id, instance=instance, stats=stats, files=manifest_files
        )
        write_manifest(partial_dir, manifest)  # last write: the package is complete
        counter = 1
        while final_dir.exists():
            counter += 1
            final_dir = exchange_root / f"{name}_{counter}"
        os.rename(partial_dir, final_dir)
    except OSError as exc:
        result.error = f"Fallo al publicar: {exc}"
        _record(conn, result.package_id, batch_ids, "FAILED", error=result.error)
        return result

    if mode.upper() == "MOVE":
        for source, _destination in copied:
            try:
                os.remove(long_path(source))
            except OSError:
                pass
        for _username, folder, _files in plan:
            _prune_empty_dirs(folder)
    result.ok = True
    result.path = final_dir
    result.accounts = len(plan)
    result.files = done
    result.bytes = total_bytes
    _record(conn, result.package_id, batch_ids, "PUBLISHED", path=str(final_dir), files=done, size=total_bytes)
    return result
