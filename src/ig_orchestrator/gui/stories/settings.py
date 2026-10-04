"""Persist last-used Stories inbox paths in GUI ``app_settings``."""

from __future__ import annotations

from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.shared.helpers import _gui_setting

STORIES_INBOX_SETTING = "stories.inbox_path"
STORIES_DB_SETTING = "stories.accounts_db_path"


def load_story_inbox_settings(connection: Connection) -> tuple[str, str]:
    inbox = _gui_setting(connection, STORIES_INBOX_SETTING, "")
    accounts_db = _gui_setting(connection, STORIES_DB_SETTING, "")
    return inbox, accounts_db


def save_story_inbox_settings(
    connection: Connection,
    *,
    inbox: str,
    accounts_db: str,
) -> None:
    if not is_gui_schema(connection):
        return
    for key, value in (
        (STORIES_INBOX_SETTING, inbox.strip()),
        (STORIES_DB_SETTING, accounts_db.strip()),
    ):
        connection.execute(
            """
            INSERT INTO app_settings (key, value, value_type, updated_at)
            VALUES (?, ?, 'PATH', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (key, value),
        )
    connection.commit()


__all__ = [
    "STORIES_DB_SETTING",
    "STORIES_INBOX_SETTING",
    "load_story_inbox_settings",
    "save_story_inbox_settings",
]
