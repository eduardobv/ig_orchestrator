from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import load_batch_draft
from ig_orchestrator.input.batch_creation_service import BatchCreationResult
from ig_orchestrator.settings import Settings

BATCH_EXPORT_FORMAT = "ig_orchestrator.batch_export"
BATCH_EXPORT_FORMAT_VERSION = "1"


class BatchTransferError(ValueError):
    """Raised when an export/import payload is invalid."""


def export_batch_payload(connection: Connection, batch_id: int) -> dict[str, Any]:
    """Build a portable JSON-serializable payload for one batch."""

    row = connection.execute(
        "SELECT id, batch_name, status, schema_version FROM input_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchTransferError(f"Batch not found: {batch_id}")
    draft = load_batch_draft(connection, batch_id)
    return {
        "format": BATCH_EXPORT_FORMAT,
        "format_version": BATCH_EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "batch": {
            "batch_name": draft.batch_name,
            "schema_version": draft.schema_version,
            "source_status": str(row["status"]),
            "source_batch_id": int(row["id"]),
            "default_start_now_date": draft.default_start_now_date,
            "accounts": [
                {
                    "username": account.username,
                    "download_stories": bool(account.download_stories),
                    "start_now_date": account.start_now_date,
                    "urls": list(account.urls),
                    "is_new_account": bool(account.is_new_account),
                    "is_catalog_update": bool(account.is_catalog_update),
                    "owner_id": account.owner_id,
                    "start_init_date": account.start_init_date,
                    "destination_path": account.destination_path,
                }
                for account in draft.accounts
            ],
        },
    }


def export_batch_to_path(
    connection: Connection,
    batch_id: int,
    path: Path,
) -> Path:
    import json

    payload = export_batch_payload(connection, batch_id)
    path = Path(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def import_batch_from_payload(
    connection: Connection,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> BatchCreationResult:
    """Import a portable payload as a new DRAFT batch with a unique name."""

    draft = _draft_from_payload(connection, payload)
    return save_batch_draft(
        draft,
        connection,
        settings=settings,
        batch_id=None,
    )


def import_batch_from_path(
    connection: Connection,
    path: Path,
    *,
    settings: Settings | None = None,
) -> BatchCreationResult:
    import json

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchTransferError(f"No se pudo leer el export: {exc}") from exc
    if not isinstance(raw, dict):
        raise BatchTransferError("El export JSON debe ser un objeto")
    return import_batch_from_payload(connection, raw, settings=settings)


def unique_import_batch_name(connection: Connection, base_name: str) -> str:
    base = base_name.strip() or f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if connection.execute(
        "SELECT 1 FROM input_batches WHERE batch_name = ? LIMIT 1",
        (base,),
    ).fetchone() is None:
        return base
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = f"{base}_import_{stamp}"
    if connection.execute(
        "SELECT 1 FROM input_batches WHERE batch_name = ? LIMIT 1",
        (candidate,),
    ).fetchone() is None:
        return candidate
    suffix = 1
    while True:
        numbered = f"{candidate}_{suffix}"
        if connection.execute(
            "SELECT 1 FROM input_batches WHERE batch_name = ? LIMIT 1",
            (numbered,),
        ).fetchone() is None:
            return numbered
        suffix += 1


def _draft_from_payload(
    connection: Connection,
    payload: dict[str, Any],
) -> BatchDraft:
    if payload.get("format") != BATCH_EXPORT_FORMAT:
        raise BatchTransferError(
            f"Formato de export no soportado: {payload.get('format')!r}"
        )
    version = str(payload.get("format_version") or "")
    if version != BATCH_EXPORT_FORMAT_VERSION:
        raise BatchTransferError(
            f"Version de export no soportada: {version!r}"
        )
    batch = payload.get("batch")
    if not isinstance(batch, dict):
        raise BatchTransferError("El export no contiene un objeto 'batch'")

    raw_name = batch.get("batch_name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise BatchTransferError("batch.batch_name es obligatorio")
    default_date = batch.get("default_start_now_date")
    if not isinstance(default_date, str) or not default_date.strip():
        raise BatchTransferError("batch.default_start_now_date es obligatorio")
    schema_version = batch.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        schema_version = "1.0"
    raw_accounts = batch.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise BatchTransferError("batch.accounts debe ser una lista no vacia")

    accounts: list[AccountDraft] = []
    for index, raw in enumerate(raw_accounts, start=1):
        if not isinstance(raw, dict):
            raise BatchTransferError(f"accounts[{index}] debe ser un objeto")
        username = raw.get("username")
        if not isinstance(username, str) or not username.strip():
            raise BatchTransferError(f"accounts[{index}].username es obligatorio")
        urls_raw = raw.get("urls") or []
        if not isinstance(urls_raw, list):
            raise BatchTransferError(f"accounts[{index}].urls debe ser una lista")
        urls = [str(url).strip() for url in urls_raw if str(url).strip()]
        start_now = raw.get("start_now_date") or default_date
        if not isinstance(start_now, str) or not start_now.strip():
            start_now = default_date
        is_new_account = bool(raw.get("is_new_account", False))
        owner_id = str(raw.get("owner_id") or "")
        destination_path = str(raw.get("destination_path") or "")
        if "is_catalog_update" in raw:
            is_catalog_update = bool(raw.get("is_catalog_update"))
        else:
            # Back-compat: metadata without new-account means catalog update.
            is_catalog_update = (
                not is_new_account and bool(owner_id.strip() or destination_path.strip())
            )
        if is_new_account and is_catalog_update:
            is_catalog_update = False
        accounts.append(
            AccountDraft(
                username=username.strip(),
                download_stories=bool(raw.get("download_stories", False)),
                urls=urls,
                start_now_date=start_now.strip(),
                is_new_account=is_new_account,
                is_catalog_update=is_catalog_update,
                owner_id=owner_id,
                start_init_date=str(raw.get("start_init_date") or ""),
                destination_path=destination_path,
            )
        )

    return BatchDraft(
        batch_name=unique_import_batch_name(connection, raw_name.strip()),
        default_start_now_date=default_date.strip(),
        accounts=accounts,
        schema_version=schema_version.strip(),
    )


__all__ = [
    "BATCH_EXPORT_FORMAT",
    "BATCH_EXPORT_FORMAT_VERSION",
    "BatchTransferError",
    "export_batch_payload",
    "export_batch_to_path",
    "import_batch_from_path",
    "import_batch_from_payload",
    "unique_import_batch_name",
]
