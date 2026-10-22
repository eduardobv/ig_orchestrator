"""MAIN side: faithfully import a published package (files + real URL results)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.exchange.inbox_scan import long_path, scan_exchange
from ig_orchestrator.exchange.manifest import IMPORTED_NAME, PackageInfo
from ig_orchestrator.exchange.pull import PullPolicy, PullResult, _prune_empty_dirs, execute_pull, plan_pull

ProgressCallback = Callable[[str, int, int], None]
ATTACHABLE_STATUSES = ("DRAFT", "IMPORTED")


@dataclass(slots=True)
class ImportResult:
    ok: bool = False
    skipped_duplicate: bool = False
    package_id: str = ""
    batch_ids: list[int] = field(default_factory=list)
    batches_created: int = 0
    batches_attached: int = 0
    accounts: int = 0
    urls: int = 0
    files: int = 0
    bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    pull: PullResult | None = None

    def summary(self) -> str:
        if self.skipped_duplicate:
            return "El paquete ya estaba importado: no se hizo nada."
        if not self.ok:
            return f"No se importo: {self.error}"
        return (
            f"Importado: {self.batches_created} lote(s) nuevo(s), {self.batches_attached} adjuntado(s), "
            f"{self.accounts} cuenta(s), {self.urls} URL(s), {self.files} fichero(s)."
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_package_files(package: PackageInfo) -> list[str]:
    """Problems found comparing ``files[]`` of the manifest with the package on disk."""

    problems = []
    for entry in package.manifest.get("files", []):
        target = package.path / Path(*str(entry["path"]).split("/"))
        try:
            size = os.stat(long_path(target)).st_size
        except OSError:
            problems.append(f"Falta {entry['path']}")
            continue
        if size != int(entry.get("size", -1)):
            problems.append(f"Tamano distinto: {entry['path']}")
    return problems


def _remove_package_data(package: PackageInfo) -> None:
    for entry in package.manifest.get("files", []):
        try:
            os.remove(long_path(package.path / Path(*str(entry["path"]).split("/"))))
        except OSError:
            pass
    _prune_empty_dirs(package.path / "data")


def already_imported(conn: sqlite3.Connection, package_id: str) -> bool:
    return conn.execute("SELECT 1 FROM exchange_imports WHERE package_id = ?", (package_id,)).fetchone() is not None


def import_package(
    conn: sqlite3.Connection,
    package: PackageInfo,
    working_folder: Path,
    *,
    keep_source: bool = False,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> ImportResult:
    result = ImportResult(package_id=package.package_id)
    if package.problem:
        result.error = package.problem
        return result
    if already_imported(conn, package.package_id) or package.imported:
        result.ok = True
        result.skipped_duplicate = True
        return result
    problems = verify_package_files(package)
    if problems:
        result.error = "Paquete danado: " + "; ".join(problems[:5])
        return result

    data_dir = package.path / "data"
    folders = scan_exchange(data_dir, stable_seconds=0) if data_dir.is_dir() else []
    # Always copy first; the package files are removed only after the batch is registered,
    # so a failed registration can be retried from the same package.
    plan = plan_pull(folders, working_folder, PullPolicy.MERGE_SKIP_IDENTICAL, keep_source=True)
    if not plan.has_enough_space:
        result.error = f"Espacio insuficiente en destino ({plan.required_bytes} B necesarios)"
        return result
    pulled = execute_pull(plan, progress=progress, cancel_event=cancel_event)
    result.pull = pulled
    if pulled.cancelled or not pulled.ok:
        errors = [e for f in pulled.folders for e in f.errors]
        result.error = "Copia de ficheros interrumpida" + (": " + "; ".join(errors[:3]) if errors else "")
        return result
    result.files = sum(f.copied + f.skipped_identical for f in pulled.folders)
    result.bytes = sum(f.bytes_copied for f in pulled.folders)

    try:
        _apply_to_database(conn, package, result)
        conn.execute(
            "INSERT INTO exchange_imports (package_id, source_instance, batch_id, imported_at, files, bytes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (package.package_id, package.source_instance, result.batch_ids[0] if result.batch_ids else None,
             _now(), result.files, result.bytes),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - reported; files were already copied (re-import is safe)
        conn.rollback()
        result.error = f"Los ficheros se copiaron pero no se pudo registrar el lote: {exc}"
        return result
    if not keep_source:
        _remove_package_data(package)
    try:
        (package.path / IMPORTED_NAME).write_text(
            json.dumps({"imported_at": _now(), "batch_ids": result.batch_ids}), encoding="utf-8"
        )
    except OSError:
        result.warnings.append("No se pudo escribir imported.json (el paquete esta registrado en la base)")
    result.ok = True
    return result


# ------------------------------------------------------------------ database
def _lookup(conn: sqlite3.Connection, table: str, code: str | None, default: str | None = None) -> int | None:
    for candidate in (code, default):
        if candidate:
            row = conn.execute(f"SELECT id FROM {table} WHERE code = ?", (candidate,)).fetchone()
            if row is not None:
                return int(row[0])
    return None


def _resolve_account(conn: sqlite3.Connection, account: dict, result: ImportResult) -> int:
    owner = str(account.get("instagram_user_id") or "").strip()
    username = str(account["username"]).strip()
    row = None
    if owner:
        row = conn.execute(
            "SELECT id, username FROM catalog_accounts WHERE instagram_user_id = ? ORDER BY id LIMIT 1", (owner,)
        ).fetchone()
        if row is not None and str(row["username"]).casefold() != username.casefold():
            result.warnings.append(f"@{username} se llama @{row['username']} en esta instancia (mismo id de Instagram)")
    if row is None:
        row = conn.execute(
            "SELECT id, username FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
    if row is not None:
        return int(row["id"])
    now = _now()
    cursor = conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, status_id, is_favorite, created_at, updated_at)"
        " VALUES (?, ?, ?, 0, ?, ?)",
        (username, owner or None, _lookup(conn, "catalog_account_statuses", "ENABLED"), now, now),
    )
    return int(cursor.lastrowid)


def _account_status(urls: list[dict]) -> str:
    if not urls:
        return "COMPLETED"
    done = sum(1 for u in urls if u.get("status") == "COMPLETED")
    if done == len(urls):
        return "COMPLETED"
    return "PARTIAL" if done else "FAILED"


def _unique_batch_name(conn: sqlite3.Connection, name: str, instance: str) -> str:
    candidate = f"{name}_{instance}" if instance else f"{name}_imp"
    counter = 1
    while conn.execute("SELECT 1 FROM batches WHERE name = ?", (candidate,)).fetchone():
        counter += 1
        candidate = f"{name}_{instance or 'imp'}{counter}"
    return candidate


def _apply_to_database(conn: sqlite3.Connection, package: PackageInfo, result: ImportResult) -> None:
    instance = package.source_instance
    now = _now()
    for batch in package.manifest["batches"]:
        name = str(batch["batch_name"])
        existing = conn.execute(
            "SELECT b.id, bs.code AS status FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id"
            " WHERE b.name = ?",
            (name,),
        ).fetchone()
        attach = existing is not None and existing["status"] in ATTACHABLE_STATUSES
        if attach:
            batch_id = int(existing["id"])
            result.batches_attached += 1
            conn.execute(
                "UPDATE batches SET status_id = ?, updated_at = ? WHERE id = ?",
                (_lookup(conn, "batch_statuses", "AWAITING_RENAME"), now, batch_id),
            )
        else:
            final_name = name if existing is None else _unique_batch_name(conn, name, instance)
            if final_name != name:
                result.warnings.append(f"El lote {name} ya existia aqui: se creo como {final_name}")
            batch_id = int(conn.execute(
                "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
                " VALUES (?, '1.0', ?, ?, ?, ?)",
                (final_name, _lookup(conn, "batch_statuses", "AWAITING_RENAME"),
                 str(batch.get("start_date") or now[:10]), now, now),
            ).lastrowid)
            result.batches_created += 1
        result.batch_ids.append(batch_id)
        run_id = int(conn.execute(
            "INSERT INTO batch_runs (batch_id, batch_account_id, status_id, started_at, finished_at, summary)"
            " VALUES (?, NULL, ?, ?, ?, ?)",
            (batch_id, _lookup(conn, "batch_run_statuses", "COMPLETED"), now, now,
             f"Imported from {instance or 'other instance'} (package {package.package_id})"),
        ).lastrowid)
        totals = {"total": 0, "completed": 0, "failed": 0, "files": 0}
        for order, account in enumerate(batch.get("accounts", []), start=1):
            _import_account(conn, batch_id, run_id, order, account, attach, now, result, totals)
        failed_status = "PARTIAL" if totals["completed"] and totals["failed"] else (
            "FAILED" if totals["failed"] and not totals["completed"] else "COMPLETED")
        conn.execute(
            "UPDATE batch_runs SET total_urls = ?, completed_urls = ?, failed_urls = ?, downloaded_files = ?,"
            " status_id = ? WHERE id = ?",
            (totals["total"], totals["completed"], totals["failed"], totals["files"],
             _lookup(conn, "batch_run_statuses", failed_status), run_id),
        )


def _import_account(conn, batch_id, run_id, order, account, attach, now, result, totals) -> None:
    catalog_id = _resolve_account(conn, account, result)
    rename = account.get("rename") or {}
    urls = account.get("urls") or []
    status_id = _lookup(conn, "batch_account_statuses", _account_status(urls), "COMPLETED")
    values = (
        int(bool(account.get("download_stories"))), int(bool(account.get("is_new_account"))),
        int(bool(account.get("is_catalog_update"))), rename.get("owner_id"), rename.get("start_init_date"),
        rename.get("destination_path"), status_id,
    )
    row = conn.execute(
        "SELECT id FROM batch_accounts WHERE batch_id = ? AND catalog_account_id = ?", (batch_id, catalog_id)
    ).fetchone() if attach else None
    if row is not None:
        account_row_id = int(row["id"])
        conn.execute(
            "UPDATE batch_accounts SET download_stories = ?, is_new_account = ?, is_catalog_update = ?,"
            " rename_owner_id = ?, rename_start_init_date = ?, rename_destination_path = ?, status_id = ?,"
            " updated_at = ? WHERE id = ?",
            (*values, now, account_row_id),
        )
    else:
        account_row_id = int(conn.execute(
            """
            INSERT INTO batch_accounts (batch_id, catalog_account_id, download_stories, is_new_account,
                is_catalog_update, rename_owner_id, rename_start_init_date, rename_destination_path, status_id,
                working_folder_rel, sort_order, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, catalog_id, *values, account["username"], order, int(account.get("priority") or 0), now, now),
        ).lastrowid)
    result.accounts += 1
    for url in urls:
        _import_url(conn, account_row_id, run_id, url, now, totals)
    totals["files"] += int((account.get("files") or {}).get("count", 0))
    result.urls += len(urls)


def _import_url(conn, account_row_id, run_id, url, now, totals) -> None:
    status = str(url.get("status") or "PENDING")
    status_id = _lookup(conn, "batch_url_statuses", status, "PENDING")
    error_id = _lookup(conn, "bot_errors", url.get("error_code"))
    final = status in ("COMPLETED", "FAILED_FINAL")
    fields = (
        status_id, int(url.get("retries") or 0), error_id, url.get("error_text"),
        int(status == "FAILED_FINAL"), run_id, now if final else None,
    )
    existing = conn.execute(
        "SELECT id FROM batch_urls WHERE batch_account_id = ? AND url = ?", (account_row_id, url["url"])
    ).fetchone()
    if existing is not None:
        conn.execute(
            "UPDATE batch_urls SET status_id = ?, retries = ?, last_error_id = ?, last_error_text = ?,"
            " non_retryable = ?, batch_run_id = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (*fields, now, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO batch_urls (batch_account_id, batch_run_id, url, publication_type_id, source_id, status_id,
                retries, last_error_id, last_error_text, non_retryable, finished_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_row_id, run_id, url["url"],
             _lookup(conn, "publication_types", url.get("type"), "UNKNOWN"),
             _lookup(conn, "url_sources", url.get("source"), "INPUT_URL"),
             status_id, int(url.get("retries") or 0), error_id, url.get("error_text"),
             int(status == "FAILED_FINAL"), now if final else None, now, now),
        )
    totals["total"] += 1
    totals["completed"] += int(status == "COMPLETED")
    totals["failed"] += int(status == "FAILED_FINAL")
