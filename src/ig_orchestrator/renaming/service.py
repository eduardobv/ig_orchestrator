"""Integrated renamer: preview and run the rename of a download folder against bdapp.

Replaces the external ``ManualRenameFiles --newRename`` call: the account folders come from bdapp
(``catalog_accounts.rel_path`` + the ``LIBRARY`` root), new accounts are registered in bdapp, and the
result is stored in ``rename_runs`` / ``rename_run_accounts``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import shutil
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from ig_orchestrator.library.compat_lite import add_to_lite, lite_path_from_settings
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import parent_rel, to_rel
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming.consult import IndexConsultProvider, has_index, write_through
from ig_orchestrator.renaming.mover import (
    FAILED,
    MOVED,
    MoveResult,
    destination_for,
    move_folder_to,
    move_renamed_folder,
    preview_move,
    preview_move_to,
)
from ig_orchestrator.staging import StagingService
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
PENDING_MOVE = "RENAMED_PENDING_MOVE"
REFERENCES = ("auto", "index", "disk")


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
    reference: str = "auto"  # auto | index | disk
    destination: str = "library"  # library | staging


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
    reference: str = "DISK"  # DISK | INDEX | NONE (new account)
    pending_move: bool = False
    staging_rel: str = ""  # destination inside the staging root (destination = staging)
    target_rel: str = ""

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
    pending: bool = False
    staged: bool = False


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
        if job.destination == "staging":
            StagingService(self.conn, root=self.fs.root).staging_root()  # raises ValueError when not configured
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
                self._choose_reference(job, plan)
            if job.destination == "staging" and plan.status != SKIPPED:
                self._staging_target(plan)
            plans.append(plan)
        return plans

    def _staging_target(self, plan: AccountPlan) -> None:
        """Where a renamed folder goes in the staging area: the same relative place it will have in the library."""

        rel = to_rel(destination_for(plan.manual_path, plan.consult_folder), self.fs.root)
        if rel is None:
            plan.status, plan.reason = SKIPPED, "El destino queda fuera de la biblioteca: no se puede almacenar"
            return
        plan.staging_rel = plan.target_rel = rel

    def _library_online(self) -> bool:
        return os.path.isdir(self.fs.root)

    def _destination_online(self, plan: AccountPlan) -> bool:
        """False when the move target is inside the library but the library (``G:``) is not reachable."""

        if to_rel(plan.consult_folder, self.fs.root) is None:
            return True
        return self._library_online()

    def _choose_reference(self, job: RenameJob, plan: AccountPlan) -> None:
        """Disk when the account folder is reachable (exact); the app index otherwise or when forced."""

        reachable = os.path.isdir(plan.consult_folder)
        if job.reference == "disk" or (job.reference == "auto" and reachable):
            if not reachable:
                plan.status, plan.reason = SKIPPED, f"La carpeta registrada no existe: {plan.consult_folder}"
            return
        if plan.account_id is not None and has_index(self.conn, plan.account_id):
            plan.reference = "INDEX"
        else:
            plan.status = SKIPPED
            plan.reason = "NO_INDEX: la biblioteca no esta disponible y la cuenta no tiene indice en la app"

    def _provider(self, plan: AccountPlan):
        if plan.reference == "INDEX" and plan.account_id is not None:
            return IndexConsultProvider(self.conn, plan.account_id)
        return DiskConsultProvider(plan.consult_folder)

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
            plan.tree = process_folder_tree(plan.manual_path, self._provider(plan), DryOps(), ctx, new_user)
            if job.move_renamed and job.destination == "staging" and plan.status != SKIPPED:
                staging = StagingService(self.conn, root=self.fs.root)
                plan.move = preview_move_to(plan.manual_path, staging.staging_path(plan.staging_rel))
            elif job.move_renamed:
                if self._destination_online(plan):
                    plan.move = preview_move(plan.manual_path, plan.consult_folder)
                else:
                    plan.pending_move = True
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
        tree = process_folder_tree(plan.manual_path, self._provider(plan), RealOps(), ctx, new_user)
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
        if job.move_renamed and job.destination == "staging":
            self._stage(plan, outcome)
        elif job.move_renamed and not self._destination_online(plan):
            if os.path.isdir(plan.manual_path):
                outcome.pending = True
                outcome.status = PENDING_MOVE
                outcome.detail = "Biblioteca no disponible: renombrada en su sitio, pendiente de mover"
        elif job.move_renamed:
            moved = move_renamed_folder(plan.manual_path, plan.consult_folder)
            outcome.moved = moved.status == MOVED
            if moved.status == FAILED:
                outcome.status = "MOVE_CONFLICT"
                outcome.detail = moved.detail + (": " + ", ".join(moved.conflicts[:5]) if moved.conflicts else "")
        try:
            account_id = self._record_in_bdapp(plan, outcome)
            plan.account_id = account_id if account_id is not None else plan.account_id
            if not outcome.moved and plan.account_id is not None and tree.actions:
                self._index_renamed(plan, tree)
        except Exception as exc:  # noqa: BLE001 - the files are already renamed; report it
            outcome.warnings.append(f"No se pudo actualizar la base de la app: {exc}")
        self._store_account(outcome, plan)
        return outcome

    def _stage(self, plan: AccountPlan, outcome: AccountResult) -> None:
        staging = StagingService(self.conn, root=self.fs.root)
        destination = staging.staging_path(plan.staging_rel)
        free = shutil.disk_usage(staging.staging_root()).free if os.path.isdir(staging.staging_root()) else None
        size = sum(os.path.getsize(os.path.join(c, n)) for c, _d, names in os.walk(plan.manual_path) for n in names)
        if free is not None and size > free:
            outcome.status, outcome.detail = "ERROR", "No hay espacio suficiente en el almacen"
            return
        moved = move_folder_to(plan.manual_path, destination)
        if moved.status == FAILED:
            outcome.status = "MOVE_CONFLICT"
            outcome.detail = moved.detail + (": " + ", ".join(moved.conflicts[:5]) if moved.conflicts else "")
            return
        outcome.staged, outcome.status = True, "STAGED"
        outcome.detail = "En el almacen, pendiente de volcar a la biblioteca"

    def _index_renamed(self, plan: AccountPlan, tree: TreeResult) -> None:
        """Write-through: the files just renamed enter the index so the next rename sees them."""

        entries = []
        for action in tree.actions:
            if action.kind != "RENAME":
                continue
            folder = os.path.relpath(os.path.dirname(action.new), plan.manual_path)
            entries.append(("" if folder == "." else folder, os.path.basename(action.new)))
        write_through(self.conn, int(plan.account_id), entries)

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
    def _record_in_bdapp(self, plan: AccountPlan, outcome: AccountResult) -> int | None:
        account_id = plan.account_id
        if plan.status == NEW_ACCOUNT and plan.spec is not None:
            account_id = self._register_new(plan, outcome)
        if account_id is not None and outcome.staged:
            StagingService(self.conn, root=self.fs.root).record(
                account_id, plan.staging_rel, plan.target_rel, getattr(self, "_run_id", None)
            )
        if account_id is not None and outcome.moved:
            try:
                LibraryScanner(self.conn, root=self.fs.root).scan(ACCOUNT, account_id=account_id)
            except Exception as exc:  # noqa: BLE001 - a scan in progress or an offline disk must not fail the rename
                outcome.warnings.append(f"Contadores no actualizados ({exc}); usa Sincronizar")
        return account_id

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
        elif not outcome.staged:
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

    def _store_account(self, outcome: AccountResult, plan: AccountPlan | None = None) -> None:
        spec = plan.spec if plan is not None and outcome.pending else None
        self.conn.execute(
            "INSERT INTO rename_run_accounts (rename_run_id, username, status, renamed, duplicated, moved, detail,"
            " manual_path, destination, account_id, spec, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (self._run_id, outcome.username, outcome.status, outcome.renamed, outcome.duplicated,
             int(outcome.moved), outcome.detail or "; ".join(outcome.warnings[:3]),
             plan.manual_path if outcome.pending and plan else None,
             plan.consult_folder if outcome.pending and plan else None,
             plan.account_id if plan else None,
             json.dumps(dataclasses.asdict(spec)) if spec is not None else None),
        )
        self.conn.commit()

    # ------------------------------------------------------- pending moves
    def pending_moves(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM rename_run_accounts WHERE status = ? AND COALESCE(resolved, 0) = 0 ORDER BY id", (PENDING_MOVE,)
        ).fetchall()

    def move_pending(self, progress: ProgressCallback | None = None) -> list[AccountResult]:
        """Move the folders renamed while the library was offline; register new accounts afterwards."""

        rows = self.pending_moves()
        if rows and not self._library_online():
            raise ValueError("La biblioteca no esta disponible: conecta la unidad e intentalo de nuevo")
        results = []
        for index, row in enumerate(rows, start=1):
            if progress is not None:
                progress(index, len(rows), row["username"])
            results.append(self._move_one_pending(row))
        return results

    def _move_one_pending(self, row: sqlite3.Row) -> AccountResult:
        manual, destination = str(row["manual_path"] or ""), str(row["destination"] or "")
        spec = NewAccountSpec(**json.loads(row["spec"])) if row["spec"] else None
        outcome = AccountResult(row["username"], NEW_ACCOUNT if spec else RENAMED)
        if not os.path.isdir(manual):
            outcome.status, outcome.detail = "SKIPPED", "La carpeta renombrada ya no esta en su sitio"
            self._resolve_pending(row, "SKIPPED", False, outcome.detail)
            return outcome
        moved = move_renamed_folder(manual, destination)
        outcome.moved = moved.status == MOVED
        if not outcome.moved:
            outcome.status = "MOVE_CONFLICT"
            outcome.detail = moved.detail + (": " + ", ".join(moved.conflicts[:5]) if moved.conflicts else "")
            return outcome
        plan = AccountPlan(row["username"], row["username"], manual, destination, outcome.status, spec=spec,
                           account_id=row["account_id"])
        try:
            self._record_in_bdapp(plan, outcome)
        except Exception as exc:  # noqa: BLE001 - already moved; report
            outcome.warnings.append(f"No se pudo actualizar la base de la app: {exc}")
        self._resolve_pending(row, outcome.status, True, outcome.detail)
        return outcome

    def _resolve_pending(self, row: sqlite3.Row, status: str, moved: bool, detail: str) -> None:
        self.conn.execute(
            "UPDATE rename_run_accounts SET status = ?, moved = ?, resolved = 1, detail = ? WHERE id = ?",
            (status, int(moved), detail, row["id"]),
        )
        self.conn.commit()

    def _finish_run(self, result: RenameResult) -> None:
        status = "CANCELLED" if result.cancelled else ("OK" if result.ok else "WITH_PROBLEMS")
        self.conn.execute("UPDATE rename_runs SET status = ?, finished_at = ? WHERE id = ?", (status, _now(), self._run_id))
        self.conn.commit()
