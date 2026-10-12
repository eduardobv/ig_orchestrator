"""``ig_orchestrator.batch_result`` package manifest: build, write, read, validate."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator import __version__

FORMAT = "ig_orchestrator.batch_result"
FORMAT_VERSION = "1"
MIN_READER_VERSION = "3.6.0"
MANIFEST_NAME = "manifest.json"
IMPORTED_NAME = "imported.json"
PARTIAL_SUFFIX = ".partial"


class ManifestError(ValueError):
    """The manifest cannot be read or is not compatible with this app."""


def parse_version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in str(text).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


@dataclass(slots=True)
class AccountStats:
    folder: str | None = None
    count: int = 0
    bytes: int = 0


@dataclass(slots=True)
class PackageInfo:
    path: Path
    package_id: str
    source_instance: str
    created_at: str
    batch_names: list[str]
    accounts: int
    files: int
    bytes: int
    imported: bool = False
    problem: str = ""
    manifest: dict = field(default_factory=dict)


def new_package_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_manifest(
    conn: sqlite3.Connection,
    batch_ids: list[int],
    *,
    package_id: str,
    instance: str,
    stats: dict[str, AccountStats],
    files: list[dict],
) -> dict:
    """Manifest dict for finished batches of *conn* and the copied files.

    ``stats`` maps ``username.casefold()`` to the copied folder/count/bytes.
    """

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    batches = []
    for batch_id in batch_ids:
        batch = conn.execute(
            "SELECT b.id, b.name, b.start_date, bs.code AS status FROM batches b"
            " JOIN batch_statuses bs ON bs.id = b.status_id WHERE b.id = ?",
            (batch_id,),
        ).fetchone()
        if batch is None:
            raise ManifestError(f"Lote no encontrado: {batch_id}")
        accounts = []
        for row in conn.execute(
            """
            SELECT ba.id, a.username, a.instagram_user_id, ba.download_stories, ba.is_new_account,
                   ba.is_catalog_update, ba.rename_owner_id, ba.rename_start_init_date,
                   ba.rename_destination_path, ba.priority
            FROM batch_accounts ba JOIN catalog_accounts a ON a.id = ba.catalog_account_id
            WHERE ba.batch_id = ? ORDER BY ba.sort_order
            """,
            (batch_id,),
        ):
            account_stats = stats.get(str(row["username"]).casefold(), AccountStats())
            urls = [
                {
                    "url": u["url"],
                    "type": u["type"],
                    "source": u["source"],
                    "status": u["status"],
                    "retries": u["retries"],
                    "error_code": u["error_code"],
                    "error_text": u["error_text"],
                    "files": u["files"],
                }
                for u in conn.execute(
                    """
                    SELECT bu.url, pt.code AS type, us.code AS source, bus.code AS status, bu.retries,
                           be.code AS error_code, bu.last_error_text AS error_text,
                           (SELECT COUNT(*) FROM downloaded_files d WHERE d.batch_url_id = bu.id) AS files
                    FROM batch_urls bu
                    JOIN publication_types pt ON pt.id = bu.publication_type_id
                    JOIN url_sources us ON us.id = bu.source_id
                    JOIN batch_url_statuses bus ON bus.id = bu.status_id
                    LEFT JOIN bot_errors be ON be.id = bu.last_error_id
                    WHERE bu.batch_account_id = ? ORDER BY bu.id
                    """,
                    (row["id"],),
                )
            ]
            accounts.append(
                {
                    "username": row["username"],
                    "instagram_user_id": row["instagram_user_id"],
                    "download_stories": bool(row["download_stories"]),
                    "is_new_account": bool(row["is_new_account"]),
                    "is_catalog_update": bool(row["is_catalog_update"]),
                    "priority": int(row["priority"] or 0),
                    "rename": {
                        "owner_id": row["rename_owner_id"],
                        "start_init_date": row["rename_start_init_date"],
                        "destination_path": row["rename_destination_path"],
                    },
                    "folder": account_stats.folder,
                    "files": {"count": account_stats.count, "bytes": account_stats.bytes},
                    "urls": urls,
                }
            )
        batches.append(
            {
                "batch_name": batch["name"],
                "start_date": batch["start_date"],
                "final_status": batch["status"],
                "accounts": accounts,
            }
        )
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": package_id,
        "created_at": _now(),
        "source": {"instance": instance, "app_version": __version__, "schema_user_version": version},
        "min_reader_version": MIN_READER_VERSION,
        "batches": batches,
        "files": files,
    }


def write_manifest(directory: Path, manifest: dict) -> Path:
    """Write ``manifest.json`` atomically (tmp + replace). Must be the last write of a package."""

    target = directory / MANIFEST_NAME
    temporary = directory / (MANIFEST_NAME + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return target


def validate_manifest(data: object, *, app_version: str = __version__) -> dict:
    if not isinstance(data, dict):
        raise ManifestError("El manifiesto no es un objeto JSON")
    if data.get("format") != FORMAT:
        raise ManifestError(f"Formato desconocido: {data.get('format')!r}")
    if parse_version(str(data.get("format_version", "0"))) > parse_version(FORMAT_VERSION):
        raise ManifestError(f"Version de formato {data.get('format_version')} no soportada por esta app")
    minimum = str(data.get("min_reader_version", "0"))
    if parse_version(minimum) > parse_version(app_version):
        raise ManifestError(f"El paquete requiere la app {minimum} o superior (esta es la {app_version})")
    if not data.get("package_id"):
        raise ManifestError("Falta package_id")
    if not isinstance(data.get("batches"), list):
        raise ManifestError("Falta la lista de lotes")
    return data


def read_package(directory: Path, *, app_version: str = __version__) -> PackageInfo:
    """Read a package directory; ``problem`` explains why it is not importable."""

    info = PackageInfo(directory, "", "", "", [], 0, 0, 0)
    manifest_path = directory / MANIFEST_NAME
    info.imported = (directory / IMPORTED_NAME).is_file()
    if directory.name.endswith(PARTIAL_SUFFIX) or not manifest_path.is_file():
        info.problem = "Incompleto (sin manifiesto)"
        return info
    try:
        data = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")), app_version=app_version)
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        info.problem = str(exc)
        return info
    files = data.get("files") or []
    info.package_id = str(data["package_id"])
    info.source_instance = str((data.get("source") or {}).get("instance", ""))
    info.created_at = str(data.get("created_at", ""))
    info.batch_names = [str(b.get("batch_name", "")) for b in data["batches"]]
    info.accounts = sum(len(b.get("accounts", [])) for b in data["batches"])
    info.files = len(files)
    info.bytes = sum(int(f.get("size", 0)) for f in files)
    info.manifest = data
    return info


def scan_packages(root: Path, *, app_version: str = __version__) -> list[PackageInfo]:
    """Packages (directories that contain or are meant to contain a manifest) in *root*."""

    packages = []
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name.casefold())
    except OSError:
        return []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            path = Path(entry.path)
            if entry.name.endswith(PARTIAL_SUFFIX) or (path / MANIFEST_NAME).is_file():
                packages.append(read_package(path, app_version=app_version))
        except OSError:
            continue
    return packages
