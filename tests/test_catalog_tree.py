from ig_orchestrator.gui.account_catalog_service import AccountCatalogEntry
from ig_orchestrator.gui.catalog_tree import build_catalog_tree
from ig_orchestrator.gui.treeview_sort import _sort_key


def test_build_catalog_tree_groups_drive_folder_and_leaf() -> None:
    entries = [
        AccountCatalogEntry(
            username="lidieblush",
            destination_path=r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova",
        ),
        AccountCatalogEntry(
            username="lerabuns",
            destination_path=r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva",
        ),
        AccountCatalogEntry(username="nopath"),
    ]
    roots = build_catalog_tree(entries, unrouted_label="Sin ruta")
    assert roots[0].name == r"G:\4K Stogram"
    folder_names = {child.name for child in roots[0].children}
    assert folder_names == {"00.FAVORITES", "00.MODELS-A"}
    models = next(child for child in roots[0].children if child.name == "00.MODELS-A")
    account_folder = models.children[0]
    assert account_folder.name == "Lidiia-Filippova"
    assert account_folder.children[0].username == "lidieblush"
    assert account_folder.children[0].is_leaf
    unrouted = roots[-1]
    assert unrouted.name == "Sin ruta"
    assert unrouted.children[0].username == "nopath"


def test_sort_key_orders_numbers_before_text() -> None:
    assert _sort_key("10") < _sort_key("2") or _sort_key("2") < _sort_key("10")
    assert _sort_key("2") < _sort_key("10")
