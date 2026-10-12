"""Mixin: mark accounts as deleted on Instagram / restore / suggestions / label 09.DELETED."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.delete_destination_dialog import choose_delete_plan
from ig_orchestrator.gui.library.plan_dialog import confirm_plan
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService, LifecyclePlan
from ig_orchestrator.library.fsops import FsOpsError


def parse_usernames(text: str) -> list[str]:
    """Usernames from free text (lines, commas, spaces; optional leading @)."""

    seen: dict[str, str] = {}
    for token in re.split(r"[\s,;]+", text):
        name = token.strip().lstrip("@")
        if name:
            seen.setdefault(name.casefold(), name)
    return list(seen.values())


class AccountLifecycleActionsMixin:
    def _lifecycle(self) -> AccountLifecycleService:
        return AccountLifecycleService(self.connection)

    def _accounts_by_username(self, usernames: list[str]) -> tuple[list[int], list[str]]:
        found, unknown = [], []
        for name in usernames:
            row = self.connection.execute(
                "SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (name,)
            ).fetchone()
            (found if row is not None else unknown).append(int(row[0]) if row is not None else name)
        return found, unknown

    # ------------------------------------------------------------ mark
    def _catalog_mark_deleted(self) -> None:
        username = self._selected_catalog_username()
        if not username:
            return
        self._mark_deleted_for([username])

    def _mark_deleted_for(self, usernames: list[str]) -> None:
        if not self._fsops_guard():
            return
        ids, unknown = self._accounts_by_username(usernames)
        if unknown:
            messagebox.showwarning(t("life.title"), t("life.unknown", names=", ".join(unknown[:15])), parent=self.root)
        if not ids:
            return
        service = self._lifecycle()
        lifecycle = choose_delete_plan(self.root, service, ids)
        if lifecycle is None:
            return
        try:
            service.execute_mark_deleted(lifecycle)
        except FsOpsError as exc:
            messagebox.showerror(t("life.title"), str(exc), parent=self.root)
            return
        self._write_console(f"{lifecycle.plan.title}: OK\n")
        self._set_status(lifecycle.plan.title)
        self._after_fsops_change()

    def _catalog_mark_many_deleted(self) -> None:
        window = tk.Toplevel(self.root)
        window.title(t("life.many_title"))
        window.geometry("420x360")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=t("life.many_hint")).pack(anchor="w")
        box = tk.Text(frame, height=12, wrap="word")
        box.pack(fill=tk.BOTH, expand=True, pady=6)

        def _go() -> None:
            names = parse_usernames(box.get("1.0", tk.END))
            window.destroy()
            if names:
                self._mark_deleted_for(names)

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text=t("life.preview"), command=_go).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)

    def _confirm_and_run_lifecycle(self, lp: LifecyclePlan, runner) -> None:
        status_only = [
            (t("life.status_only"), a.username, "DELETED") for a in lp.actions if a.dst_rel is None
        ]
        if not confirm_plan(self.root, lp.plan, extra_rows=status_only, can_execute=lp.can_execute):
            return
        try:
            runner(lp)
        except FsOpsError as exc:
            messagebox.showerror(t("life.title"), str(exc), parent=self.root)
            return
        self._write_console(f"{lp.plan.title}: OK\n")
        self._set_status(lp.plan.title)
        self._after_fsops_change()

    # ---------------------------------------------------------- restore
    def _catalog_restore_deleted(self) -> None:
        username = self._selected_catalog_username()
        if not username or not self._fsops_guard():
            return
        ids, _ = self._accounts_by_username([username])
        if not ids:
            return
        service = self._lifecycle()
        self._confirm_and_run_lifecycle(service.plan_restore(ids[0]), service.execute_restore)

    # ------------------------------------------------------ suggestions
    def _catalog_suggest_deleted(self) -> None:
        suggestions = self._lifecycle().suggest_deleted()
        if not suggestions:
            messagebox.showinfo(t("life.title"), t("life.no_suggestions"), parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(t("life.suggest_title"))
        window.geometry("480x440")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=t("life.suggest_hint"), wraplength=440, justify="left").pack(anchor="w")
        tree = ttk.Treeview(frame, columns=("user", "batches"), show="headings", selectmode="extended")
        tree.heading("user", text=t("life.col.user"))
        tree.heading("batches", text=t("life.col.batches"))
        tree.column("user", width=300)
        tree.column("batches", width=80, anchor="center")
        for _id, name, batches in suggestions:
            tree.insert("", tk.END, iid=name, values=(name, batches))
        tree.pack(fill=tk.BOTH, expand=True, pady=6)

        def _go() -> None:
            names = list(tree.selection())
            window.destroy()
            if names:
                self._mark_deleted_for(names)

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text=t("life.preview"), command=_go).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)

    # --------------------------------------------------------- label 09
    def _catalog_label_deleted(self) -> None:
        service = self._lifecycle()
        found = service.find_unlabeled_deleted()
        if not found:
            messagebox.showinfo(t("life.title"), t("life.label_none", folder=service.deleted_folder), parent=self.root)
            return
        names = ", ".join(str(r["username"]) for r in found[:12])
        more = f" (+{len(found) - 12})" if len(found) > 12 else ""
        if not messagebox.askyesno(
            t("life.title"),
            t("life.label_confirm", count=len(found), folder=service.deleted_folder, names=names + more),
            parent=self.root,
        ):
            return
        count = service.label_deleted([int(r["id"]) for r in found])
        self._write_console(f"{count} cuentas de {service.deleted_folder} etiquetadas como eliminadas.\n")
        self._after_fsops_change()

    # ------------------------------------------------- editor protection
    def _confirm_if_deleted(self, username: str) -> bool:
        """True when it is fine to continue (not deleted, or the user confirmed)."""

        row = self.connection.execute(
            "SELECT s.code FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
            " WHERE a.username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if row is None or row[0] != "DELETED":
            return True
        return messagebox.askyesno(t("life.title"), t("life.editor_confirm", user=username), parent=self.root)
