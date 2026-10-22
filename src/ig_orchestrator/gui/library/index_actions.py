"""Menu actions of the file index and the renamed-but-not-moved folders."""

from __future__ import annotations

from tkinter import messagebox

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming import RenameService
from ig_orchestrator.renaming.consult import index_status, verify_index

MAX_LINES = 15


class IndexActionsMixin:
    def _move_pending_renamed(self) -> None:
        service = RenameService(self.connection)
        pending = service.pending_moves()
        if not pending:
            messagebox.showinfo(t("pending.title"), t("pending.none"), parent=self.root)
            return
        names = ", ".join("@" + row["username"] for row in pending[:MAX_LINES])
        if not messagebox.askyesno(t("pending.title"), t("pending.confirm", count=len(pending), names=names), parent=self.root):
            return
        try:
            results = service.move_pending()
        except ValueError as exc:
            messagebox.showwarning(t("pending.title"), str(exc), parent=self.root)
            return
        lines = [f"@{r.username}: {r.status}" + (f" - {r.detail}" if r.detail else "") for r in results]
        self._write_console("\n".join(lines) + "\n")
        self._reload_catalog()
        messagebox.showinfo(t("pending.title"), t("pending.done", moved=sum(r.moved for r in results), total=len(results)), parent=self.root)

    def _verify_account_index(self) -> None:
        account_id = self._selected_catalog_account_id()
        if account_id is None:
            messagebox.showinfo(t("index.title"), t("scan.select_account"), parent=self.root)
            return
        service = RenameService(self.connection)
        row = self.connection.execute("SELECT username, rel_path FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None or not row["rel_path"] or not service._library_online():  # noqa: SLF001
            messagebox.showwarning(t("index.title"), t("index.offline"), parent=self.root)
            return
        diff = verify_index(self.connection, account_id, service.fs.abs(str(row["rel_path"])))
        if not diff["added"] and not diff["removed"]:
            messagebox.showinfo(t("index.title"), t("index.ok", status=index_status(self.connection, account_id)), parent=self.root)
            return
        sample = "\n".join([*diff["added"][:MAX_LINES], *diff["removed"][:MAX_LINES]])
        if messagebox.askyesno(
            t("index.title"),
            t("index.differences", added=len(diff["added"]), removed=len(diff["removed"]), sample=sample),
            parent=self.root,
        ):
            LibraryScanner(self.connection, root=service.fs.root).scan(ACCOUNT, account_id=account_id, deep=True)
            self._reload_catalog()
