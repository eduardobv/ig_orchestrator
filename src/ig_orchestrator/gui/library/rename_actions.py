"""Mixin: username changes (rename / merge), duplicated Instagram ids and old-name resolution."""

from __future__ import annotations

from tkinter import messagebox, simpledialog

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.owner_groups_dialog import open_owner_groups
from ig_orchestrator.gui.library.rename_dialog import confirm_rename
from ig_orchestrator.library.account_rename import AccountRenameService
from ig_orchestrator.library.compat_lite import lite_path_from_settings
from ig_orchestrator.library.fsops import FsOpsError
from ig_orchestrator.library.owner_groups import OwnerGroup


class AccountRenameActionsMixin:
    def _rename_service(self) -> AccountRenameService:
        return AccountRenameService(self.connection)

    # ----------------------------------------------------------- actions
    def _catalog_username_changed(self) -> None:
        username = self._selected_catalog_username()
        if not username or not self._fsops_guard():
            return
        row = self.connection.execute(
            "SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if row is None:
            return
        new_name = simpledialog.askstring(
            t("rename.title"), t("rename.ask_new", old=username), parent=self.root
        )
        if new_name:
            self._rename_account_flow(int(row[0]), new_name.strip().lstrip("@"))

    def _rename_account_flow(self, account_id: int, new_username: str) -> bool:
        service = self._rename_service()
        try:
            plan = confirm_rename(self.root, service, account_id, new_username)
        except FsOpsError as exc:
            messagebox.showerror(t("rename.title"), str(exc), parent=self.root)
            return False
        if plan is None:
            return False
        try:
            service.execute(plan, lite_path=lite_path_from_settings(self.connection))
        except FsOpsError as exc:
            messagebox.showerror(t("rename.title"), str(exc), parent=self.root)
            return False
        self._write_console(f"{plan.plan.title}: OK\n")
        self._set_status(plan.plan.title)
        self._after_account_rename(plan.old_username, plan.new_username)
        return True

    def _after_account_rename(self, old: str, new: str) -> None:
        """Refresh everything that showed the old name, without restarting the app."""

        for draft in getattr(self, "accounts", []):
            if draft.username.casefold() == old.casefold():
                draft.username = new
        if self.username_var.get().strip().casefold() == old.casefold():
            self.username_var.set(new)
        self._after_fsops_change()
        self._refresh_table()
        self._update_batch_context()

    def _open_owner_groups(self) -> None:
        open_owner_groups(self)

    def _resolve_owner_group(self, group: OwnerGroup, current_username: str) -> None:
        """Merge/rename every other member of the group into *current_username*."""

        if not self._fsops_guard():
            return
        for member in group.members:
            if member.username.casefold() == current_username.casefold():
                continue
            if not self._rename_account_flow(member.account_id, current_username):
                break

    # ----------------------------------------------------- editor aliases
    def _resolve_editor_alias(self, username: str) -> str | None:
        """Username to use in the editor: asks when *username* is an old name of an account.

        Returns ``None`` when the user cancels.
        """

        name = username.strip().lstrip("@")
        if not name or self.catalog_service.find_entry(name) is not None:
            return name
        matches = self._rename_service().resolve_alias(name)
        if not matches:
            return name
        if len(matches) > 1:
            messagebox.showwarning(
                t("rename.title"),
                t("rename.alias_ambiguous", old=name, names=", ".join(f"@{n}" for _i, n in matches)),
                parent=self.root,
            )
            return name
        current = matches[0][1]
        answer = messagebox.askyesnocancel(
            t("rename.title"), t("rename.alias_use", old=name, new=current), parent=self.root
        )
        if answer is None:
            return None
        return current if answer else name
