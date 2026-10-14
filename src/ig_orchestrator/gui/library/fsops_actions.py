"""Mixin: catalog actions that change the library on disk (move / rename / new folder)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.folder_picker import pick_folder
from ig_orchestrator.gui.library.fsops_history_dialog import open_history
from ig_orchestrator.gui.library.plan_dialog import confirm_plan
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.trash import TrashService
from ig_orchestrator.library.compat_lite import lite_path_from_settings, mirror_to_lite
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError
from ig_orchestrator.library.fsops_plan import Plan


STATUS_TEXT = {"DELETE": "plan.status_deleted", "INACTIVATE": "plan.status_inactive", "ACTIVATE": "plan.status_active"}


class FsOpsActionsMixin:
    """Catalog folder/account actions backed by ``FsOperationService``."""

    # ----------------------------------------------------------- helpers
    def _fsops_service(self) -> FsOperationService:
        return FsOperationService(self.connection)

    def _fsops_online(self) -> bool:
        try:
            return self._fsops_service().is_online()
        except FsOpsError:
            return False

    def _selected_catalog_folder_id(self) -> int | None:
        tree = getattr(self, "catalog_tree", None)
        if tree is None or getattr(self, "catalog_view_mode", "list") != "tree":
            return None
        selection = tree.selection()
        if not selection or not str(selection[0]).startswith("folder:"):
            return None
        path = str(selection[0])[len("folder:"):]
        row = self.connection.execute(
            "SELECT id FROM catalog_folders WHERE lower(full_path) = lower(?)", (path,)
        ).fetchone()
        return int(row[0]) if row is not None else None

    def _selected_catalog_account_id(self) -> int | None:
        username = self._selected_catalog_username()
        if not username:
            return None
        row = self.connection.execute(
            "SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        return int(row[0]) if row is not None else None

    def _fsops_guard(self) -> bool:
        """True when disk actions can run; otherwise explains why."""

        if self.process_runner.is_running():
            messagebox.showinfo(t("plan.title"), t("fsops.busy_process"), parent=self.root)
            return False
        if not self._fsops_online():
            messagebox.showinfo(t("plan.title"), t("fsops.offline"), parent=self.root)
            return False
        return True

    def _run_plan(self, plan: Plan) -> None:
        lifecycle = AccountLifecycleService(self.connection)
        extra = [
            (t("plan.status_change"), "@" + name, t(STATUS_TEXT[kind]))
            for _id, name, kind in lifecycle.preview_status_changes(plan)
        ]
        if not confirm_plan(self.root, plan, extra_rows=extra or None):
            return
        try:
            group = self._fsops_service().execute(plan)
        except FsOpsError as exc:
            messagebox.showerror(t("plan.title"), str(exc), parent=self.root)
            return
        for message in lifecycle.sync_with_location(lifecycle.affected_accounts(group), group):
            self._write_console(message + "\n")
        self._write_console(f"{plan.title}: OK\n")
        self._set_status(plan.title)
        self._after_fsops_change()

    def _after_fsops_change(self) -> None:
        """Refresh the legacy lite mirror and the catalog after any disk operation."""

        self._mirror_lite_quietly()
        self.destination_paths = self.catalog_service.list_destination_paths()
        self._reload_catalog()
        self._refresh_editor_catalog_fields()

    def _refresh_editor_catalog_fields(self) -> None:
        """Re-read owner id / destination path of the editor account from the catalog.

        A disk operation may have changed its folder; without this the editor keeps the old path.
        """

        username = self.username_var.get().strip()
        if not username or self.new_account_var.get():
            return
        entry = self.catalog_service.find_entry(username)
        if entry is None:
            return
        if entry.owner_id:
            self.owner_id_var.set(entry.owner_id)
        self.destination_path_var.set(entry.destination_path or "")

    def _mirror_lite_quietly(self) -> None:
        try:
            lite = lite_path_from_settings(self.connection)
            if lite is not None:
                service = self._fsops_service()
                changed = mirror_to_lite(self.connection, lite, service.root)
                if changed:
                    self._write_console(f"accounts_lite actualizada ({changed} filas).\n")
        except Exception as exc:  # noqa: BLE001 - lite offline must not fail the operation
            self._write_console(f"accounts_lite pendiente de actualizar ({exc}).\n")

    # ----------------------------------------------------------- actions
    def _catalog_new_folder(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is None or not self._fsops_guard():
            return
        name = simpledialog.askstring(t("fsops.new_folder"), t("fsops.new_folder_name"), parent=self.root)
        if not name:
            return
        self._plan_and_run(lambda s: s.plan_mkdir(folder_id, name.strip()))

    def _catalog_rename_folder(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is None or not self._fsops_guard():
            return
        current = self._fsops_service().folder(folder_id).name
        name = simpledialog.askstring(
            t("fsops.rename_folder"), t("fsops.rename_folder_name"), initialvalue=current, parent=self.root
        )
        if not name:
            return
        self._plan_and_run(lambda s: s.plan_rename_folder(folder_id, name.strip()))

    def _catalog_delete_empty_folder(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is None or not self._fsops_guard():
            return
        self._plan_and_run(lambda s: s.plan_delete_empty_folder(folder_id))

    def _catalog_move_folder(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is None or not self._fsops_guard():
            return
        dest = pick_folder(self.root, self.connection, t("fsops.move_to"))
        if dest is None:
            return
        self._plan_and_run(lambda s: s.plan_move_folder(folder_id, dest))

    def _catalog_move_account(self) -> None:
        account_id = self._selected_catalog_account_id()
        if account_id is None or not self._fsops_guard():
            return
        dest = pick_folder(self.root, self.connection, t("fsops.move_to"))
        if dest is None:
            return
        self._plan_and_run(lambda s: s.plan_move_account(account_id, dest))

    def _plan_and_run(self, make_plan) -> None:
        try:
            plan = make_plan(self._fsops_service())
        except FsOpsError as exc:
            messagebox.showerror(t("plan.title"), str(exc), parent=self.root)
            return
        self._run_plan(plan)

    def _open_fsops_history(self) -> None:
        open_history(self)

    # ------------------------------------------------------------ startup
    def _fsops_startup(self) -> None:
        """Complete/revert interrupted operations and re-sync the lite mirror."""

        try:
            service = self._fsops_service()
            if not service.is_online():
                return
            messages = service.recover()
            if messages:
                self._write_console("Operaciones de disco recuperadas:\n" + "\n".join(messages) + "\n")
                messagebox.showinfo(t("plan.title"), "\n".join(messages), parent=self.root)
                self._reload_catalog()
            self._mirror_lite_quietly()
            late = TrashService(self.connection).expired()
            if late:
                self._write_console(t("trash.expired_hint", count=len(late)) + "\n")
            self._refresh_staging_hint()
        except Exception as exc:  # noqa: BLE001 - never block start-up
            self._write_console(f"Recuperacion de operaciones de disco: {exc}\n")

    # -------------------------------------------------------------- menus
    def _popup_folder_menu(self, event: tk.Event, row: str) -> None:
        self.catalog_tree.selection_set(row)
        menu = getattr(self, "catalog_folder_menu", None)
        if menu is None:
            menu = tk.Menu(self.root, tearoff=False)
            menu.add_command(label=t("fsops.new_folder"), command=self._catalog_new_folder)
            menu.add_command(label=t("fsops.rename_folder"), command=self._catalog_rename_folder)
            menu.add_command(label=t("fsops.move_to"), command=self._catalog_move_folder)
            menu.add_command(label=t("fsops.delete_empty"), command=self._catalog_delete_empty_folder)
            menu.add_separator()
            menu.add_command(label=t("scan.category"), command=self._sync_category)
            self.catalog_folder_menu = menu
        state = "normal" if self._fsops_online() else "disabled"
        for index in range(4):
            menu.entryconfigure(index, state=state)
        menu.tk_popup(event.x_root, event.y_root)
