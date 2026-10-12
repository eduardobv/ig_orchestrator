"""Rename an account (Instagram username changed) or merge it into the account that already has the new name.

* **Simple rename**: the same ``catalog_accounts`` row (same primary key) gets the new username; the folder is
  renamed on disk; the old name stays as an alias in ``account_usernames``.
* **Merge**: both accounts exist (or a folder with the new name exists). Both must have the same
  ``instagram_user_id``. One folder/row survives; the other folder is merged into it without losing files
  (see ``merge.py``) and its batch references are re-pointed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.library import merge as merge_module
from ig_orchestrator.library.compat_lite import mirror_to_lite
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError
from ig_orchestrator.library.fsops_plan import Conflict, OpType, Plan, Step
from ig_orchestrator.library.owner_groups import Member
from ig_orchestrator.library.paths import parent_rel, rel_key

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
SIMPLE, MERGE, STATUS_ONLY = "RENAME", "MERGE", "STATUS_ONLY"
INACTIVE_STATUSES = ("ARCHIVED", "DELETED")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _basename(rel: str) -> str:
    return rel.rsplit("\\", 1)[-1]


def _join(parent: str, name: str) -> str:
    return f"{parent}\\{name}" if parent else name


@dataclass(slots=True)
class Candidate:
    account_id: int
    username: str
    rel_path: str | None
    owner_id: str
    content: int
    last_media_at: str
    on_disk: bool
    dead: bool = False  # lives in 09.DELETED / 06.EXCLUDED / a -Deleted group


@dataclass(slots=True)
class RenamePlan:
    plan: Plan
    scenario: str
    account_id: int
    old_username: str
    new_username: str
    survivor_id: int | None = None
    removed_id: int | None = None
    final_rel: str | None = None
    merge_report: merge_module.MergeReport | None = None
    candidates: list[Candidate] = field(default_factory=list)
    rewrite_urls: int = 0
    needs_confirmation: bool = False  # ids could not be compared (one side empty)
    orphan_folder: bool = False  # the new name is a folder without an account row

    @property
    def can_execute(self) -> bool:
        return not self.plan.blocking and (bool(self.plan.steps) or self.scenario in (SIMPLE, STATUS_ONLY, MERGE))


class AccountRenameService:
    def __init__(self, connection: sqlite3.Connection, *, fs: FsOperationService | None = None) -> None:
        self.conn = connection
        self.fs = fs or FsOperationService(connection)

    # ---------------------------------------------------------------- data
    def _account(self, account_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT a.*, s.code AS status FROM catalog_accounts a"
            " JOIN catalog_account_statuses s ON s.id = a.status_id WHERE a.id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise FsOpsError(f"Cuenta no encontrada: {account_id}")
        return row

    def _by_username(self, username: str, exclude_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT a.*, s.code AS status FROM catalog_accounts a"
            " JOIN catalog_account_statuses s ON s.id = a.status_id"
            " WHERE a.username = ? COLLATE NOCASE AND a.id <> ?",
            (username, exclude_id),
        ).fetchone()

    def _candidate(self, row: sqlite3.Row) -> Candidate:
        content = sum(int(row[c] or 0) for c in ("posts_count", "reels_count", "story_count", "highlights_count"))
        rel = row["rel_path"]
        return Candidate(
            int(row["id"]),
            str(row["username"]),
            rel,
            str(row["instagram_user_id"] or "").strip(),
            content,
            str(row["last_media_at"] or ""),
            bool(rel) and os.path.isdir(self.fs.abs(rel)),
            Member(int(row["id"]), str(row["username"]), str(rel or ""), str(row["status"]), "", content).is_dead,
        )

    # ---------------------------------------------------------------- plan
    def plan_rename(
        self,
        account_id: int,
        new_username: str,
        *,
        survivor: str = "auto",
        confirm_unverified: bool = False,
    ) -> RenamePlan:
        """``survivor``: ``auto`` | ``old`` (keep this account's row/folder) | ``new`` (keep the existing one)."""

        old = self._account(account_id)
        new_username = new_username.strip().lstrip("@")
        title = f"Cambio de username: @{old['username']} -> @{new_username}"
        result = RenamePlan(Plan(title), SIMPLE, account_id, str(old["username"]), new_username)
        plan = result.plan
        if not USERNAME_RE.match(new_username):
            plan.conflicts.append(Conflict("INVALID_USERNAME", "Username no valido (letras, numeros, . y _; hasta 30)"))
            return result
        if new_username == old["username"]:
            plan.conflicts.append(Conflict("NO_CHANGE", "El username es el mismo"))
            return result
        busy = self.fs._busy_accounts([account_id])
        other = self._by_username(new_username, account_id)
        if other is not None:
            busy += self.fs._busy_accounts([int(other["id"])])
        if busy:
            plan.conflicts.append(Conflict("ACCOUNT_IN_ACTIVE_BATCH", "Hay una cuenta en un lote en ejecucion"))
            return result

        online = self.fs.is_online()
        old_rel = old["rel_path"]
        old_dir_ok = bool(old_rel) and online and os.path.isdir(self.fs.abs(old_rel))
        new_rel_same_parent = _join(parent_rel(old_rel), new_username) if old_rel else None
        # a folder with the new name next to the old one (with or without an account row)
        orphan_dir = (
            new_rel_same_parent
            if new_rel_same_parent
            and rel_key(new_rel_same_parent) != rel_key(old_rel)
            and online
            and os.path.isdir(self.fs.abs(new_rel_same_parent))
            and other is None
            else None
        )
        plan.affected_accounts = 1

        if other is None and orphan_dir is None:  # --------------------- simple rename
            if not old_dir_ok:
                result.scenario = STATUS_ONLY
                plan.conflicts.append(
                    Conflict("NO_FOLDER", "La cuenta no tiene carpeta en disco: solo cambia el username", blocking=False)
                )
                result.survivor_id = account_id
                return result
            if not online:
                plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
                return result
            result.final_rel = new_rel_same_parent
            result.survivor_id = account_id
            plan.steps.append(Step(OpType.RENAME_DIR, old_rel, new_rel_same_parent, account_id))
            result.rewrite_urls = self._count_story_urls(account_id, str(old["username"]))
            if self.fs.conn.execute("SELECT 1 FROM catalog_accounts WHERE rel_path IS NOT NULL AND lower(rel_path)=lower(?)",
                                    (new_rel_same_parent,)).fetchone() and rel_key(new_rel_same_parent) != rel_key(old_rel):
                plan.conflicts.append(Conflict("DEST_IN_CATALOG", f"Ya hay una cuenta con la ruta {new_rel_same_parent}"))
            return result

        # -------------------------------------------------------------- merge
        result.scenario = MERGE
        result.orphan_folder = other is None
        new_row = other
        owner_old = str(old["instagram_user_id"] or "").strip()
        owner_new = str(new_row["instagram_user_id"] or "").strip() if new_row is not None else ""
        if owner_old and owner_new and owner_old != owner_new:
            plan.conflicts.append(
                Conflict("OWNER_MISMATCH", f"Los ids de Instagram son distintos ({owner_old} y {owner_new}): no se fusiona")
            )
            return result
        if not (owner_old and owner_new):
            result.needs_confirmation = True
            if not confirm_unverified:
                plan.conflicts.append(
                    Conflict("UNVERIFIED_ID", "No se puede comprobar que sean la misma cuenta (falta un id de Instagram): confirma para continuar")
                )
        if not online:
            plan.conflicts.append(Conflict("OFFLINE", "La biblioteca (G:) no esta disponible"))
            return result

        cand_old = self._candidate(old)
        if new_row is not None:
            cand_new = self._candidate(new_row)
            result.candidates = [cand_old, cand_new]
            new_rel = cand_new.rel_path
        else:
            new_rel = orphan_dir
            result.candidates = [cand_old, Candidate(0, new_username, new_rel, "", 0, "", True)]
            cand_new = result.candidates[1]

        keep_old = self._choose_survivor(survivor, cand_old, cand_new, orphan=new_row is None)
        if keep_old:
            survivor_row, removed_row = old, new_row
            survivor_rel, removed_rel = old_rel, new_rel
        else:
            survivor_row, removed_row = new_row, old
            survivor_rel, removed_rel = new_rel, old_rel
        result.survivor_id = int(survivor_row["id"]) if survivor_row is not None else None
        result.removed_id = int(removed_row["id"]) if removed_row is not None else None

        survivor_dir_ok = bool(survivor_rel) and os.path.isdir(self.fs.abs(survivor_rel))
        removed_dir_ok = bool(removed_rel) and os.path.isdir(self.fs.abs(removed_rel))
        if not survivor_dir_ok and not removed_dir_ok:
            result.scenario = STATUS_ONLY
            plan.conflicts.append(Conflict("NO_FOLDER", "Ninguna de las dos cuentas tiene carpeta en disco: solo se fusionan los datos", blocking=False))
            result.final_rel = None
        elif not survivor_dir_ok:
            # the survivor has no folder: the other folder simply becomes the survivor's (renamed/moved)
            survivor_rel = removed_rel
            result.final_rel = _join(parent_rel(removed_rel), new_username)
            if rel_key(result.final_rel) != rel_key(removed_rel):
                plan.steps.append(Step(OpType.RENAME_DIR, removed_rel, result.final_rel, result.survivor_id))
        else:
            if removed_dir_ok:
                report = merge_module.plan_merge(Path(self.fs.abs(removed_rel)), Path(self.fs.abs(survivor_rel)))
                result.merge_report = report
                plan.steps.append(Step(OpType.MERGE_DIR, removed_rel, survivor_rel, result.removed_id))
            result.final_rel = _join(parent_rel(survivor_rel), new_username)
            if rel_key(result.final_rel) != rel_key(survivor_rel) or result.final_rel != survivor_rel:
                plan.steps.append(Step(OpType.RENAME_DIR, survivor_rel, result.final_rel, result.survivor_id))
        plan.affected_accounts = 2 if result.removed_id else 1
        result.rewrite_urls = self._count_story_urls(account_id, str(old["username"]))
        return result

    @staticmethod
    def _choose_survivor(mode: str, old: Candidate, new: Candidate, *, orphan: bool) -> bool:
        """True when the renamed account (``old``) is the survivor."""

        if orphan:
            return True  # the orphan folder has no row: keep the account and merge the folder into its own
        if mode == "old":
            return True
        if mode == "new":
            return False
        if old.dead != new.dead:  # keep the location that is still in use, not the archived one
            return not old.dead
        if old.content != new.content:
            return old.content > new.content
        return old.account_id <= new.account_id  # older account

    def _count_story_urls(self, account_id: int, old_username: str) -> int:
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) FROM batch_urls bu JOIN batch_accounts ba ON ba.id = bu.batch_account_id
            JOIN batches b ON b.id = ba.batch_id JOIN batch_statuses bs ON bs.id = b.status_id
            WHERE ba.catalog_account_id = ? AND bs.code IN ('DRAFT', 'IMPORTED')
              AND lower(bu.url) LIKE ?
            """,
            (account_id, f"%/stories/{old_username.lower()}/%"),
        ).fetchone()
        return int(row[0])

    # ----------------------------------------------------------- execution
    def execute(self, rp: RenamePlan, *, lite_path: Path | None = None, root: str | None = None) -> str | None:
        if not rp.can_execute:
            raise FsOpsError("; ".join(c.message for c in rp.plan.blocking) or "Nada que hacer")
        survivor_before = dict(
            self.conn.execute(
                "SELECT * FROM catalog_accounts WHERE id = ?",
                (rp.survivor_id if rp.survivor_id is not None else rp.account_id,),
            ).fetchone()
        )
        removed_before = None
        if rp.removed_id is not None:
            removed_before = dict(self.conn.execute("SELECT * FROM catalog_accounts WHERE id = ?", (rp.removed_id,)).fetchone())
            # free its path so the survivor can take the final one without a unique-index clash
            self.conn.execute("UPDATE catalog_accounts SET rel_path = NULL WHERE id = ?", (rp.removed_id,))
            self.conn.commit()
        try:
            group = self.fs.execute(rp.plan) if rp.plan.steps else None
        except Exception:
            if removed_before is not None:
                self.conn.execute("UPDATE catalog_accounts SET rel_path = ? WHERE id = ?",
                                  (removed_before["rel_path"], rp.removed_id))
                self.conn.commit()
            raise
        lifecycle_group = group or f"db-{_now()}"
        try:
            snapshot = self._apply_db(rp, lifecycle_group, removed_before, survivor_before)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        if lite_path is not None:
            self._sync_lite(lite_path, root or self.fs.root, snapshot.get("removed", {}).get("legacy_lite_id"))
        return group

    def _sync_lite(self, lite_path: Path, root: str, removed_lite_id: int | None) -> None:
        try:
            if not lite_path.is_file():
                return
            lite = sqlite3.connect(lite_path, timeout=5)
            try:
                for row in self.conn.execute(
                    "SELECT legacy_lite_id, username FROM catalog_accounts WHERE legacy_lite_id IS NOT NULL"
                ):
                    lite.execute("UPDATE accounts_dir SET username = ? WHERE id = ? AND username <> ?",
                                 (row["username"], row["legacy_lite_id"], row["username"]))
                if removed_lite_id is not None:
                    lite.execute("DELETE FROM accounts_dir WHERE id = ?", (removed_lite_id,))
                lite.commit()
            finally:
                lite.close()
            mirror_to_lite(self.conn, lite_path, root)
        except (sqlite3.Error, OSError):
            pass  # lite is a transitional mirror; the audit reports any drift

    # ------------------------------------------------------------- DB part
    def _ensure_aliases(self, account_id: int, username: str) -> None:
        if not self.conn.execute("SELECT 1 FROM account_usernames WHERE catalog_account_id = ?", (account_id,)).fetchone():
            self.conn.execute(
                "INSERT INTO account_usernames (catalog_account_id, username, valid_from, valid_to, reason, created_at)"
                " VALUES (?, ?, NULL, NULL, 'INITIAL', ?)",
                (account_id, username, _now()),
            )

    def _apply_db(
        self, rp: RenamePlan, op_group: str, removed_before: dict | None = None, survivor_before: dict | None = None
    ) -> dict:
        now, today = _now(), _today()
        survivor_id = rp.survivor_id if rp.survivor_id is not None else rp.account_id
        survivor = self.conn.execute("SELECT * FROM catalog_accounts WHERE id = ?", (survivor_id,)).fetchone()
        removed = (
            self.conn.execute("SELECT * FROM catalog_accounts WHERE id = ?", (rp.removed_id,)).fetchone()
            if rp.removed_id is not None
            else None
        )
        snapshot: dict = {
            "scenario": rp.scenario,
            "old_username": rp.old_username,
            "new_username": rp.new_username,
            "survivor": survivor_before or dict(survivor),
            "removed": (removed_before or dict(removed)) if removed is not None else {},
            "repointed_ba": [],
            "merged_same_batch": False,
            "alias_created": [],
            "alias_moved": [],
            "alias_closed": [],
            "url_rewrites": [],
        }
        self._ensure_aliases(survivor_id, str(survivor["username"]))
        if removed is not None:
            self._ensure_aliases(int(removed["id"]), str(removed["username"]))

        if removed is not None:
            self._merge_rows(survivor, removed, snapshot)

        # new username + location on the survivor
        final_rel = rp.final_rel if rp.final_rel is not None else survivor["rel_path"]
        folder_id = survivor["folder_id"]
        if rp.final_rel is not None:
            folder_id = self.fs.ensure_folder_rows(parent_rel(rp.final_rel)) or folder_id
        # the removed row must disappear first (unique username / rel_path)
        if removed is not None:
            self.conn.execute("DELETE FROM catalog_accounts WHERE id = ?", (removed["id"],))
        self.conn.execute(
            "UPDATE catalog_accounts SET username = ?, rel_path = ?, folder_id = ?, updated_at = ? WHERE id = ?",
            (rp.new_username, final_rel, folder_id, now, survivor_id),
        )
        self._rotate_aliases(survivor_id, rp, snapshot, today, now)
        snapshot["url_rewrites"] = self._rewrite_story_urls(survivor_id, rp.old_username, rp.new_username)
        self.conn.execute(
            "INSERT INTO account_lifecycle (op_group, account_id, kind, prev_status_id, prev_favorite, prev_rel_path,"
            " created_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (op_group, survivor_id, rp.scenario if rp.scenario != STATUS_ONLY else "RENAME",
             survivor["status_id"], survivor["is_favorite"], (survivor_before or survivor)["rel_path"], now,
             json.dumps(snapshot, ensure_ascii=False, default=str)),
        )
        return snapshot

    def _merge_rows(self, survivor: sqlite3.Row, removed: sqlite3.Row, snapshot: dict) -> None:
        s_id, o_id = int(survivor["id"]), int(removed["id"])
        # --- data carried over to the survivor
        updates: dict[str, object] = {}
        if not str(survivor["instagram_user_id"] or "").strip() and removed["instagram_user_id"]:
            updates["instagram_user_id"] = removed["instagram_user_id"]
        s_status = self.conn.execute("SELECT code FROM catalog_account_statuses WHERE id = ?", (survivor["status_id"],)).fetchone()[0]
        o_status = self.conn.execute("SELECT code FROM catalog_account_statuses WHERE id = ?", (removed["status_id"],)).fetchone()[0]
        if s_status in INACTIVE_STATUSES and o_status not in INACTIVE_STATUSES:
            updates["status_id"] = removed["status_id"]
        if removed["is_favorite"] and not survivor["is_favorite"]:
            updates["is_favorite"] = 1
        if not survivor["start_init_date"] and removed["start_init_date"]:
            updates["start_init_date"] = removed["start_init_date"]
        for column in ("posts_count", "reels_count", "story_count", "highlights_count"):
            a, b = survivor[column], removed[column]
            if a is not None or b is not None:
                updates[column] = int(a or 0) + int(b or 0)
        if (removed["last_media_at"] or "") > (survivor["last_media_at"] or ""):
            updates["last_media_at"] = removed["last_media_at"]
        if updates:
            assignments = ", ".join(f"{c} = ?" for c in updates)
            self.conn.execute(f"UPDATE catalog_accounts SET {assignments} WHERE id = ?", (*updates.values(), s_id))

        # --- batches: re-point references, merging rows of the same batch
        for ba in self.conn.execute("SELECT id, batch_id FROM batch_accounts WHERE catalog_account_id = ?", (o_id,)).fetchall():
            twin = self.conn.execute(
                "SELECT id FROM batch_accounts WHERE batch_id = ? AND catalog_account_id = ?", (ba["batch_id"], s_id)
            ).fetchone()
            if twin is None:
                self.conn.execute("UPDATE batch_accounts SET catalog_account_id = ? WHERE id = ?", (s_id, ba["id"]))
                snapshot["repointed_ba"].append(int(ba["id"]))
            else:
                snapshot["merged_same_batch"] = True
                self.conn.execute("UPDATE batch_urls SET batch_account_id = ? WHERE batch_account_id = ?", (twin["id"], ba["id"]))
                self.conn.execute("UPDATE batch_runs SET batch_account_id = ? WHERE batch_account_id = ?", (twin["id"], ba["id"]))
                self.conn.execute("DELETE FROM batch_accounts WHERE id = ?", (ba["id"],))
        # --- file index: keep the survivor's rows, move the others; counters will be rebuilt on the next scan
        self.conn.execute(
            "UPDATE media_index SET account_id = ? WHERE account_id = ? AND NOT EXISTS ("
            " SELECT 1 FROM media_index m WHERE m.account_id = ? AND m.kind = media_index.kind"
            " AND m.media_id = media_index.media_id)",
            (s_id, o_id, s_id),
        )
        self.conn.execute("DELETE FROM media_index_state WHERE account_id IN (?, ?)", (s_id, o_id))
        # --- history rows of the removed account move to the survivor
        moved = [int(r[0]) for r in self.conn.execute("SELECT id FROM account_usernames WHERE catalog_account_id = ?", (o_id,))]
        self.conn.execute("UPDATE account_usernames SET catalog_account_id = ? WHERE catalog_account_id = ?", (s_id, o_id))
        snapshot["alias_moved"] = moved
        self.conn.execute("UPDATE account_lifecycle SET account_id = ? WHERE account_id = ?", (s_id, o_id))
        self.conn.execute("UPDATE fs_operations SET account_id = ? WHERE account_id = ?", (s_id, o_id))

    def _rotate_aliases(self, account_id: int, rp: RenamePlan, snapshot: dict, today: str, now: str) -> None:
        for row in self.conn.execute(
            "SELECT id, username FROM account_usernames WHERE catalog_account_id = ? AND valid_to IS NULL", (account_id,)
        ).fetchall():
            if str(row["username"]).casefold() != rp.new_username.casefold():
                self.conn.execute("UPDATE account_usernames SET valid_to = ? WHERE id = ?", (today, row["id"]))
                snapshot["alias_closed"].append(int(row["id"]))
        current = self.conn.execute(
            "SELECT id FROM account_usernames WHERE catalog_account_id = ? AND username = ? COLLATE NOCASE"
            " AND valid_to IS NULL",
            (account_id, rp.new_username),
        ).fetchone()
        if current is None:
            cursor = self.conn.execute(
                "INSERT INTO account_usernames (catalog_account_id, username, valid_from, valid_to, reason, created_at)"
                " VALUES (?, ?, ?, NULL, 'RENAMED', ?)",
                (account_id, rp.new_username, today, now),
            )
            snapshot["alias_created"].append(int(cursor.lastrowid))
        else:
            self.conn.execute("UPDATE account_usernames SET username = ? WHERE id = ?", (rp.new_username, current["id"]))

    def _rewrite_story_urls(self, account_id: int, old: str, new: str) -> list[list]:
        rewritten = []
        for row in self.conn.execute(
            """
            SELECT bu.id, bu.url FROM batch_urls bu JOIN batch_accounts ba ON ba.id = bu.batch_account_id
            JOIN batches b ON b.id = ba.batch_id JOIN batch_statuses bs ON bs.id = b.status_id
            WHERE ba.catalog_account_id = ? AND bs.code IN ('DRAFT', 'IMPORTED')
            """,
            (account_id,),
        ).fetchall():
            url = str(row["url"])
            marker = f"/stories/{old}/"
            if marker.lower() in url.lower():
                index = url.lower().index(marker.lower())
                changed = url[:index] + f"/stories/{new}/" + url[index + len(marker):]
                self.conn.execute("UPDATE batch_urls SET url = ?, updated_at = ? WHERE id = ?", (changed, _now(), row["id"]))
                rewritten.append([int(row["id"]), url])
        return rewritten

    # ---------------------------------------------------------------- undo
    def undo_blocker(self, op_group: str) -> str:
        """Reason why the database part of a rename/merge cannot be undone ('' if it can)."""

        for row in self._lifecycle_rows(op_group):
            payload = json.loads(row["payload"] or "{}")
            if payload.get("merged_same_batch"):
                return "La fusion unio filas del mismo lote: no se puede deshacer automaticamente"
            current = self.conn.execute(
                "SELECT username FROM catalog_accounts WHERE id = ?", (row["account_id"],)
            ).fetchone()
            if current is None or str(current["username"]).casefold() != str(payload.get("new_username", "")).casefold():
                return "El username de la cuenta cambio despues: no se puede deshacer"
            removed = payload.get("removed") or {}
            if removed and self.conn.execute("SELECT 1 FROM catalog_accounts WHERE id = ?", (removed.get("id"),)).fetchone():
                return "El id de la cuenta eliminada ya se uso de nuevo"
        return ""

    def _lifecycle_rows(self, op_group: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM account_lifecycle WHERE op_group = ? AND kind IN ('RENAME', 'MERGE') AND undone = 0",
            (op_group,),
        ).fetchall()

    def restore_after_undo(self, op_group: str) -> int:
        """After ``FsOperationService.undo``: bring the database back (username, aliases, removed row)."""

        count = 0
        for row in self._lifecycle_rows(op_group):
            payload = json.loads(row["payload"] or "{}")
            survivor = payload["survivor"]
            sid = int(survivor["id"])
            self.conn.execute(
                "UPDATE catalog_accounts SET username = ?, rel_path = ?, folder_id = ?, status_id = ?, is_favorite = ?,"
                " instagram_user_id = ?, start_init_date = ?, posts_count = ?, reels_count = ?, story_count = ?,"
                " highlights_count = ?, last_media_at = ?, updated_at = ? WHERE id = ?",
                (survivor["username"], survivor["rel_path"], survivor["folder_id"], survivor["status_id"],
                 survivor["is_favorite"], survivor["instagram_user_id"], survivor["start_init_date"],
                 survivor["posts_count"], survivor["reels_count"], survivor["story_count"],
                 survivor["highlights_count"], survivor["last_media_at"], _now(), sid),
            )
            removed = payload.get("removed") or {}
            if removed:
                columns = list(removed.keys())
                self.conn.execute(
                    f"INSERT INTO catalog_accounts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                    [removed[c] for c in columns],
                )
                for ba_id in payload.get("repointed_ba", []):
                    self.conn.execute("UPDATE batch_accounts SET catalog_account_id = ? WHERE id = ?", (removed["id"], ba_id))
                for alias_id in payload.get("alias_moved", []):
                    self.conn.execute("UPDATE account_usernames SET catalog_account_id = ? WHERE id = ?", (removed["id"], alias_id))
                self.conn.execute("DELETE FROM media_index_state WHERE account_id IN (?, ?)", (sid, removed["id"]))
            for alias_id in payload.get("alias_created", []):
                self.conn.execute("DELETE FROM account_usernames WHERE id = ?", (alias_id,))
            for alias_id in payload.get("alias_closed", []):
                self.conn.execute("UPDATE account_usernames SET valid_to = NULL WHERE id = ?", (alias_id,))
            if not removed:
                self.conn.execute(
                    "UPDATE account_usernames SET username = ? WHERE catalog_account_id = ? AND valid_to IS NULL",
                    (survivor["username"], sid),
                )
            for url_id, url in payload.get("url_rewrites", []):
                self.conn.execute("UPDATE batch_urls SET url = ? WHERE id = ?", (url, url_id))
            self.conn.execute("UPDATE account_lifecycle SET undone = 1 WHERE id = ?", (row["id"],))
            count += 1
        self.conn.commit()
        return count

    # --------------------------------------------------------------- alias
    def resolve_alias(self, username: str) -> list[tuple[int, str]]:
        """Accounts that used *username* in the past: ``[(account_id, current_username)]``."""

        rows = self.conn.execute(
            """
            SELECT DISTINCT a.id, a.username FROM account_usernames u
            JOIN catalog_accounts a ON a.id = u.catalog_account_id
            WHERE u.username = ? COLLATE NOCASE AND a.username <> ? COLLATE NOCASE
            """,
            (username, username),
        ).fetchall()
        return [(int(r["id"]), str(r["username"])) for r in rows]
