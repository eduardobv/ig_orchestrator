from __future__ import annotations

from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.stories.settings import (
    STORIES_DB_SETTING,
    STORIES_INBOX_SETTING,
    load_story_inbox_settings,
    save_story_inbox_settings,
)


def test_story_inbox_settings_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        assert load_story_inbox_settings(connection) == ("", "")
        save_story_inbox_settings(
            connection,
            inbox=r"G:\inbox\stories",
            accounts_db=r"G:\4K Stogram\accounts.db",
        )
        assert load_story_inbox_settings(connection) == (
            r"G:\inbox\stories",
            r"G:\4K Stogram\accounts.db",
        )
        keys = {
            str(row["key"])
            for row in connection.execute(
                "SELECT key FROM app_settings WHERE key LIKE 'stories.%'"
            )
        }
        assert keys == {STORIES_INBOX_SETTING, STORIES_DB_SETTING}
        save_story_inbox_settings(
            connection,
            inbox=r"D:\other",
            accounts_db=r"D:\other.db",
        )
        assert load_story_inbox_settings(connection) == (r"D:\other", r"D:\other.db")
