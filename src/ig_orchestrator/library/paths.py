"""Library path helpers: absolute <-> relative to the LIBRARY root (Windows-style)."""

from __future__ import annotations

from pathlib import PureWindowsPath


def _parts(path: str) -> tuple[str, ...]:
    return tuple(p for p in PureWindowsPath(path.strip()).parts)


def to_rel(path: str, root: str) -> str | None:
    """Path relative to *root* (``a\\b``), ``''`` for the root itself, ``None`` if outside."""

    path_parts = _parts(path)
    root_parts = _parts(root)
    if len(path_parts) < len(root_parts):
        return None
    if [p.casefold() for p in path_parts[: len(root_parts)]] != [p.casefold() for p in root_parts]:
        return None
    return "\\".join(path_parts[len(root_parts):])


def to_abs(rel: str, root: str) -> str:
    """Absolute path for *rel* under *root*."""

    root = root.rstrip("\\/")
    return f"{root}\\{rel}" if rel else root


def rel_key(rel: str) -> str:
    """Comparison key (case-insensitive, normalized separators)."""

    return "\\".join(p.casefold() for p in rel.replace("/", "\\").split("\\") if p)


def parent_rel(rel: str) -> str:
    parts = [p for p in rel.replace("/", "\\").split("\\") if p]
    return "\\".join(parts[:-1])
