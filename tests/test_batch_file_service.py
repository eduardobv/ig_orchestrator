from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.input import backup_and_clean_batch_json, parse_batch_json


def test_backup_and_clean_batch_json_preserves_reusable_account_fields(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    batch_path = config_dir / "batch.json"
    original = {
        "schema_version": "1.0",
        "batch_name": "descargas_21_junio_2026",
        "defaults": {"start_now_date": "2026-06-21"},
        "accounts": [
            {
                "username": "lerabuns",
                "start_now_date": "2026-06-21",
                "download_stories": True,
                "urls": ["https://www.instagram.com/reel/ABC123/"],
            }
        ],
    }
    batch_path.write_text(json.dumps(original), encoding="utf-8")
    parsed = parse_batch_json(batch_path)

    result = backup_and_clean_batch_json(parsed)

    assert result.backup_path == (
        config_dir / "bkp" / "descargas_21_junio_2026_batch.json"
    )
    assert json.loads(result.backup_path.read_text(encoding="utf-8")) == original
    cleaned = json.loads(batch_path.read_text(encoding="utf-8"))
    assert cleaned["accounts"] == [
        {
            "username": "lerabuns",
            "start_now_date": "2026-06-21",
            "download_stories": False,
            "urls": [],
        }
    ]
