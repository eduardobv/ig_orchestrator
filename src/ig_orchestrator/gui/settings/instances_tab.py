"""Settings tab: registry of instances (pc1, inst1...) and their folders.

Unlike the other tabs, changes here are written immediately (each row is its
own save), so ``Guardar``/``Cancelar`` of the settings dialog do not affect them.
"""

from __future__ import annotations

from sqlite3 import Connection
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator import __version__
from ig_orchestrator.db.instances_repository import ROLES, Instance, InstanceRepository
from ig_orchestrator.exchange.compare import probe_path
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close


def format_free_space(free_bytes: int | None) -> str:
    if free_bytes is None:
        return "?"
    return f"{free_bytes / (1024 ** 3):.1f} GB"


class InstancesTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, connection: Connection) -> None:
        super().__init__(parent, padding=12)
        self._repo = InstanceRepository(connection)
        self._by_item: dict[str, Instance] = {}

        columns = ("name", "role", "local", "source")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8, selectmode="browse")
        for column, width in zip(columns, (110, 80, 60, 360), strict=True):
            self.tree.heading(column, text=t(f"settings.instances.col.{column}"))
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=5, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        for index, (key, command) in enumerate(
            (
                ("add", self._add),
                ("edit", self._edit),
                ("delete", self._delete),
                ("test", self._test),
            )
        ):
            ttk.Button(self, text=t(f"settings.instances.{key}"), command=command).grid(
                row=1, column=index, sticky="w", pady=(8, 0), padx=(0, 6)
            )
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, wraplength=520).grid(
            row=2, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._by_item.clear()
        for instance in self._repo.list():
            item = self.tree.insert(
                "",
                tk.END,
                values=(
                    instance.name,
                    instance.role,
                    t("settings.instances.yes") if instance.is_local else "",
                    instance.pull_source,
                ),
            )
            self._by_item[item] = instance

    def _selected(self) -> Instance | None:
        selection = self.tree.selection()
        return self._by_item.get(selection[0]) if selection else None

    def _add(self) -> None:
        self._open_form(None)

    def _edit(self) -> None:
        instance = self._selected()
        if instance is not None:
            self._open_form(instance)

    def _delete(self) -> None:
        instance = self._selected()
        if instance is None or instance.id is None:
            return
        if messagebox.askyesno(
            t("settings.instances.title"),
            t("settings.instances.confirm_delete", name=instance.name),
            parent=self,
        ):
            self._repo.delete(instance.id)
            self.refresh()

    def _test(self) -> None:
        instance = self._selected()
        if instance is None:
            return
        lines = []
        for label, path in (
            ("working_path", instance.working_path),
            ("exchange_path", instance.exchange_path),
        ):
            if not path:
                continue
            self.status.set(t("settings.instances.testing", path=path))
            self.update_idletasks()
            probe = probe_path(path)
            if probe.ok:
                state = t(
                    "settings.instances.probe_ok",
                    write=t("settings.instances.yes") if probe.writable else "no",
                    free=format_free_space(probe.free_bytes),
                )
            else:
                state = probe.error
            lines.append(f"{label}: {path} -> {state}")
        self.status.set("\n".join(lines) or t("settings.instances.no_paths"))

    def _open_form(self, instance: Instance | None) -> None:
        window = tk.Toplevel(self)
        window.title(t("settings.instances.title"))
        window.transient(self.winfo_toplevel())
        window.grab_set()
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        current = instance or Instance(None, "", "WORKER")
        name = tk.StringVar(value=current.name)
        role = tk.StringVar(value=current.role)
        local = tk.BooleanVar(value=current.is_local)
        path_vars = {
            "working_path": tk.StringVar(value=current.working_path),
            "exchange_path": tk.StringVar(value=current.exchange_path),
            "exchange_local_path": tk.StringVar(value=current.exchange_local_path),
        }
        notes = tk.StringVar(value=current.notes)

        ttk.Label(frame, text=t("settings.instances.col.name")).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=name).grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(frame, text=t("settings.instances.col.role")).grid(row=1, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=role, values=ROLES, state="readonly", width=12).grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Checkbutton(frame, text=t("settings.instances.is_local"), variable=local).grid(
            row=2, column=1, sticky="w"
        )
        for row, key in enumerate(path_vars, start=3):
            ttk.Label(frame, text=t(f"settings.instances.{key}")).grid(row=row, column=0, sticky="w")
            ttk.Entry(frame, textvariable=path_vars[key], width=58).grid(
                row=row, column=1, sticky="ew", pady=2, padx=(0, 6)
            )
            ttk.Button(
                frame,
                text=t("audit.browse"),
                command=lambda v=path_vars[key]: _browse_dir(window, v),
            ).grid(row=row, column=2)
        ttk.Label(frame, text=t("settings.instances.notes")).grid(row=6, column=0, sticky="w")
        ttk.Entry(frame, textvariable=notes).grid(row=6, column=1, columnspan=2, sticky="ew", pady=2)

        def _save() -> None:
            candidate = Instance(
                id=current.id,
                name=name.get(),
                role=role.get(),
                is_local=local.get(),
                working_path=_native(path_vars["working_path"].get()),
                exchange_path=_native(path_vars["exchange_path"].get()),
                exchange_local_path=_native(path_vars["exchange_local_path"].get()),
                app_version=__version__ if local.get() else current.app_version,
                last_seen_at=current.last_seen_at,
                notes=notes.get(),
            )
            try:
                self._repo.save(candidate)
            except ValueError as exc:
                messagebox.showerror(t("settings.instances.title"), str(exc), parent=window)
                return
            window.destroy()
            self.refresh()

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text=t("settings.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text=t("settings.save"), command=_save).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)


def _native(value: str) -> str:
    from ig_orchestrator.library.audit_cli import native_path_text

    text = value.strip()
    # Keep UNC prefixes intact; normpath preserves them on Windows.
    return native_path_text(text)


def _browse_dir(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askdirectory(parent=parent, initialdir=variable.get() or None)
    if chosen:
        variable.set(_native(chosen))
