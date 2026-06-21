from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ig_orchestrator.input.batch_json_parser import ParsedBatch


@dataclass(frozen=True, slots=True)
class BatchFileFinalization:
    backup_path: Path
    input_path: Path


def backup_and_clean_batch_json(
    parsed_batch: ParsedBatch,
    *,
    backup_directory: Path | None = None,
) -> BatchFileFinalization:
    input_path = parsed_batch.source_file
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Batch JSON root must be an object")

    backup_root = backup_directory or input_path.parent / "bkp"
    backup_root.mkdir(parents=True, exist_ok=True)
    safe_batch_name = re.sub(r'[<>:"/\\|?*]+', "_", parsed_batch.batch_name).strip()
    backup_path = backup_root / f"{safe_batch_name}_batch.json"
    shutil.copy2(input_path, backup_path)

    raw_accounts = payload.get("accounts", [])
    cleaned_accounts: list[dict[str, Any]] = []
    if isinstance(raw_accounts, list):
        for raw_account in raw_accounts:
            if not isinstance(raw_account, dict):
                continue
            cleaned_account = {
                "username": raw_account.get("username", ""),
                "start_now_date": raw_account.get(
                    "start_now_date",
                    payload.get("defaults", {}).get("start_now_date")
                    if isinstance(payload.get("defaults"), dict)
                    else None,
                ),
                "download_stories": False,
                "urls": [],
            }
            cleaned_accounts.append(cleaned_account)
    payload["accounts"] = cleaned_accounts
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return BatchFileFinalization(backup_path=backup_path, input_path=input_path)


__all__ = ["BatchFileFinalization", "backup_and_clean_batch_json"]
