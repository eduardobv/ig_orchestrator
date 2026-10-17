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


def _suffix_entries() -> list[AccountCatalogEntry]:
    base = r"G:\4K Stogram\00.MODELS-A"
    return [
        AccountCatalogEntry(username="alive", destination_path=rf"{base}\Ana"),
        AccountCatalogEntry(username="gone", destination_path=rf"{base}\Ana-Deleted"),
        AccountCatalogEntry(username="sleeping", destination_path=rf"{base}\Ana-Inactive"),
    ]


def _leaf_names(nodes) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        if node.is_leaf:
            found.add(node.username)
        found |= _leaf_names(node.children)
    return found


def test_build_catalog_tree_shows_everything_by_default() -> None:
    roots = build_catalog_tree(_suffix_entries())
    assert _leaf_names(roots) == {"alive", "gone", "sleeping"}


def test_build_catalog_tree_hides_deleted_and_inactive_folders_independently() -> None:
    assert _leaf_names(build_catalog_tree(_suffix_entries(), hide_deleted=True)) == {"alive", "sleeping"}
    assert _leaf_names(build_catalog_tree(_suffix_entries(), hide_inactive=True)) == {"alive", "gone"}
    both = build_catalog_tree(_suffix_entries(), hide_deleted=True, hide_inactive=True)
    assert _leaf_names(both) == {"alive"}


def test_build_catalog_tree_hides_empty_suffixed_folders() -> None:
    extra = [r"G:\4K Stogram\00.MODELS-A\Bea-Deleted", r"G:\4K Stogram\00.MODELS-A\Bea"]
    roots = build_catalog_tree([], extra_folder_paths=extra, hide_deleted=True)
    group = roots[0].children[0]
    assert [c.name for c in group.children] == ["Bea"]


def test_open_catalog_folders_lists_only_expanded_folder_nodes() -> None:
    import tkinter as tk
    from tkinter import ttk

    from ig_orchestrator.gui.catalog.panel import CatalogPanelMixin

    try:
        root = tk.Tk()
    except tk.TclError:
        return
    try:
        tree = ttk.Treeview(root)
        tree.insert("", tk.END, iid="folder:A", text="A", open=True)
        tree.insert("folder:A", tk.END, iid="folder:A\B", text="B", open=False)
        tree.insert("folder:A", tk.END, iid="folder:A\C", text="C", open=True)
        tree.insert("folder:A\C", tk.END, iid="user:x", text="x", open=True)
        assert sorted(CatalogPanelMixin._open_catalog_folders(tree)) == ["folder:A", "folder:A\C"]
    finally:
        root.destroy()
