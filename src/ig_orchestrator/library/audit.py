"""Read-only audit of discrepancies between bdapp, sc1 databases and disk.

Nothing here writes to any database or to disk: sc1 databases are opened with
``mode=ro`` and the disk is only touched with ``os.path.exists``.
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from ig_orchestrator.library.audit_report import AuditReport, Finding, Severity

DELETED_CATEGORY_PREFIX = "09.DELETED"
UNKNOWN_OWNERS = frozenset({"", "unknown", "none", "null"})

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class _Row:
    username: str
    owner_id: str
    path: str
    last_modified: str = ""
    modified_at: str = ""
    status: str = ""


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _owner(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return "" if text.casefold() in UNKNOWN_OWNERS else text


def _connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _load_sc1(path: Path, tables: tuple[str, ...]) -> list[_Row]:
    connection = _connect_ro(path)
    try:
        existing = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        table = next((name for name in tables if name in existing), None)
        if table is None:
            raise ValueError(f"{path}: none of the tables {tables} found")
        rows = connection.execute(
            f"SELECT username, ownerId, path, last_modified, modified_at FROM {table}"
        ).fetchall()
    finally:
        connection.close()
    return [
        _Row(
            username=str(row["username"] or ""),
            owner_id=_owner(row["ownerId"]),
            path=str(row["path"] or ""),
            last_modified=str(row["last_modified"] or ""),
            modified_at=str(row["modified_at"] or ""),
        )
        for row in rows
    ]


def _load_app(connection: sqlite3.Connection) -> list[_Row]:
    rows = connection.execute(
        """
        SELECT a.username, a.instagram_user_id, f.full_path, s.code
        FROM catalog_accounts a
        LEFT JOIN catalog_folders f ON f.id = a.folder_id
        LEFT JOIN catalog_account_statuses s ON s.id = a.status_id
        """
    ).fetchall()
    return [
        _Row(
            username=str(row[0] or ""),
            owner_id=_owner(row[1]),
            path=str(row[2] or ""),
            status=str(row[3] or ""),
        )
        for row in rows
    ]


def classify_owner_group(paths: list[str]) -> str:
    """Hint (not a decision) for a group of folders sharing one ownerId."""

    categories = [PureWindowsPath(p).parent.name for p in paths]
    deleted = [c.upper().startswith(DELETED_CATEGORY_PREFIX) for c in categories]
    if all(deleted):
        return "ALL_DELETED"
    if any(deleted):
        return "DELETED_PAIR"
    if len({c.casefold() for c in categories}) == 1:
        return "SAME_CATEGORY"
    return "CROSS_CATEGORY"


def _common_root(rows: list[_Row]) -> str | None:
    parents = [os.path.dirname(row.path) for row in rows if row.path]
    if not parents:
        return None
    try:
        return os.path.commonpath(parents)
    except ValueError:
        return None


def run_audit(
    app_conn: sqlite3.Connection | None,
    lite_path: Path | None,
    complete_path: Path | None = None,
    *,
    check_disk: bool = True,
    progress: ProgressCallback | None = None,
) -> AuditReport:
    report = AuditReport()
    lite = _load_sc1(lite_path, ("accounts_dir",)) if lite_path else []
    complete: list[_Row] = []
    if complete_path is not None:
        if complete_path.exists():
            complete = _load_sc1(complete_path, ("accounts", "accounts_dir"))
        else:
            report.notes.append(
                f"accounts_complete no encontrado ({complete_path}): se omite COMPLETE_STALE."
            )
    app = _load_app(app_conn) if app_conn is not None else []

    _check_disk(report, app, lite, check_disk, progress)
    _check_lite(report, lite)
    if app_conn is not None and lite_path:
        _check_app_vs_lite(report, app, lite)
    if complete:
        _check_complete(report, lite, complete)
    if app_conn is not None:
        _check_index(report, app_conn)
    return report


def _check_index(report: AuditReport, conn: sqlite3.Connection) -> None:
    """``INDEX_MISSING``: the account has files (per its counters) but no index rows.
    ``INDEX_STALE``: a counter differs from the number of indexed files of that sub-folder."""

    try:
        rows = conn.execute(
            """
            SELECT a.id, a.username, a.instagram_user_id, a.rel_path, a.posts_count, a.reels_count, a.story_count,
                   a.highlights_count FROM catalog_accounts a WHERE a.rel_path IS NOT NULL AND a.disk_state = 'PRESENT'
            """
        ).fetchall()
        counts = {
            (int(r[0]), int(r[1])): int(r[2])
            for r in conn.execute("SELECT account_id, kind, COUNT(*) FROM media_index GROUP BY account_id, kind")
        }
    except sqlite3.OperationalError:
        return
    labels = ("posts", "reels", "stories", "highlights")
    for row in rows:
        counters = [int(row[i] or 0) for i in (4, 5, 6, 7)]
        if not any(counters):
            continue
        indexed = [counts.get((int(row["id"]), kind), 0) for kind in range(4)]
        owner = _owner(row["instagram_user_id"])
        if not any(indexed):
            report.findings.append(Finding(
                "INDEX_MISSING", Severity.WARNING, str(row["username"]), owner, (str(row["rel_path"]),),
                f"{sum(counters)} ficheros en disco segun los contadores y ninguno en el indice",
            ))
            continue
        diffs = [f"{labels[k]} {counters[k]} vs indice {indexed[k]}" for k in range(4) if counters[k] != indexed[k]]
        if diffs:
            report.findings.append(Finding(
                "INDEX_STALE", Severity.INFO, str(row["username"]), owner, (str(row["rel_path"]),), "; ".join(diffs),
            ))


def _check_disk(
    report: AuditReport,
    app: list[_Row],
    lite: list[_Row],
    check_disk: bool,
    progress: ProgressCallback | None,
) -> None:
    if not check_disk:
        report.notes.append("Comprobación de disco desactivada.")
        return
    root = _common_root(lite) or _common_root(app)
    if root is not None and not os.path.isdir(root):
        report.findings.append(
            Finding(
                "DISK_OFFLINE",
                Severity.WARNING,
                paths=(root,),
                detail="Unidad/ruta raíz no disponible: se omiten las comprobaciones de disco.",
            )
        )
        report.notes.append("Disco no disponible: solo se compararon las bases de datos.")
        return
    report.disk_checked = True
    seen: set[str] = set()
    targets = [(r, "lite") for r in lite] + [(r, "bdapp") for r in app if r.path]
    for index, (row, source) in enumerate(targets, start=1):
        key = _norm(row.path) if row.path else ""
        if key and key not in seen:
            seen.add(key)
            if not os.path.exists(row.path):
                report.findings.append(
                    Finding(
                        "PATH_MISSING",
                        Severity.ERROR,
                        row.username,
                        row.owner_id,
                        (row.path,),
                        f"origen: {source}",
                    )
                )
        if progress is not None and index % 100 == 0:
            progress(index, len(targets))
    if progress is not None:
        progress(len(targets), len(targets))


def _check_lite(report: AuditReport, lite: list[_Row]) -> None:
    by_owner: dict[str, list[_Row]] = defaultdict(list)
    by_user: dict[str, list[_Row]] = defaultdict(list)
    for row in lite:
        if row.owner_id:
            by_owner[row.owner_id].append(row)
        by_user[row.username.casefold()].append(row)
        folder = os.path.basename(os.path.normpath(row.path)) if row.path else ""
        if folder and folder != row.username and folder.casefold() == row.username.casefold():
            report.findings.append(
                Finding(
                    "NAME_CASE",
                    Severity.WARNING,
                    row.username,
                    row.owner_id,
                    (row.path,),
                    "la carpeta difiere del username solo en mayúsculas/minúsculas",
                )
            )

    for owner_id, rows in sorted(by_owner.items()):
        if len({_norm(r.path) for r in rows}) < 2:
            continue
        report.findings.append(
            Finding(
                "OWNER_DUP",
                Severity.WARNING,
                ", ".join(sorted(r.username for r in rows)),
                owner_id,
                tuple(r.path for r in rows),
                classify_owner_group([r.path for r in rows]),
            )
        )
    for rows in by_user.values():
        if len({_norm(r.path) for r in rows}) > 1:
            report.findings.append(
                Finding(
                    "USERNAME_DUP",
                    Severity.WARNING,
                    rows[0].username,
                    rows[0].owner_id,
                    tuple(r.path for r in rows),
                    "mismo username en varias rutas",
                )
            )

    stamps = [v for r in lite for v in (r.last_modified, r.modified_at) if v]
    iso = sum(1 for v in stamps if "T" in v)
    spaced = len(stamps) - iso
    if iso and spaced:
        report.findings.append(
            Finding(
                "LAST_MODIFIED_MIXED",
                Severity.INFO,
                detail=(
                    f"{iso} fechas con formato ISO 'T' y {spaced} con "
                    "'YYYY-MM-DD HH:MM:SS' (last_modified/modified_at)"
                ),
            )
        )


def _check_app_vs_lite(report: AuditReport, app: list[_Row], lite: list[_Row]) -> None:
    lite_by_user: dict[str, list[_Row]] = defaultdict(list)
    for row in lite:
        lite_by_user[row.username.casefold()].append(row)
    app_users = {row.username.casefold() for row in app}

    for row in app:
        matches = lite_by_user.get(row.username.casefold())
        if not matches:
            report.findings.append(
                Finding(
                    "ONLY_IN_APP",
                    Severity.WARNING,
                    row.username,
                    row.owner_id,
                    (row.path,) if row.path else (),
                    f"estado {row.status}",
                )
            )
            continue
        owners = {m.owner_id for m in matches if m.owner_id}
        if row.owner_id and owners and row.owner_id not in owners:
            report.findings.append(
                Finding(
                    "OWNER_MISMATCH",
                    Severity.ERROR,
                    row.username,
                    row.owner_id,
                    tuple(m.path for m in matches),
                    f"bdapp={row.owner_id} lite={','.join(sorted(owners))}",
                )
            )
        # The catalog folder is the person's folder; sc1 stores one row per
        # account folder inside it (``<folder>/<username>``), so either matches.
        accepted = {_norm(m.path) for m in matches} | {
            _norm(os.path.dirname(m.path)) for m in matches
        }
        if row.path and _norm(row.path) not in accepted:
            report.findings.append(
                Finding(
                    "FOLDER_MISMATCH",
                    Severity.ERROR,
                    row.username,
                    row.owner_id,
                    (row.path, *(m.path for m in matches)),
                    "bdapp ≠ lite",
                )
            )
    for row in lite:
        if row.username.casefold() not in app_users:
            report.findings.append(
                Finding(
                    "ONLY_IN_LITE",
                    Severity.INFO,
                    row.username,
                    row.owner_id,
                    (row.path,),
                    "cuenta no gestionada por la app",
                )
            )


def _check_complete(report: AuditReport, lite: list[_Row], complete: list[_Row]) -> None:
    lite_by_path = {_norm(r.path): r for r in lite}
    complete_by_path = {_norm(r.path): r for r in complete}
    for key, row in lite_by_path.items():
        other = complete_by_path.get(key)
        if other is None:
            detail = "ruta en lite ausente en complete"
        elif other.username.casefold() != row.username.casefold() or (
            row.owner_id and other.owner_id and row.owner_id != other.owner_id
        ):
            detail = f"complete tiene username={other.username} owner={other.owner_id}"
        else:
            continue
        report.findings.append(
            Finding("COMPLETE_STALE", Severity.WARNING, row.username, row.owner_id, (row.path,), detail)
        )
    for key, row in complete_by_path.items():
        if key not in lite_by_path:
            report.findings.append(
                Finding(
                    "COMPLETE_STALE",
                    Severity.WARNING,
                    row.username,
                    row.owner_id,
                    (row.path,),
                    "ruta en complete ausente en lite",
                )
            )
