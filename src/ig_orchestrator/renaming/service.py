"""Integrated renamer: preview and run the rename of a download folder against bdapp.

Replaces the external ``ManualRenameFiles --newRename`` call: the account folders come from bdapp
(``catalog_accounts.rel_path`` + the ``LIBRARY`` root), new accounts are registered in bdapp, and the
result is stored in ``rename_runs`` / ``rename_run_accounts``.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from ig_orchestrator.library.compat_lite import add_to_lite, lite_path_from_settings
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import parent_rel, to_rel
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming.mover import FAILED, MOVED, MoveResult, move_renamed_folder, preview_move
from ig_orchestrator.renaming.planner import (
    DiskConsultProvider,
    DryOps,
    FileAction,
    NewUser,
    RealOps,
    TreeResult,
    process_folder_tree,
)
from ig_orchestrator.renaming.timeline import TimelineContext

ProgressCallback = Callable[[int, int, str], None]
RENAMED, NEW_ACCOUNT, SKIPPED = "RENAMED", "NEW", "SKIPPED"


@dataclass(frozen=True, slots=True)
class NewAccountSpec:
    username: str
    owner_id: str
    start_init_date: str
    destination_path: str


@dataclass(slots=True)
class RenameJob:
    source_folder: str
    start_now_date: str
    new_accounts: tuple[NewAccountSpec, ...] = ()
    no_duplicated: bool = True
    move_renamed: bool = True


@dataclass(slots=True)
class AccountPlan:
    username: str
    folder_name: str
    manual_path: str
    consult_folder: str = ""
    status: str = RENAMED  # RENAMED | NEW | SKIPPED
    reason: str = ""
    spec: NewAccountSpec | None = None
    account_id: int | None = None
    tree: TreeResult = field(default_factory=TreeResult)
    move: MoveResult | None = None

    @property
    def renamed(self) -> int:
        return sum(1 for a in self.tree.actions if a.kind == "RENAME")

    @property
    def duplicated(self) -> int:
        return sum(1 for a in self.tree.actions if a.kind == "DUPLICATE")

    @property
    def actions(self) -> list[FileAction]:
        return self.tree.actions


@dataclass(slots=True)
class RenamePreview:
    job: RenameJob
    seed: int
    now: datetime
    accounts: list[AccountPlan] = field(default_factory=list)

    @property
    def runnable(self) -> bool:
        return any(a.status != SKIPPED for a in self.accounts)


@dataclass(slots=True)
class AccountResult:
    username: str
    status: str  # RENAMED | NEW | SKIPPED | MOVE_CONFLICT | ERROR | NO_FILES
    renamed: int = 0
    duplicated: int = 0
    deleted_duplicates: int = 0
    moved: bool = False
    detail: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RenameResult:
    run_id: int = 0
    accounts: list[AccountResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def problems(self) -> list[AccountResult]:
        return [a for a in self.accounts if a.status in ("SKIPPED", "MOVE_CONFLICT", "ERROR")]

    @property
    def ok(self) -> bool:
        return not self.cancelled and not self.problems

    def summary(self) -> str:
        return (
            f"{len(self.accounts)} cuentas · {sum(a.renamed for a in self.accounts)} renombrados · "
            f"{sum(a.duplicated for a in self.accounts)} duplicados · "
            f"{sum(a.deleted_duplicates for a in self.accounts)} duplicados eliminados · "
            f"{sum(1 for a in self.accounts if a.moved)} carpetas movidas · {len(self.problems)} con problemas"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_path_inside(path: str, roots: list[str]) -> bool:
    absolute = os.path.abspath(path)
    for root in roots:
        base = os.path.abspath(root)
        try:
            if os.path.commonpath([absolute, base]) == base:
                return True
        except ValueError:
            continue
    return False


def resolve_account_folder(configured: str, username: str) -> str:
    """Accept either the account folder or its destination parent."""

    normalized = os.path.normpath(configured)
    if os.path.basename(normalized).casefold() == username.casefold():
        return normalized
    return os.path.join(normalized, username)


class RenameService:
    def __init__(self, conn: sqlite3.Connection, *, root: str | None = None) -> None:
        self.conn = conn
        self.fs = FsOperationService(conn, root=root)

    # ------------------------------------------------------------- planning
    def _parse_date(self, text: str) -> date:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()

    def _targets(self, job: RenameJob) -> list[AccountPlan]:
        if not os.path.isdir(job.source_folder):
            raise ValueError(f"La carpeta de origen no existe: {job.source_folder}")
        specs = {s.username.casefold(): s for s in job.new_accounts}
        folders = {
            name.casefold(): (name, os.path.join(job.source_folder, name))
            for name in os.listdir(job.source_folder)
            if os.path.isdir(os.path.join(job.source_folder, name))
        }
        plans: list[AccountPlan] = []
        for key, spec in specs.items():
            if key not in folders:
                plans.append(AccountPlan(spec.username, spec.username, "", status=SKIPPED,
                                         reason="La cuenta nueva no esta como carpeta en el origen", spec=spec))
        for key, (name, manual_path) in folders.items():
            spec = specs.get(key)
            row = self.conn.execute(
                "SELECT id, rel_path FROM catalog_accounts WHERE username = ? COLLATE NOCASE AND rel_path IS NOT NULL",
                (name,),
            ).fetchone()
            plan = AccountPlan(name, name, manual_path, spec=spec, account_id=int(row["id"]) if row else None)
            if spec is not None:
                if row is not None:
                    plan.status, plan.reason = SKIPPED, "Declarada como nueva pero ya esta registrada en la app"
                else:
                    plan.status = NEW_ACCOUNT
                    plan.consult_folder = resolve_account_folder(spec.destination_path, name)
            elif row is None:
                plan.status, plan.reason = SKIPPED, "No esta registrada en la app y no se declaro como cuenta nueva"
            else:
                plan.consult_folder = self.fs.abs(str(row["rel_path"]))
                if not os.path.isdir(plan.consult_folder):
                    plan.status, plan.reason = SKIPPED, f"La carpeta registrada no existe: {plan.consult_folder}"
            plans.append(plan)
        return plans

    def _context(self, job: RenameJob, rng: random.Random, now: datetime, spec: NewAccountSpec | None):
        if spec is None:
            return TimelineContext(rng, now), None
        start = datetime.strptime(spec.start_init_date, "%Y-%m-%d")
        return TimelineContext(rng, now, forced_user_id=spec.owner_id, flag_new=True), NewUser(start, spec.owner_id)

    def _base_now(self, job: RenameJob, now: datetime | None) -> datetime:
        reference = now or datetime.now()
        return datetime.combine(self._parse_date(job.start_now_date), reference.time())

    def preview(self, job: RenameJob, *, seed: int | None = None, now: datetime | None = None) -> RenamePreview:
        seed = random.SystemRandom().randrange(1, 2**31) if seed is None else seed
        stamp = self._base_now(job, now)
        rng = random.Random(seed)
        preview = RenamePreview(job, seed, stamp)
        for plan in self._targets(job):
            preview.accounts.append(plan)
            if plan.status == SKIPPED:
                continue
            ctx, new_user = self._context(job, rng, stamp, plan.spec)
            provider = DiskConsultProvider(plan.consult_folder)
            plan.tree = process_folder_tree(plan.manual_path, provider, DryOps(), ctx, new_user)
            if job.move_renamed:
                plan.move = preview_move(plan.manual_path, plan.consult_folder)
        return preview

    # ------------------------------------------------------------ execution
    def run(
        self,
        preview: RenamePreview,
        *,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> RenameResult:
        """Apply the job again with the preview's seed/clock so names equal what was previewed."""

        job = preview.job
        cancel = cancel_event or threading.Event()
        rng = random.Random(preview.seed)
        result = RenameResult()
        result.run_id = self._start_run(job, preview.seed)
        plans = self._targets(job)
        total = len(plans)
        for index, plan in enumerate(plans, start=1):
            if cancel.is_set():
                result.cancelled = True
                break
            if progress is not None:
                progress(index, total, plan.username)
            result.accounts.append(self._run_account(job, plan, rng, preview.now))
        self._finish_run(result)
        return result

    def _run_account(self, job: RenameJob, plan: AccountPlan, rng: random.Random, now: datetime) -> AccountResult:
        if plan.status == SKIPPED:
            return AccountResult(plan.username, "SKIPPED", detail=plan.reason)
        ctx, new_user = self._context(job, rng, now, plan.spec)
        provider = DiskConsultProvider(plan.consult_folder)
        tree = process_folder_tree(plan.manual_path, provider, RealOps(), ctx, new_user)
        outcome = AccountResult(
            plan.username,
            plan.status,
            renamed=sum(1 for a in tree.actions if a.kind == "RENAME"),
            duplicated=sum(1 for a in tree.actions if a.kind == "DUPLICATE"),
            warnings=[*tree.warnings, *tree.errors],
        )
        if tree.errors:
            outcome.status = "ERROR"
            outcome.detail = tree.errors[0]
        if job.no_duplicated:
            outcome.deleted_duplicates = self._delete_duplicates(tree.duplicated_files, plan.manual_path, outcome)
        if not (outcome.renamed or outcome.duplicated) and outcome.status == plan.status:
            outcome.status = "NO_FILES" if plan.status == RENAMED else outcome.status
        if job.move_renamed:
            moved = move_renamed_folder(plan.manual_path, plan.consult_folder)
            outcome.moved = moved.status == MOVED
            if moved.status == FAILED:
                outcome.status = "MOVE_CONFLICT"
                outcome.detail = moved.detail + (": " + ", ".join(moved.conflicts[:5]) if moved.conflicts else "")
        try:
            self._record_in_bdapp(plan, outcome)
        except Exception as exc:  # noqa: BLE001 - the files are already renamed; report it
            outcome.warnings.append(f"No se pudo actualizar la base de la app: {exc}")
        self._store_account(outcome)
        return outcome

    def _delete_duplicates(self, files: list[str], manual_path: str, outcome: AccountResult) -> int:
        deleted = 0
        for path in files:
            if "_duplicated" not in os.path.basename(path) or not is_path_inside(path, [manual_path]) or not os.path.isfile(path):
                outcome.warnings.append(f"No se elimina el duplicado: {os.path.basename(path)}")
                continue
            try:
                os.remove(path)
                deleted += 1
            except OSError as exc:
                outcome.warnings.append(f"No se pudo eliminar {os.path.basename(path)}: {exc}")
        return deleted

    # -------------------------------------------------------------- bdapp
    def _record_in_bdapp(self, plan: AccountPlan, outcome: AccountResult) -> None:
        account_id = plan.account_id
        if plan.status == NEW_ACCOUNT and plan.spec is not None:
            account_id = self._register_new(plan, outcome)
        if account_id is not None and outcome.moved:
            try:
                LibraryScanner(self.conn, root=self.fs.root).scan(ACCOUNT, account_id=account_id)
            except Exception as exc:  # noqa: BLE001 - a scan in progress or an offline disk must not fail the rename
                outcome.warnings.append(f"Contadores no actualizados ({exc}); usa Sincronizar")

    def _register_new(self, plan: AccountPlan, outcome: AccountResult) -> int:
        spec = plan.spec
        now = _now()
        row = self.conn.execute(
            "SELECT id, instagram_user_id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (spec.username,)
        ).fetchone()
        if row is None:
            status = self.conn.execute("SELECT id FROM catalog_account_statuses WHERE code = 'ENABLED'").fetchone()[0]
            account_id = int(self.conn.execute(
                "INSERT INTO catalog_accounts (username, instagram_user_id, status_id, is_favorite, created_at, updated_at)"
                " VALUES (?, ?, ?, 0, ?, ?)",
                (spec.username, spec.owner_id, status, now, now),
            ).lastrowid)
        else:
            account_id = int(row["id"])
            if not str(row["instagram_user_id"] or "").strip():
                self.conn.execute("UPDATE catalog_accounts SET instagram_user_id = ? WHERE id = ?", (spec.owner_id, account_id))
        self.conn.execute("UPDATE catalog_accounts SET start_init_date = COALESCE(start_init_date, ?) WHERE id = ?",
                          (spec.start_init_date, account_id))
        if outcome.moved:
            rel = to_rel(plan.consult_folder, self.fs.root)
            if rel is not None:
                folder_id = self.fs.ensure_folder_rows(parent_rel(rel))
                self.conn.execute(
                    "UPDATE catalog_accounts SET rel_path = ?, folder_id = ?, disk_state = 'PRESENT', updated_at = ? WHERE id = ?",
                    (rel, folder_id, now, account_id),
                )
                self.conn.commit()
                lite = lite_path_from_settings(self.conn)
                if lite is not None:
                    try:
                        add_to_lite(self.conn, lite, account_id, self.fs.root, spec.start_init_date)
                    except (sqlite3.Error, OSError) as exc:
                        outcome.warnings.append(f"accounts_lite no actualizada: {exc}")
            else:
                outcome.warnings.append("La carpeta destino queda fuera de la biblioteca: cuenta sin ruta")
        else:
            outcome.warnings.append("Cuenta nueva sin mover: queda sin ruta hasta que se mueva a la biblioteca")
        self.conn.commit()
        return account_id

    # ------------------------------------------------------------ history
    def _start_run(self, job: RenameJob, seed: int) -> int:
        cursor = self.conn.execute(
            "INSERT INTO rename_runs (engine, source_folder, start_now_date, options, status, started_at)"
            " VALUES ('integrated', ?, ?, ?, 'RUNNING', ?)",
            (job.source_folder, job.start_now_date,
             json.dumps({"seed": seed, "no_duplicated": job.no_duplicated, "move_renamed": job.move_renamed}), _now()),
        )
        self.conn.commit()
        self._run_id = int(cursor.lastrowid)
        return self._run_id

    def _store_account(self, outcome: AccountResult) -> None:
        self.conn.execute(
            "INSERT INTO rename_run_accounts (rename_run_id, username, status, renamed, duplicated, moved, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self._run_id, outcome.username, outcome.status, outcome.renamed, outcome.duplicated,
             int(outcome.moved), outcome.detail or "; ".join(outcome.warnings[:3])),
        )
        self.conn.commit()

    def _finish_run(self, result: RenameResult) -> None:
        status = "CANCELLED" if result.cancelled else ("OK" if result.ok else "WITH_PROBLEMS")
        self.conn.execute("UPDATE rename_runs SET status = ?, finished_at = ? WHERE id = ?", (status, _now(), self._run_id))
        self.conn.commit()
