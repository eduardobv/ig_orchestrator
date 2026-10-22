"""Advanced catalog actions: account card, multi-select move, drag and drop, trash."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.folder_picker import pick_folder
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.gui.text_edit import bind_edit_context_menu
from ig_orchestrator.library.account_card import card_summary_text, load_card, save_card, validate_card
from ig_orchestrator.library.fsops import FsOpsError
from ig_orchestrator.library.trash import CONFIRM_WORD, TrashError, TrashService

DRAG_THRESHOLD = 6


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


class CatalogAdvancedMixin:
    # ---------------------------------------------------------- selection
    def _selected_catalog_usernames(self) -> list[str]:
        tree = getattr(self, "catalog_tree", None)
        if getattr(self, "catalog_view_mode", "list") == "tree" and tree is not None:
            return [str(i)[5:] for i in tree.selection() if str(i).startswith("user:")]
        username = self._selected_catalog_username()
        return [username] if username else []

    def _selected_catalog_account_ids(self) -> list[int]:
        ids = []
        for username in self._selected_catalog_usernames():
            row = self.connection.execute(
                "SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
            if row is not None:
                ids.append(int(row[0]))
        return ids

    # ---------------------------------------------------------------- card
    def _card_abs_path(self, rel_path: str) -> str:
        if not rel_path:
            return ""
        try:
            return self._fsops_service().abs(rel_path)
        except FsOpsError:
            return rel_path

    def _catalog_edit_card(self) -> None:
        ids = self._selected_catalog_account_ids()
        if not ids:
            return
        card = load_card(self.connection, ids[0])
        abs_path = self._card_abs_path(card.rel_path)
        window = tk.Toplevel(self.root)
        window.title(t("card.title", username=card.username))
        window.transient(self.root)
        window.geometry("720x660")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        username_var = tk.StringVar(value=card.username)
        owner_var = tk.StringVar(value=card.instagram_user_id)
        date_var = tk.StringVar(value=card.start_init_date)
        fav_var = tk.BooleanVar(value=card.is_favorite)
        private_var = tk.BooleanVar(value=card.is_private)
        message = tk.StringVar()

        def copy_text(value: str) -> None:
            window.clipboard_clear()
            window.clipboard_append(value)
            self._set_status(t("card.copied", value=value[:60]))

        def field(row: int, label: str, var: tk.StringVar, *, readonly: bool = False, pady=(2, 2)) -> ttk.Entry:
            """Label + selectable entry + copy button."""

            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=pady)
            entry = ttk.Entry(frame, textvariable=var, state="readonly" if readonly else "normal")
            entry.grid(row=row, column=1, sticky="ew", pady=pady)
            bind_edit_context_menu(entry)
            ttk.Button(frame, text=t("card.copy"), width=8, command=lambda: copy_text(var.get())).grid(
                row=row, column=2, padx=(6, 0), pady=pady
            )
            return entry

        field(0, t("card.username"), username_var)
        field(1, t("card.owner"), owner_var)
        ttk.Label(frame, text=t("card.owner_help"), wraplength=640, foreground="#666666").grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        field(3, t("card.start_date"), date_var, pady=(8, 2))
        flags = ttk.Frame(frame)
        flags.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(flags, text=t("card.favorite"), variable=fav_var).pack(side=tk.LEFT)
        ttk.Checkbutton(flags, text=t("card.private"), variable=private_var).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Label(frame, text=t("card.notes")).grid(row=5, column=0, sticky="nw")
        notes = tk.Text(frame, height=4, wrap="word")
        notes.insert("1.0", card.notes)
        notes.grid(row=5, column=1, columnspan=2, sticky="ew", pady=2)
        bind_edit_context_menu(notes)
        field(6, t("card.full_path"), tk.StringVar(value=abs_path or "-"), readonly=True, pady=(8, 2))
        info = [
            (t("card.info.status"), card.status),
            (t("card.info.rel_path"), card.rel_path or "-"),
            (t("card.info.disk"), card.disk_state),
            (t("card.info.counts"), f"{card.posts} / {card.reels} / {card.stories} / {card.highlights}"),
            (t("card.info.last"), card.last_media_at or "-"),
            (t("card.info.names"), ", ".join(card.previous_names) or "-"),
            (t("card.info.batches"), ", ".join(card.batches) or "-"),
        ]
        for row, (label, value) in enumerate(info, start=7):
            field(row, label, tk.StringVar(value=value), readonly=True)
        ttk.Label(frame, text=t("card.info.ops")).grid(row=14, column=0, sticky="nw", pady=1)
        ops = tk.Text(frame, height=4, wrap="word")
        ops.insert("1.0", "\n".join(card.operations) or "-")
        ops.configure(state="disabled")  # read-only but selectable/copyable
        ops.grid(row=14, column=1, columnspan=2, sticky="ew", pady=1)
        bind_edit_context_menu(ops)
        ttk.Label(frame, textvariable=message, wraplength=680, foreground="#aa3300").grid(
            row=15, column=0, columnspan=3, sticky="w", pady=6
        )

        def save() -> None:
            new_username = username_var.get().strip().lstrip("@")
            renamed = bool(new_username) and new_username != card.username
            if renamed and not self._fsops_guard():
                return
            issues = validate_card(self.connection, card.id, owner_var.get(), date_var.get())
            if any(i.blocking for i in issues):
                message.set("\n".join(i.message for i in issues if i.blocking))
                return
            warnings = [i.message for i in issues]
            if warnings and not messagebox.askyesno(t("card.title", username=card.username), "\n".join(warnings) + "\n\n" + t("card.save_anyway"), parent=window):
                return
            save_card(self.connection, card.id, owner_id=owner_var.get(), start_date=date_var.get(),
                      notes=notes.get("1.0", tk.END), favorite=fav_var.get(), private=private_var.get())
            self._after_fsops_change()
            window.destroy()
            if renamed:
                self._rename_account_flow(card.id, new_username)

        buttons = ttk.Frame(frame)
        buttons.grid(row=16, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text=t("card.copy_all"), command=lambda: copy_text(card_summary_text(card, abs_path))).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text=t("card.save"), command=save).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)

    # ----------------------------------------------------- folder helpers
    def _catalog_open_folder(self) -> None:
        ids = self._selected_catalog_account_ids()
        if not ids:
            return
        row = self.connection.execute("SELECT rel_path FROM catalog_accounts WHERE id = ?", (ids[0],)).fetchone()
        if not row or not row[0]:
            messagebox.showinfo(t("plan.title"), t("card.no_path"), parent=self.root)
            return
        path = self._fsops_service().abs(str(row[0]))
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606 - Windows only app
        else:
            messagebox.showinfo(t("plan.title"), t("fsops.offline"), parent=self.root)

    def _catalog_copy_path(self) -> None:
        ids = self._selected_catalog_account_ids()
        if not ids:
            return
        service = self._fsops_service()
        paths = []
        for account_id in ids:
            row = self.connection.execute("SELECT rel_path FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()
            if row and row[0]:
                paths.append(service.abs(str(row[0])))
        if paths:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(paths))
            self._set_status(t("card.path_copied", count=len(paths)))

    # ---------------------------------------------------------- moving
    def _catalog_move_selected(self) -> None:
        ids = self._selected_catalog_account_ids()
        if not ids or not self._fsops_guard():
            return
        dest = pick_folder(self.root, self.connection, t("fsops.move_to"), account_ids=ids)
        if dest is None:
            return
        self._plan_and_run(lambda s: s.plan_move_accounts(ids, dest))

    def _setup_catalog_drag_and_drop(self) -> None:
        tree = self.catalog_tree
        state = {"items": [], "start": (0, 0), "moving": False, "row": ""}

        def on_press(event) -> str | None:
            row = tree.identify_row(event.y)
            state.update(items=[], start=(event.x, event.y), moving=False, row=row)
            if not row:
                return None
            selected = list(tree.selection())
            plain_click = not (event.state & 0x0001 or event.state & 0x0004)  # no Shift / Ctrl
            if plain_click and row in selected and len(selected) > 1:
                state["items"] = selected
                return "break"  # keep the multi-selection while the user may drag it
            state["items"] = [row] if plain_click else []
            return None

        def on_motion(event) -> None:
            if not state["items"]:
                return
            if abs(event.x - state["start"][0]) + abs(event.y - state["start"][1]) > DRAG_THRESHOLD:
                state["moving"] = True
                tree.configure(cursor="hand2")

        def on_release(event) -> str | None:
            tree.configure(cursor="")
            items, moving = state["items"], state["moving"]
            state.update(items=[], moving=False)
            if not items:
                return None
            if not moving:
                if len(items) > 1:
                    tree.selection_set(state["row"])
                return None
            target = tree.identify_row(event.y)
            if not target:
                return "break"
            self._drop_on_catalog_tree(items, target)
            return "break"

        def on_escape(_event) -> None:
            state.update(items=[], moving=False)
            tree.configure(cursor="")

        tree.bind("<ButtonPress-1>", on_press, add="+")
        tree.bind("<B1-Motion>", on_motion, add="+")
        tree.bind("<ButtonRelease-1>", on_release, add="+")
        tree.bind("<Escape>", on_escape, add="+")

    def _drop_on_catalog_tree(self, items: list[str], target: str) -> None:
        """Dropped ``items`` (tree iids) on ``target``: plan the move and ask for confirmation."""

        if target.startswith("user:"):  # dropping on an account means "next to it": use its folder
            parent = self.catalog_tree.parent(target)
            if not parent:
                return
            target = parent
        if not target.startswith("folder:"):
            return
        if not self._fsops_guard():
            return
        row = self.connection.execute(
            "SELECT id FROM catalog_folders WHERE lower(full_path) = lower(?)", (target[len("folder:"):],)
        ).fetchone()
        if row is None:
            return
        dest_id = int(row[0])
        accounts = []
        for iid in items:
            if iid.startswith("user:"):
                found = self.connection.execute("SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (iid[5:],)).fetchone()
                if found is not None:
                    accounts.append(int(found[0]))
        folders = [i for i in items if i.startswith("folder:")]
        if accounts and not folders:
            self._plan_and_run(lambda s: s.plan_move_accounts(accounts, dest_id))
        elif len(folders) == 1 and not accounts:
            src = self.connection.execute(
                "SELECT id FROM catalog_folders WHERE lower(full_path) = lower(?)", (folders[0][len("folder:"):],)
            ).fetchone()
            if src is not None:
                self._plan_and_run(lambda s: s.plan_move_folder(int(src[0]), dest_id))
        else:
            messagebox.showinfo(t("plan.title"), t("dnd.mixed"), parent=self.root)

    # ----------------------------------------------------------- trash
    def _catalog_delete_to_trash(self) -> None:
        ids = self._selected_catalog_account_ids()
        if not ids or not self._fsops_guard():
            return
        trash = TrashService(self.connection)
        allowed, blocked = [], []
        for account_id in ids:
            reasons = trash.blockers(account_id)
            name = self.connection.execute("SELECT username FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()[0]
            (blocked if reasons else allowed).append((account_id, name, "; ".join(reasons)))
        text = t("trash.confirm", count=len(allowed), names=", ".join("@" + n for _i, n, _r in allowed[:10]))
        if blocked:
            text += "\n\n" + t("trash.blocked") + "\n" + "\n".join(f"@{n}: {r}" for _i, n, r in blocked[:10])
        if not allowed:
            messagebox.showwarning(t("trash.title"), text, parent=self.root)
            return
        if not messagebox.askyesno(t("trash.title"), text, parent=self.root):
            return
        done = 0
        for account_id, name, _reason in allowed:
            try:
                trash.quarantine(account_id)
                done += 1
            except (TrashError, OSError) as exc:
                self._write_console(f"@{name}: {exc}\n")
        self._write_console(t("trash.done", count=done) + "\n")
        self._after_fsops_change()

    def _open_trash_dialog(self) -> None:
        trash = TrashService(self.connection)
        window = tk.Toplevel(self.root)
        window.title(t("trash.title"))
        window.geometry("820x420")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        info = tk.StringVar()
        ttk.Label(frame, textvariable=info).pack(anchor="w")
        columns = ("files", "size", "date", "expires", "original")
        tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="extended")
        tree.heading("#0", text=t("staging.col.account"))
        tree.column("#0", width=160)
        for column, width in zip(columns, (70, 90, 140, 140, 300), strict=True):
            tree.heading(column, text=t(f"trash.col.{column}"))
            tree.column(column, width=width)
        tree.pack(fill=tk.BOTH, expand=True, pady=8)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            items = trash.list_items()
            for item in items:
                tree.insert("", tk.END, iid=str(item.id), text="@" + item.username,
                            values=(item.files, human_size(item.bytes), item.deleted_at[:16], item.expires_at[:10] or "-",
                                    item.original_rel))
            late = len(trash.expired())
            info.set(t("trash.info", count=len(items), size=human_size(sum(i.bytes for i in items)))
                     + (" · " + t("trash.expired", count=late) if late else ""))

        def restore() -> None:
            for iid in tree.selection():
                try:
                    trash.restore(int(iid))
                except (TrashError, OSError) as exc:
                    messagebox.showwarning(t("trash.title"), str(exc), parent=window)
            refresh()
            self._after_fsops_change()

        def purge(selected: bool, only_expired: bool = False) -> None:
            ids = [int(i) for i in tree.selection()] if selected else None
            if only_expired:
                ids = [i.id for i in trash.expired()]
                if not ids:
                    messagebox.showinfo(t("trash.title"), t("trash.no_expired"), parent=window)
                    return
            pool = [i for i in trash.list_items() if ids is None or i.id in ids]
            if not pool:
                return
            lines = "\n".join(f"@{i.username}: {i.files} ficheros, {human_size(i.bytes)}" for i in pool[:15])
            word = simpledialog.askstring(
                t("trash.title"), t("trash.purge_prompt", count=len(pool), files=sum(i.files for i in pool),
                                    size=human_size(sum(i.bytes for i in pool)), lines=lines, word=CONFIRM_WORD),
                parent=window)
            if word is None:
                return
            if word.strip() != CONFIRM_WORD:
                messagebox.showwarning(t("trash.title"), t("trash.type_word", word=CONFIRM_WORD), parent=window)
                return
            forget = messagebox.askyesno(t("trash.title"), t("trash.forget_catalog"), parent=window)
            account_ids = [i.account_id for i in pool]
            try:
                trash.purge(ids, word)
            except (TrashError, OSError) as exc:
                messagebox.showwarning(t("trash.title"), str(exc), parent=window)
                refresh()
                return
            if forget:
                removed, kept = trash.remove_from_catalog(account_ids)
                self._write_console(t("trash.removed", removed=removed, kept=len(kept)) + "\n")
                self._after_fsops_change()
            refresh()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=t("trash.restore"), command=restore).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("trash.purge_selected"), command=lambda: purge(True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=t("trash.purge_all"), command=lambda: purge(False)).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("trash.purge_expired"), command=lambda: purge(False, True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)
        refresh()


__all__ = ["CatalogAdvancedMixin", "FsOpsError"]
