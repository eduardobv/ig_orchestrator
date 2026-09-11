from __future__ import annotations

from dataclasses import dataclass, field

from ig_orchestrator.db.catalog_importer import split_destination_path
from ig_orchestrator.gui.account_catalog_service import AccountCatalogEntry


UNROUTED_PATH = ""


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
) -> list[CatalogTreeNode]:
    """Group catalog entries into a folder tree; usernames are leaves."""

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


__all__ = ["CatalogTreeNode", "UNROUTED_PATH", "build_catalog_tree"]
