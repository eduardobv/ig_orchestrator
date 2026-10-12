"""Single entry point for every change to library folders (disk + bdapp together).

Contract of an action: ``plan_*`` (no effects) -> preview -> ``execute(plan)``.
Each step is journaled in ``fs_operations`` (PLANNED -> DISK_DONE -> COMMITTED) so
an interrupted run can be completed or reverted by ``recover()`` and any group of
operations can be reverted with ``undo()``. Never overwrites; never leaves LIBRARY.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ig_orchestrator.library.fsops_plan import (
    Conflict,
    OpStatus,
    OpType,
    Plan,
    Step,
    validate_name,
)
from ig_orchestrator.library.paths import parent_rel, rel_key, to_abs, to_rel

_LOCK = threading.Lock()  # one disk operation at a time inside the app


class FsOpsError(RuntimeError):
    """The operation cannot run (plan blocked, library offline, busy...)."""


@dataclass(frozen=True, slots=True)
class FolderInfo:
    id: int
    name: str
    rel_path: str
    parent_id: int | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _basename(rel: str) -> str:
    return rel.rsplit("\\", 1)[-1]


def _join(parent: str, name: str) -> str:
    return f"{parent}\\{name}" if parent else name


def _under(rel: str, prefix: str) -> bool:
    key, base = rel_key(rel), rel_key(prefix)
    return key == base or key.startswith(base + "\\")


class FsOperationService:
    def __init__(self, connection: sqlite3.Connection, *, root: str | None = None) -> None:
        self.conn = connection
        self._root = root

    # ------------------------------------------------------------------ roots
    @property
    def root(self) -> str:
        if self._root:
            return self._root
        row = self.conn.execute("SELECT path FROM path_roots WHERE code = 'LIBRARY'").fetchone()
        if row is None or not str(row[0]).strip():
            raise FsOpsError("No hay raiz de biblioteca configurada (path_roots.LIBRARY)")
        return str(row[0]).strip().rstrip("\\/")

    def is_online(self) -> bool:
        try:
            return os.path.isdir(self.root)
        except FsOpsError:
            return False

    def abs(self, rel: str) -> str:
        return to_abs(rel, self.root)

    # ---------------------------------------------------------------- lookups
    def folder(self, folder_id: int) -> FolderInfo:
        row = self.conn.execute(
            "SELECT id, name, full_path, rel_path, parent_id FROM catalog_folders WHERE id = ?",
            (folder_id,),
        ).fetchone()
        if row is None:
            raise FsOpsError(f"Carpeta no encontrada: {folder_id}")
        rel = row["rel_path"]
        if rel is None:
            rel = to_rel(str(row["full_path"]), self.root)
        if rel is None:
            raise FsOpsError(f"La carpeta esta fuera de la biblioteca: {row['full_path']}")
        return FolderInfo(int(row["id"]), str(row["name"]), str(rel), row["parent_id"])

    def folder_id_for_rel(self, rel: str) -> int | None:
        key = rel_key(rel)
        for row in self.conn.execute("SELECT id, rel_path, full_path FROM catalog_folders"):
            value = row["rel_path"] if row["rel_path"] is not None else to_rel(str(row["full_path"]), self.root)
            if value is not None and rel_key(value) == key:
                return int(row["id"])
        return None

    def _accounts_under(self, rel: str) -> list[sqlite3.Row]:
        return [
            r
            for r in self.conn.execute(
                "SELECT id, username, rel_path FROM catalog_accounts WHERE rel_path IS NOT NULL"
            )
            if _under(str(r["rel_path"]), rel)
        ]

    def _folders_under(self, rel: str) -> list[sqlite3.Row]:
        return [
            r
            for r in self.conn.execute("SELECT id, rel_path FROM catalog_folders WHERE rel_path IS NOT NULL")
            if _under(str(r["rel_path"]), rel)
        ]

    def _busy_accounts(self, account_ids: list[int]) -> list[str]:
        if not account_ids:
            return []
        marks = ",".join("?" for _ in account_ids)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT a.username FROM batch_accounts ba
            JOIN batches b ON b.id = ba.batch_id
            JOIN batch_statuses bs ON bs.id = b.status_id
            JOIN catalog_accounts a ON a.id = ba.catalog_account_id
            WHERE bs.code = 'PROCESSING' AND ba.catalog_account_id IN ({marks})
            """,
            account_ids,
        ).fetchall()
        return [str(r[0]) for r in rows]

    # ------------------------------------------------------------- validation
    def _check_common(self, plan: Plan, src: str | None, dst: str | None) -> None:
        if not self.is_online():
            plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
            return
        for rel in (src, dst):
            if rel is None:
                continue
            absolute = os.path.abspath(self.abs(rel))
            root = os.path.abspath(self.root)
            if os.path.normcase(os.path.commonpath([absolute, root])) != os.path.normcase(root):
                plan.conflicts.append(Conflict("OUTSIDE_ROOT", f"Fuera de la biblioteca: {rel}"))
        if src is not None and not os.path.exists(self.abs(src)):
            plan.conflicts.append(Conflict("SRC_MISSING", f"No existe en disco: {src}"))
        if dst is not None and src is not None and rel_key(dst) != rel_key(src):
            if os.path.exists(self.abs(dst)):
                plan.conflicts.append(Conflict("DEST_EXISTS", f"Ya existe en disco: {dst}"))
        if dst is not None:
            if self.conn.execute(
                "SELECT 1 FROM catalog_accounts WHERE rel_path IS NOT NULL AND lower(rel_path) = lower(?)"
                " LIMIT 1",
                (dst,),
            ).fetchone() and (src is None or rel_key(dst) != rel_key(src)):
                plan.conflicts.append(Conflict("DEST_IN_CATALOG", f"Ya hay una cuenta en el catalogo con esa ruta: {dst}"))

    def _check_busy(self, plan: Plan, rel: str) -> None:
        accounts = self._accounts_under(rel)
        plan.affected_accounts = len(accounts)
        plan.affected_folders = len(self._folders_under(rel))
        busy = self._busy_accounts([int(a["id"]) for a in accounts])
        if busy:
            plan.conflicts.append(
                Conflict("ACCOUNT_IN_ACTIVE_BATCH", "Cuentas en un lote en ejecucion: " + ", ".join(busy[:5]))
            )

    # ------------------------------------------------------------------ plans
    def plan_mkdir(self, parent_folder_id: int, name: str) -> Plan:
        parent = self.folder(parent_folder_id)
        dst = _join(parent.rel_path, name)
        plan = Plan(f"Nueva carpeta '{name}' en '{parent.rel_path or 'raiz'}'")
        problem = validate_name(name)
        if problem:
            plan.conflicts.append(Conflict("INVALID_NAME", problem))
            return plan
        if not self.is_online():
            plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
            return plan
        if os.path.exists(self.abs(dst)):
            plan.conflicts.append(Conflict("DEST_EXISTS", f"Ya existe en disco: {dst}"))
        if self.folder_id_for_rel(dst) is not None:
            plan.conflicts.append(Conflict("DEST_IN_CATALOG", f"Ya existe en el catalogo: {dst}"))
        plan.steps.append(Step(OpType.MKDIR, None, dst))
        return plan

    def plan_rename_folder(self, folder_id: int, new_name: str) -> Plan:
        folder = self.folder(folder_id)
        plan = Plan(f"Renombrar carpeta '{folder.name}' -> '{new_name}'")
        if folder.parent_id is None or folder.rel_path == "":
            plan.conflicts.append(Conflict("IS_ROOT", "No se puede renombrar la raiz de la biblioteca"))
            return plan
        problem = validate_name(new_name)
        if problem:
            plan.conflicts.append(Conflict("INVALID_NAME", problem))
            return plan
        dst = _join(parent_rel(folder.rel_path), new_name)
        if new_name == _basename(folder.rel_path):
            plan.conflicts.append(Conflict("NO_CHANGE", "El nombre es el mismo"))
            return plan
        self._check_common(plan, folder.rel_path, dst)
        self._check_busy(plan, folder.rel_path)
        plan.steps.append(Step(OpType.RENAME_DIR, folder.rel_path, dst))
        return plan

    def plan_move_folder(self, folder_id: int, dest_folder_id: int) -> Plan:
        folder = self.folder(folder_id)
        dest = self.folder(dest_folder_id)
        plan = Plan(f"Mover carpeta '{folder.name}' -> '{dest.rel_path or 'raiz'}'")
        if folder.parent_id is None or folder.rel_path == "":
            plan.conflicts.append(Conflict("IS_ROOT", "No se puede mover la raiz de la biblioteca"))
            return plan
        if _under(dest.rel_path, folder.rel_path):
            plan.conflicts.append(Conflict("INTO_ITSELF", "No se puede mover una carpeta dentro de si misma"))
            return plan
        if rel_key(dest.rel_path) == rel_key(parent_rel(folder.rel_path)):
            plan.conflicts.append(Conflict("NO_CHANGE", "Ya esta en esa carpeta"))
            return plan
        dst = _join(dest.rel_path, _basename(folder.rel_path))
        self._check_common(plan, folder.rel_path, dst)
        self._check_busy(plan, folder.rel_path)
        plan.steps.append(Step(OpType.MOVE_DIR, folder.rel_path, dst))
        return plan

    def plan_move_account(self, account_id: int, dest_folder_id: int) -> Plan:
        row = self.conn.execute(
            "SELECT id, username, rel_path FROM catalog_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise FsOpsError(f"Cuenta no encontrada: {account_id}")
        dest = self.folder(dest_folder_id)
        plan = Plan(f"Mover cuenta '{row['username']}' -> '{dest.rel_path or 'raiz'}'")
        if not row["rel_path"]:
            plan.conflicts.append(Conflict("NO_PATH", "La cuenta no tiene carpeta conocida en la biblioteca"))
            return plan
        src = str(row["rel_path"])
        if rel_key(dest.rel_path) == rel_key(parent_rel(src)):
            plan.conflicts.append(Conflict("NO_CHANGE", "Ya esta en esa carpeta"))
            return plan
        dst = _join(dest.rel_path, _basename(src))
        self._check_common(plan, src, dst)
        plan.affected_accounts = 1
        busy = self._busy_accounts([account_id])
        if busy:
            plan.conflicts.append(Conflict("ACCOUNT_IN_ACTIVE_BATCH", "La cuenta esta en un lote en ejecucion"))
        plan.steps.append(Step(OpType.MOVE_DIR, src, dst, account_id))
        return plan

    # -------------------------------------------------------------- execution
    def execute(self, plan: Plan) -> str:
        if not plan.can_execute:
            raise FsOpsError("; ".join(c.message for c in plan.blocking) or "Plan vacio")
        if not _LOCK.acquire(blocking=False):
            raise FsOpsError("Hay otra operacion de disco en curso")
        try:
            group = uuid.uuid4().hex
            for seq, step in enumerate(plan.steps, start=1):
                self._run_step(group, seq, step)
            return group
        finally:
            _LOCK.release()

    def _insert_op(self, group: str, seq: int, step: Step, undo_of: int | None = None) -> int:
        now = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO fs_operations (op_group, seq, op_type, src_rel, dst_rel, account_id,
                                       status, undo_of, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PLANNED', ?, ?, ?)
            """,
            (group, seq, step.op_type.value, step.src_rel, step.dst_rel, step.account_id, undo_of, now, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _set_status(self, op_id: int, status: OpStatus, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE fs_operations SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status.value, error, _now(), op_id),
        )

    def _run_step(self, group: str, seq: int, step: Step, undo_of: int | None = None) -> int:
        op_id = self._insert_op(group, seq, step, undo_of)
        try:
            self._disk(step.op_type, step.src_rel, step.dst_rel)
        except OSError as exc:
            self._set_status(op_id, OpStatus.FAILED, str(exc))
            self.conn.commit()
            raise FsOpsError(f"Fallo en disco: {exc}") from exc
        self._set_status(op_id, OpStatus.DISK_DONE)
        self.conn.commit()
        self._commit_db(op_id, step.op_type, step.src_rel, step.dst_rel)
        return op_id

    def _commit_db(self, op_id: int, op_type: OpType, src: str | None, dst: str | None) -> None:
        try:
            self._apply_db(op_type, src, dst)
            self._set_status(op_id, OpStatus.COMMITTED)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _disk(self, op_type: OpType, src: str | None, dst: str | None) -> None:
        if op_type is OpType.MKDIR:
            os.mkdir(self.abs(dst))
        elif op_type is OpType.RMDIR:
            os.rmdir(self.abs(src))
        else:
            source, target = self.abs(src), self.abs(dst)
            if rel_key(src) == rel_key(dst) and src != dst:
                # case-only rename on NTFS: go through a temporary name
                temp = f"{source}.__rename_{uuid.uuid4().hex[:8]}"
                os.rename(source, temp)
                os.rename(temp, target)
            else:
                os.rename(source, target)

    # -------------------------------------------------------------- DB effect
    def _apply_db(self, op_type: OpType, src: str | None, dst: str | None) -> None:
        if op_type is OpType.MKDIR:
            parent_id = self.folder_id_for_rel(parent_rel(dst))
            depth = len([p for p in dst.split("\\") if p])
            now = _now()
            self.conn.execute(
                """
                INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at,
                                             updated_at, rel_path, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (parent_id, _basename(dst), self.abs(dst), depth, now, now, dst,
                 "CATEGORY" if depth == 1 else "GROUP"),
            )
        elif op_type is OpType.RMDIR:
            folder_id = self.folder_id_for_rel(src)
            if folder_id is not None:
                self.conn.execute("DELETE FROM catalog_folders WHERE id = ?", (folder_id,))
        else:
            self._prefix_replace(src, dst)

    def _prefix_replace(self, src: str, dst: str) -> None:
        now = _now()
        new_parent_id = self.folder_id_for_rel(parent_rel(dst))
        for row in self._folders_under(src):
            rel = str(row["rel_path"])
            new_rel = dst + rel[len(src):]
            depth = len([p for p in new_rel.split("\\") if p])
            exact = rel_key(rel) == rel_key(src)
            self.conn.execute(
                """
                UPDATE catalog_folders SET name = ?, full_path = ?, rel_path = ?, depth = ?, kind = ?,
                    parent_id = CASE WHEN ? THEN ? ELSE parent_id END, updated_at = ?
                WHERE id = ?
                """,
                (_basename(new_rel), self.abs(new_rel), new_rel, depth,
                 "CATEGORY" if depth == 1 else "GROUP", 1 if exact else 0, new_parent_id, now, row["id"]),
            )
        for row in self._accounts_under(src):
            rel = str(row["rel_path"])
            new_rel = dst + rel[len(src):]
            if rel_key(rel) == rel_key(src):  # the account folder itself
                self.conn.execute(
                    "UPDATE catalog_accounts SET rel_path = ?, folder_id = ?, updated_at = ? WHERE id = ?",
                    (new_rel, new_parent_id, now, row["id"]),
                )
            else:
                self.conn.execute(
                    "UPDATE catalog_accounts SET rel_path = ?, updated_at = ? WHERE id = ?",
                    (new_rel, now, row["id"]),
                )

    # -------------------------------------------------------------- recovery
    def recover(self) -> list[str]:
        """Resolve operations left in PLANNED/DISK_DONE by an interrupted run."""

        messages: list[str] = []
        rows = self.conn.execute(
            "SELECT id, op_type, src_rel, dst_rel FROM fs_operations"
            " WHERE status IN ('PLANNED', 'DISK_DONE') ORDER BY id"
        ).fetchall()
        for row in rows:
            op_type = OpType(row["op_type"])
            src, dst = row["src_rel"], row["dst_rel"]
            src_exists = bool(src) and os.path.exists(self.abs(src))
            dst_exists = bool(dst) and os.path.exists(self.abs(dst))
            if op_type is OpType.RMDIR:
                done = not src_exists
            elif op_type is OpType.MKDIR:
                done = dst_exists
            else:
                done = dst_exists and not (src_exists and rel_key(src) != rel_key(dst))
            if done:
                try:
                    self._commit_db(int(row["id"]), op_type, src, dst)
                    messages.append(f"Completada operacion pendiente: {op_type.value} {src or ''} -> {dst or ''}")
                except Exception as exc:  # noqa: BLE001 - reported to the user
                    self._set_status(int(row["id"]), OpStatus.FAILED, str(exc))
                    self.conn.commit()
                    messages.append(f"No se pudo completar {op_type.value}: {exc}")
            else:
                self._set_status(int(row["id"]), OpStatus.FAILED, "No se llego a ejecutar en disco")
                self.conn.commit()
                messages.append(f"Descartada operacion no ejecutada: {op_type.value} {src or ''} -> {dst or ''}")
        return messages

    # ------------------------------------------------------------------ undo
    def can_undo(self, op_group: str) -> tuple[bool, str]:
        rows = self._group_rows(op_group)
        if not rows or any(r["status"] != "COMMITTED" for r in rows):
            return False, "Solo se pueden deshacer grupos completados"
        if self.conn.execute("SELECT 1 FROM fs_operations WHERE undo_of IN (%s) LIMIT 1" % ",".join(str(r["id"]) for r in rows)).fetchone():
            return False, "Ya fue deshecho"
        if not self.is_online():
            return False, "La biblioteca (G:) no esta disponible"
        for row in rows:
            op_type = OpType(row["op_type"])
            if op_type is OpType.MKDIR:
                target = self.abs(row["dst_rel"])
                if not os.path.isdir(target) or os.listdir(target):
                    return False, f"La carpeta creada ya no esta vacia o no existe: {row['dst_rel']}"
            else:
                if not os.path.exists(self.abs(row["dst_rel"])):
                    return False, f"El estado actual no coincide: falta {row['dst_rel']}"
                if rel_key(row["src_rel"]) != rel_key(row["dst_rel"]) and os.path.exists(self.abs(row["src_rel"])):
                    return False, f"El origen ya existe de nuevo: {row['src_rel']}"
        return True, ""

    def undo(self, op_group: str) -> str:
        ok, reason = self.can_undo(op_group)
        if not ok:
            raise FsOpsError(reason)
        if not _LOCK.acquire(blocking=False):
            raise FsOpsError("Hay otra operacion de disco en curso")
        try:
            group = uuid.uuid4().hex
            rows = self._group_rows(op_group)
            for seq, row in enumerate(reversed(rows), start=1):
                op_type = OpType(row["op_type"])
                if op_type is OpType.MKDIR:
                    step = Step(OpType.RMDIR, row["dst_rel"], None)
                elif op_type is OpType.RMDIR:
                    step = Step(OpType.MKDIR, None, row["src_rel"])
                else:
                    step = Step(op_type, row["dst_rel"], row["src_rel"], row["account_id"])
                self._run_step(group, seq, step, undo_of=int(row["id"]))
                self._set_status(int(row["id"]), OpStatus.UNDONE)
                self.conn.commit()
            return group
        finally:
            _LOCK.release()

    def _group_rows(self, op_group: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM fs_operations WHERE op_group = ? ORDER BY seq", (op_group,)
        ).fetchall()

    def history(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT op_group, MIN(created_at) AS created_at, COUNT(*) AS steps,
                   GROUP_CONCAT(DISTINCT op_type) AS op_types,
                   MIN(src_rel) AS src_rel, MIN(dst_rel) AS dst_rel,
                   MAX(CASE WHEN undo_of IS NOT NULL THEN 1 ELSE 0 END) AS is_undo,
                   MIN(status) AS status
            FROM fs_operations GROUP BY op_group ORDER BY MIN(id) DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
