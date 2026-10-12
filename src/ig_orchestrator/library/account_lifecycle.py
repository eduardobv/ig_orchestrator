"""Account lifecycle: mark accounts as deleted on Instagram (and restore them).

Builds on ``FsOperationService``: the folder move goes through the same journal
(preview, undo, recovery); this module adds the catalog status change and the
data needed to restore the previous state.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ig_orchestrator.library.fsops import FsOperationService, FsOpsError
from ig_orchestrator.library.fsops_plan import Conflict, OpType, Plan, Step
from ig_orchestrator.library.paths import parent_rel, rel_key

DELETED_FOLDER_SETTING = "library.deleted_folder_rel"
KEEP_GROUP_SETTING = "library.deleted_keep_group"
DEFAULT_DELETED_FOLDER = "09.DELETED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _basename(rel: str) -> str:
    return rel.rsplit("\\", 1)[-1]


def _join(parent: str, name: str) -> str:
    return f"{parent}\\{name}" if parent else name


def _setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return str(row[0]).strip() if row is not None and str(row[0]).strip() else default


@dataclass(slots=True)
class AccountAction:
    account_id: int
    username: str
    src_rel: str | None
    dst_rel: str | None  # None => status-only (no folder on disk / already archived)


@dataclass(slots=True)
class LifecyclePlan:
    plan: Plan
    actions: list[AccountAction] = field(default_factory=list)

    @property
    def can_execute(self) -> bool:
        return bool(self.actions) and not self.plan.blocking


class AccountLifecycleService:
    def __init__(self, connection: sqlite3.Connection, *, fs: FsOperationService | None = None) -> None:
        self.conn = connection
        self.fs = fs or FsOperationService(connection)

    # ------------------------------------------------------------ settings
    @property
    def deleted_folder(self) -> str:
        return _setting(self.conn, DELETED_FOLDER_SETTING, DEFAULT_DELETED_FOLDER).strip("\\/")

    @property
    def keep_group(self) -> bool:
        return _setting(self.conn, KEEP_GROUP_SETTING, "0").lower() in {"1", "true", "yes"}

    def _status_id(self, code: str) -> int:
        return int(self.conn.execute("SELECT id FROM catalog_account_statuses WHERE code = ?", (code,)).fetchone()[0])

    # ----------------------------------------------------------- planning
    def plan_mark_deleted(self, account_ids: list[int], *, suffix_on_conflict: bool = False) -> LifecyclePlan:
        rows = self._accounts(account_ids)
        title = (
            f"Marcar como eliminada: {rows[0]['username']}" if len(rows) == 1
            else f"Marcar {len(rows)} cuentas como eliminadas"
        )
        result = LifecyclePlan(Plan(title))
        plan = result.plan
        deleted_root = self.deleted_folder
        online = self.fs.is_online()
        taken: set[str] = set()
        planned_dirs: set[str] = set()
        busy = set(self.fs._busy_accounts([int(r["id"]) for r in rows]))

        for row in rows:
            username = str(row["username"])
            if str(row["status"]) == "DELETED":
                plan.conflicts.append(Conflict("ALREADY_DELETED", f"@{username} ya esta marcada como eliminada"))
                continue
            if username in busy:
                plan.conflicts.append(Conflict("ACCOUNT_IN_ACTIVE_BATCH", f"@{username} esta en un lote en ejecucion"))
                continue
            self._owner_warning(plan, row)
            if row["is_favorite"]:
                plan.conflicts.append(Conflict("WAS_FAVORITE", f"@{username} era favorita: dejara de serlo", blocking=False))
            src = row["rel_path"]
            if self._in_draft_batch(int(row["id"])):
                plan.conflicts.append(
                    Conflict("IN_DRAFT_BATCH", f"@{username} esta en un lote borrador (no se quita del lote)", blocking=False)
                )
            if not src or (online and not os.path.exists(self.fs.abs(src))):
                plan.conflicts.append(
                    Conflict("NO_FOLDER", f"@{username}: sin carpeta en disco; solo cambia el estado", blocking=False)
                )
                result.actions.append(AccountAction(int(row["id"]), username, src, None))
                plan.affected_accounts += 1
                continue
            if rel_key(parent_rel(src)).startswith(rel_key(deleted_root)):
                plan.conflicts.append(
                    Conflict("ALREADY_IN_DELETED", f"@{username} ya esta en {deleted_root}: solo cambia el estado", blocking=False)
                )
                result.actions.append(AccountAction(int(row["id"]), username, src, None))
                plan.affected_accounts += 1
                continue

            group_part = _basename(parent_rel(src)) if self.keep_group and parent_rel(src) else ""
            dest_parent = _join(deleted_root, group_part) if group_part else deleted_root
            name = _basename(src)
            dst = _join(dest_parent, name)
            if suffix_on_conflict:
                counter = 2
                while self._exists(dst) or rel_key(dst) in taken:
                    dst = _join(dest_parent, f"{name}_{counter}")
                    counter += 1
            elif self._exists(dst) or rel_key(dst) in taken:
                plan.conflicts.append(Conflict("DEST_EXISTS", f"Ya existe {dst}. Usa 'sufijo _2' o resuelvelo antes"))
                continue
            taken.add(rel_key(dst))
            for directory in self._missing_dirs(dest_parent):
                if rel_key(directory) not in planned_dirs:
                    planned_dirs.add(rel_key(directory))
                    plan.steps.append(Step(OpType.MKDIR, None, directory))
            plan.steps.append(Step(OpType.MOVE_DIR, src, dst, int(row["id"])))
            result.actions.append(AccountAction(int(row["id"]), username, src, dst))
            plan.affected_accounts += 1

        if plan.steps and not online:
            plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
        return result

    def _exists(self, rel: str) -> bool:
        return os.path.exists(self.fs.abs(rel)) or self.fs.folder_id_for_rel(rel) is not None or bool(
            self.conn.execute(
                "SELECT 1 FROM catalog_accounts WHERE rel_path IS NOT NULL AND lower(rel_path) = lower(?) LIMIT 1",
                (rel,),
            ).fetchone()
        )

    def _missing_dirs(self, rel: str) -> list[str]:
        """Folders from the library root down to *rel* that do not exist yet (top-down)."""

        missing: list[str] = []
        current = rel
        while current and not os.path.isdir(self.fs.abs(current)):
            missing.append(current)
            current = parent_rel(current)
        return list(reversed(missing))

    def _owner_warning(self, plan: Plan, row: sqlite3.Row) -> None:
        owner = str(row["instagram_user_id"] or "").strip()
        if not owner:
            return
        others = [
            str(r[0])
            for r in self.conn.execute(
                "SELECT username FROM catalog_accounts WHERE instagram_user_id = ? AND id <> ?", (owner, row["id"])
            )
        ]
        if others:
            plan.conflicts.append(
                Conflict(
                    "OWNER_SHARED",
                    f"@{row['username']}: el id {owner} aparece tambien en @{', @'.join(others[:3])}"
                    " (quiza es un renombrado, no una eliminacion)",
                    blocking=False,
                )
            )

    def _in_draft_batch(self, account_id: int) -> bool:
        return bool(
            self.conn.execute(
                """
                SELECT 1 FROM batch_accounts ba JOIN batches b ON b.id = ba.batch_id
                JOIN batch_statuses bs ON bs.id = b.status_id
                WHERE ba.catalog_account_id = ? AND bs.code = 'DRAFT' LIMIT 1
                """,
                (account_id,),
            ).fetchone()
        )

    def _accounts(self, account_ids: list[int]) -> list[sqlite3.Row]:
        marks = ",".join("?" for _ in account_ids)
        return self.conn.execute(
            f"""
            SELECT a.id, a.username, a.rel_path, a.is_favorite, a.instagram_user_id,
                   a.status_id, s.code AS status
            FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id
            WHERE a.id IN ({marks}) ORDER BY a.username COLLATE NOCASE
            """,
            account_ids,
        ).fetchall()

    # ----------------------------------------------------------- execution
    def execute_mark_deleted(self, lifecycle: LifecyclePlan) -> str | None:
        if not lifecycle.can_execute:
            raise FsOpsError("; ".join(c.message for c in lifecycle.plan.blocking) or "Nada que hacer")
        group = self.fs.execute(lifecycle.plan) if lifecycle.plan.steps else None
        deleted_id = self._status_id("DELETED")
        now = _now()
        try:
            for action in lifecycle.actions:
                row = self.conn.execute(
                    "SELECT status_id, is_favorite, rel_path FROM catalog_accounts WHERE id = ?",
                    (action.account_id,),
                ).fetchone()
                moved = action.dst_rel is not None
                self.conn.execute(
                    "INSERT INTO account_lifecycle (op_group, account_id, kind, prev_status_id, prev_favorite,"
                    " prev_rel_path, created_at) VALUES (?, ?, 'DELETE', ?, ?, ?, ?)",
                    (group if moved else None, action.account_id, row["status_id"], row["is_favorite"],
                     action.src_rel if moved else None, now),
                )
                self.conn.execute(
                    "UPDATE catalog_accounts SET status_id = ?, is_favorite = 0, deleted_at = ?,"
                    " previous_rel_path = ?, updated_at = ? WHERE id = ?",
                    (deleted_id, now, action.src_rel if moved else None, now, action.account_id),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return group

    # --------------------------------------------------------------- undo
    def restore_after_undo(self, op_group: str) -> int:
        """After ``FsOperationService.undo``: put status/favorite back for that group."""

        count = 0
        for row in self.conn.execute(
            "SELECT id, account_id, prev_status_id, prev_favorite FROM account_lifecycle"
            " WHERE op_group = ? AND undone = 0 AND kind = 'DELETE'",
            (op_group,),
        ).fetchall():
            self.conn.execute(
                "UPDATE catalog_accounts SET status_id = ?, is_favorite = ?, deleted_at = NULL,"
                " previous_rel_path = NULL, updated_at = ? WHERE id = ?",
                (row["prev_status_id"], row["prev_favorite"], _now(), row["account_id"]),
            )
            self.conn.execute("UPDATE account_lifecycle SET undone = 1 WHERE id = ?", (row["id"],))
            count += 1
        self.conn.commit()
        return count

    # ------------------------------------------------------------ restore
    def plan_restore(self, account_id: int) -> LifecyclePlan:
        row = self.conn.execute(
            "SELECT a.id, a.username, a.rel_path, a.previous_rel_path, s.code AS status"
            " FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id WHERE a.id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise FsOpsError(f"Cuenta no encontrada: {account_id}")
        plan = Plan(f"Restaurar cuenta: {row['username']}")
        result = LifecyclePlan(plan)
        if row["status"] != "DELETED":
            plan.conflicts.append(Conflict("NOT_DELETED", "La cuenta no esta marcada como eliminada"))
            return result
        previous = row["previous_rel_path"]
        if previous and row["rel_path"]:
            if not self.fs.is_online():
                plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
            elif not os.path.exists(self.fs.abs(row["rel_path"])):
                plan.conflicts.append(Conflict("SRC_MISSING", f"No existe en disco: {row['rel_path']}"))
            elif self._exists(previous):
                plan.conflicts.append(Conflict("DEST_EXISTS", f"Ya existe {previous}"))
            else:
                for directory in self._missing_dirs(parent_rel(previous)):
                    plan.steps.append(Step(OpType.MKDIR, None, directory))
                plan.steps.append(Step(OpType.MOVE_DIR, row["rel_path"], previous, account_id))
                plan.affected_accounts = 1
        else:
            plan.conflicts.append(
                Conflict("STATUS_ONLY", "No se conoce la carpeta anterior: solo cambia el estado", blocking=False)
            )
        result.actions.append(AccountAction(account_id, str(row["username"]), row["rel_path"], previous))
        return result

    def execute_restore(self, lifecycle: LifecyclePlan) -> str | None:
        if not lifecycle.can_execute:
            raise FsOpsError("; ".join(c.message for c in lifecycle.plan.blocking) or "Nada que hacer")
        action = lifecycle.actions[0]
        group = self.fs.execute(lifecycle.plan) if lifecycle.plan.steps else None
        prev = self.conn.execute(
            "SELECT prev_status_id FROM account_lifecycle WHERE account_id = ? AND kind IN ('DELETE', 'LABEL')"
            " ORDER BY id DESC LIMIT 1",
            (action.account_id,),
        ).fetchone()
        status_id = int(prev["prev_status_id"]) if prev and prev["prev_status_id"] else self._status_id("ENABLED")
        now = _now()
        self.conn.execute(
            "UPDATE catalog_accounts SET status_id = ?, deleted_at = NULL, previous_rel_path = NULL,"
            " updated_at = ? WHERE id = ?",
            (status_id, now, action.account_id),
        )
        self.conn.execute(
            "INSERT INTO account_lifecycle (op_group, account_id, kind, created_at) VALUES (?, ?, 'RESTORE', ?)",
            (group, action.account_id, now),
        )
        self.conn.commit()
        return group

    # ---------------------------------------------- label existing 09.DELETED
    def find_unlabeled_deleted(self) -> list[sqlite3.Row]:
        """Accounts already inside the deleted folder whose status is not DELETED."""

        prefix = rel_key(self.deleted_folder)
        return [
            r
            for r in self.conn.execute(
                "SELECT a.id, a.username, a.rel_path, s.code AS status FROM catalog_accounts a"
                " JOIN catalog_account_statuses s ON s.id = a.status_id"
                " WHERE a.rel_path IS NOT NULL AND s.code <> 'DELETED' ORDER BY a.username COLLATE NOCASE"
            )
            if rel_key(str(r["rel_path"])).startswith(prefix + "\\")
        ]

    def label_deleted(self, account_ids: list[int]) -> int:
        deleted_id = self._status_id("DELETED")
        now = _now()
        for row in self._accounts(account_ids):
            if row["status"] == "DELETED":
                continue
            self.conn.execute(
                "INSERT INTO account_lifecycle (op_group, account_id, kind, prev_status_id, prev_favorite,"
                " created_at) VALUES (NULL, ?, 'LABEL', ?, ?, ?)",
                (row["id"], row["status_id"], row["is_favorite"], now),
            )
            self.conn.execute(
                "UPDATE catalog_accounts SET status_id = ?, is_favorite = 0, deleted_at = ?, updated_at = ?"
                " WHERE id = ?",
                (deleted_id, now, now, row["id"]),
            )
        self.conn.commit()
        return len(account_ids)

    # ------------------------------------------------------- suggestions
    def suggest_deleted(self, *, min_batches: int = 2) -> list[tuple[int, str, int]]:
        """Accounts whose real failures are 'not found' in >= ``min_batches`` batches.

        Only a hint: failures caused by 'Executed on another instance' are ignored and an
        account with a later COMPLETED URL is excluded. Returns ``(account_id, username, batches)``.
        """

        rows = self.conn.execute(
            """
            SELECT a.id, a.username,
                   COUNT(DISTINCT ba.batch_id) AS batches,
                   MAX(bu.updated_at) AS last_fail
            FROM batch_urls bu
            JOIN batch_accounts ba ON ba.id = bu.batch_account_id
            JOIN catalog_accounts a ON a.id = ba.catalog_account_id
            JOIN catalog_account_statuses s ON s.id = a.status_id
            JOIN bot_errors be ON be.id = bu.last_error_id
            WHERE be.code IN ('STORIES_NOT_FOUND', 'NOT_FOUND')
              AND COALESCE(bu.last_error_text, '') NOT LIKE '%another instance%'
              AND s.code NOT IN ('DELETED', 'DISABLED')
            GROUP BY a.id HAVING COUNT(DISTINCT ba.batch_id) >= ?
            """,
            (min_batches,),
        ).fetchall()
        suggestions = []
        for row in rows:
            later_ok = self.conn.execute(
                """
                SELECT 1 FROM batch_urls bu JOIN batch_accounts ba ON ba.id = bu.batch_account_id
                JOIN batch_url_statuses bs ON bs.id = bu.status_id
                WHERE ba.catalog_account_id = ? AND bs.code = 'COMPLETED' AND bu.updated_at > ? LIMIT 1
                """,
                (row["id"], row["last_fail"]),
            ).fetchone()
            if not later_ok:
                suggestions.append((int(row["id"]), str(row["username"]), int(row["batches"])))
        return sorted(suggestions, key=lambda item: (-item[2], item[1].casefold()))
