"""Renamer settings stored in ``app_settings``."""

from __future__ import annotations

import sqlite3

ENGINE_SETTING = "renaming.engine"  # integrated | legacy_sc2
PREVIEW_SETTING = "renaming.preview"  # 1 = always show the preview before renaming
INTEGRATED, LEGACY = "integrated", "legacy_sc2"


class NoSettingsTable(Exception):
    """The connection is a v1 database (no ``app_settings``)."""


def _value(conn: sqlite3.Connection, key: str, default: str) -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError as exc:
        raise NoSettingsTable from exc
    return str(row[0]).strip() if row is not None and str(row[0]).strip() else default


def read_engine(conn: sqlite3.Connection) -> str:
    try:
        value = _value(conn, ENGINE_SETTING, INTEGRATED)
    except NoSettingsTable:
        return LEGACY  # the integrated renamer needs the v2 catalog
    return value if value in (INTEGRATED, LEGACY) else INTEGRATED


def preview_required(conn: sqlite3.Connection) -> bool:
    try:
        return _value(conn, PREVIEW_SETTING, "1").lower() in {"1", "true", "yes"}
    except NoSettingsTable:
        return True


def write_setting(conn: sqlite3.Connection, key: str, value: str, kind: str = "TEXT") -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value, value_type, updated_at) VALUES (?, ?, ?, datetime('now'))"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, kind),
    )
    conn.commit()


def staging_after_rename(conn: sqlite3.Connection) -> str:
    """``ASK`` | ``STAGING`` | ``LIBRARY`` (what to do with renamed folders)."""

    try:
        value = _value(conn, "staging.after_rename", "ASK").upper()
    except NoSettingsTable:
        return "LIBRARY"
    return value if value in ("ASK", "STAGING", "LIBRARY") else "ASK"


def staging_root_setting(conn: sqlite3.Connection) -> str:
    try:
        return _value(conn, "staging.root", "")
    except NoSettingsTable:
        return ""


def lite_mirror_enabled(conn: sqlite3.Connection) -> bool:
    try:
        return _value(conn, "compat.lite.enabled", "1").lower() not in {"0", "false", "no"}
    except NoSettingsTable:
        return True
