from __future__ import annotations

import re
from dataclasses import dataclass, field

from ig_orchestrator.db.catalog_importer import split_destination_path
from ig_orchestrator.gui.account_catalog_service import AccountCatalogEntry


UNROUTED_PATH = ""

_DELETED_SUFFIX = re.compile(r"-delete[d]?$", re.IGNORECASE)
_INACTIVE_SUFFIX = re.compile(r"-inactiv(?:e|a|o)$", re.IGNORECASE)


def folder_suffix_kind(name: str) -> str | None:
    """``'deleted'`` / ``'inactive'`` when the folder *name* ends in ``-Deleted`` / ``-Inactive``."""

    if _DELETED_SUFFIX.search(name):
        return "deleted"
    if _INACTIVE_SUFFIX.search(name):
        return "inactive"
    return None


def path_is_hidden(path: str, *, hide_deleted: bool, hide_inactive: bool) -> bool:
    """True when any folder of *path* has a hidden ``-Deleted`` / ``-Inactive`` suffix."""

    for name in split_destination_path(path):
        kind = folder_suffix_kind(name)
        if (kind == "deleted" and hide_deleted) or (kind == "inactive" and hide_inactive):
            return True
    return False


@dataclass
class CatalogTreeNode:
    name: str
    path: str
    username: str | None = None
    entry: AccountCatalogEntry | None = None
    children: list[CatalogTreeNode] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.username is not None


def build_catalog_tree(
    entries: list[AccountCatalogEntry],
    *,
    unrouted_label: str = "Sin ruta",
    extra_folder_paths: list[str] | None = None,
    hide_deleted: bool = False,
    hide_inactive: bool = False,
) -> list[CatalogTreeNode]:
    """Group catalog entries into a folder tree; usernames are leaves.

    ``extra_folder_paths`` adds folders that hold no account yet (e.g. just created).
    ``hide_deleted`` / ``hide_inactive`` drop folders suffixed ``-Deleted`` / ``-Inactive`` (and what they
    hold) from the tree only; the data and the folder pickers are untouched.
    """

    def hidden(path: str) -> bool:
        return (hide_deleted or hide_inactive) and path_is_hidden(
            path, hide_deleted=hide_deleted, hide_inactive=hide_inactive
        )

    folders: dict[str, CatalogTreeNode] = {}
    roots: list[CatalogTreeNode] = []
    unrouted = CatalogTreeNode(name=unrouted_label, path=UNROUTED_PATH)

    def folder_node(path: str, name: str, parent: CatalogTreeNode | None) -> CatalogTreeNode:
        existing = folders.get(path)
        if existing is not None:
            return existing
        node = CatalogTreeNode(name=name, path=path)
        folders[path] = node
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
        return node

    for entry in entries:
        if hidden(entry.destination_path):
            continue
        segments = split_destination_path(entry.destination_path)
        if not segments:
            unrouted.children.append(
                CatalogTreeNode(
                    name=entry.username,
                    path=UNROUTED_PATH,
                    username=entry.username,
                    entry=entry,
                )
            )
            continue
        parent: CatalogTreeNode | None = None
        current_path = ""
        for index, name in enumerate(segments):
            current_path = name if index == 0 else _join_windows(current_path, name)
            parent = folder_node(current_path, name, parent)
        assert parent is not None
        parent.children.append(
            CatalogTreeNode(
                name=entry.username,
                path=parent.path,
                username=entry.username,
                entry=entry,
            )
        )

    for extra in extra_folder_paths or []:
        if hidden(extra):
            continue
        parent = None
        current_path = ""
        for index, name in enumerate(split_destination_path(extra)):
            current_path = name if index == 0 else _join_windows(current_path, name)
            parent = folder_node(current_path, name, parent)

    if unrouted.children:
        unrouted.children.sort(key=lambda node: node.name.casefold())
        roots.append(unrouted)
    _sort_nodes(roots)
    return roots


def _join_windows(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    return f"{parent_path}\\{name}"


def _sort_nodes(nodes: list[CatalogTreeNode]) -> None:
    nodes.sort(key=lambda node: (node.is_leaf, node.name.casefold()))
    for node in nodes:
        _sort_nodes(node.children)


__all__ = [
    "CatalogTreeNode",
    "UNROUTED_PATH",
    "build_catalog_tree",
    "folder_suffix_kind",
    "path_is_hidden",
]
