from __future__ import annotations

from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.account_catalog_service import AccountCatalogEntry
from ig_orchestrator.models import AccountHistoryStatus


DEFAULT_CATALOG_COLORS = {
    "favorite": "#d9ead3",
    "inactive": "#fff2cc",
    "in_batch": "#f5c08c",
    "today": "#fff59d",
    "disabled": "#f4cccc",
    "enabled": "",
    "changed": "#cfe2f3",
}


def load_catalog_colors(connection: Connection) -> dict[str, str]:
    colors = dict(DEFAULT_CATALOG_COLORS)
    if not is_gui_schema(connection):
        return colors
    for key, setting_key in (
        ("favorite", "ui.color_favorite"),
        ("in_batch", "ui.color_in_batch"),
        ("today", "ui.color_today"),
    ):
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (setting_key,),
        ).fetchone()
        if row is not None and str(row["value"]).startswith("#"):
            colors[key] = str(row["value"])
    for row in connection.execute(
        "SELECT code, color_hex FROM catalog_account_statuses"
    ):
        code = str(row["code"]).casefold()
        hex_color = row["color_hex"]
        if hex_color and str(hex_color).startswith("#"):
            colors[code] = str(hex_color)
    return colors


def save_color(connection: Connection, key: str, hex_color: str) -> None:
    if not is_gui_schema(connection):
        return
    mapping = {
        "favorite": "ui.color_favorite",
        "in_batch": "ui.color_in_batch",
        "today": "ui.color_today",
    }
    if key in mapping:
        connection.execute(
            """
            INSERT INTO app_settings (key, value, value_type, updated_at)
            VALUES (?, ?, 'TEXT', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (mapping[key], hex_color),
        )
    else:
        connection.execute(
            """
            UPDATE catalog_account_statuses
            SET color_hex = ?
            WHERE lower(code) = ?
            """,
            (hex_color, key.casefold()),
        )
    connection.commit()


def colors_for_entry(
    entry: AccountCatalogEntry,
    palette: dict[str, str],
    *,
    in_batch: bool = False,
    today: bool = False,
) -> dict[str, str]:
    if entry.status is AccountHistoryStatus.DISABLED:
        return _bg(palette.get("disabled"))
    if in_batch:
        return _bg(palette.get("in_batch"))
    if today:
        return _bg(palette.get("today"))
    if entry.status is AccountHistoryStatus.INACTIVE:
        return _bg(palette.get("inactive"))
    if entry.is_favorite:
        return _bg(palette.get("favorite"))
    if entry.status is AccountHistoryStatus.CHANGED:
        return _bg(palette.get("changed"))
    return _bg(palette.get("enabled"))


def _bg(color: str | None) -> dict[str, str]:
    if not color:
        return {}
    return {"background": color}


__all__ = [
    "DEFAULT_CATALOG_COLORS",
    "colors_for_entry",
    "load_catalog_colors",
    "save_color",
]
