from pathlib import Path

from ig_orchestrator.db import (
    AccountHistoryRepository,
    connect,
    import_catalog_from_v1,
    init_database,
    init_gui_database,
    split_destination_path,
)
from ig_orchestrator.models import AccountHistoryStatus


def test_split_destination_path_groups_drive_and_base_folder() -> None:
    segments = split_destination_path(
        r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva"
    )
    assert segments[0] == r"G:\4K Stogram"
    assert segments[1:] == ("00.FAVORITES", "Valeria-Makusheva")


def test_split_destination_path_models_example() -> None:
    segments = split_destination_path(
        r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova"
    )
    assert segments == (
        r"G:\4K Stogram",
        "00.MODELS-A",
        "Lidiia-Filippova",
    )


def test_split_destination_path_blank_is_empty() -> None:
    assert split_destination_path(None) == ()
    assert split_destination_path("   ") == ()


def test_import_catalog_preserves_ids_and_builds_folder_tree(tmp_path: Path) -> None:
    v1_path = tmp_path / "orchestrator.sqlite"
    gui_path = tmp_path / "orchestrator_gui.sqlite"
    init_database(v1_path)
    init_gui_database(gui_path)

    with connect(v1_path) as v1:
        history = AccountHistoryRepository(v1)
        first = history.create_or_get("lerabuns")
        history.update_rename_metadata(
            "lerabuns",
            owner_id="111",
            destination_path=r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva",
            start_init_date="2024-01-01",
        )
        history.set_favorite("lerabuns", favorite=True)
        second = history.create_or_get("lera.berry")
        history.update_identity_and_path(
            "lera.berry",
            owner_id="222",
            destination_path=r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva",
        )
        third = history.create_or_get("lidieblush")
        history.update_rename_metadata(
            "lidieblush",
            owner_id="333",
            destination_path=r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova",
            start_init_date="2025-06-01",
        )
        orphan = history.create_or_get("no_path_user")
        history.update_status("no_path_user", AccountHistoryStatus.INACTIVE)

        with connect(gui_path) as gui:
            result = import_catalog_from_v1(v1, gui)
            result_again = import_catalog_from_v1(v1, gui)

            accounts = {
                str(row["username"]).casefold(): row
                for row in gui.execute("SELECT * FROM catalog_accounts")
            }
            folders = {
                str(row["full_path"]): row
                for row in gui.execute("SELECT * FROM catalog_folders")
            }
            batch_count = int(
                gui.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
            )
            url_count = int(
                gui.execute("SELECT COUNT(*) FROM batch_urls").fetchone()[0]
            )
            file_count = int(
                gui.execute("SELECT COUNT(*) FROM downloaded_files").fetchone()[0]
            )
            inactive_id = int(
                gui.execute(
                    "SELECT id FROM catalog_account_statuses WHERE code = 'INACTIVE'"
                ).fetchone()[0]
            )

    assert result.accounts_imported == 4
    assert result.accounts_without_path == 1
    assert result_again.accounts_imported == 4
    assert first.id is not None
    assert second.id is not None
    assert third.id is not None
    assert orphan.id is not None
    assert int(accounts["lerabuns"]["id"]) == first.id
    assert int(accounts["lera.berry"]["id"]) == second.id
    assert int(accounts["lidieblush"]["id"]) == third.id
    assert int(accounts["no_path_user"]["id"]) == orphan.id
    assert accounts["lerabuns"]["instagram_user_id"] == "111"
    assert accounts["lerabuns"]["start_init_date"] == "2024-01-01"
    assert int(accounts["lerabuns"]["is_favorite"]) == 1
    assert accounts["no_path_user"]["folder_id"] is None
    assert int(accounts["no_path_user"]["status_id"]) == inactive_id

    root = folders[r"G:\4K Stogram"]
    favorites = folders[r"G:\4K Stogram\00.FAVORITES"]
    valeria = folders[r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva"]
    models = folders[r"G:\4K Stogram\00.MODELS-A"]
    lidiia = folders[r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova"]
    assert root["parent_id"] is None
    assert int(root["depth"]) == 0
    assert int(favorites["parent_id"]) == int(root["id"])
    assert int(valeria["parent_id"]) == int(favorites["id"])
    assert int(accounts["lerabuns"]["folder_id"]) == int(valeria["id"])
    assert int(accounts["lera.berry"]["folder_id"]) == int(valeria["id"])
    assert int(accounts["lidieblush"]["folder_id"]) == int(lidiia["id"])
    assert int(models["parent_id"]) == int(root["id"])
    assert batch_count == 0
    assert url_count == 0
    assert file_count == 0
