"""Dialog to move dumped story files into each account's story folder."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.filesystem.story_inbox import (
    StoryInboxError,
    StoryInboxStatus,
    organize_story_inbox,
    summarize_results,
)
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.stories.settings import (
    load_story_inbox_settings,
    save_story_inbox_settings,
)
from ig_orchestrator.gui.text_edit import bind_edit_context_menu


class StoriesInboxMixin:
    """Mixin: Organizar stories dialog."""

    def _open_stories_inbox(self) -> None:
        existing = getattr(self, "_stories_inbox_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_set()
                    return
            except tk.TclError:
                self._stories_inbox_window = None

        inbox_saved, db_saved = load_story_inbox_settings(self.connection)
        window = tk.Toplevel(self.root)
        window.title(t("stories.title"))
        window.geometry("720x420")
        window.minsize(520, 320)
        self._stories_inbox_window = window

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        inbox_var = tk.StringVar(value=inbox_saved)
        db_var = tk.StringVar(value=db_saved)

        ttk.Label(frame, text=t("stories.inbox")).grid(row=0, column=0, sticky="w")
        inbox_entry = ttk.Entry(frame, textvariable=inbox_var)
        inbox_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        bind_edit_context_menu(inbox_entry)
        ttk.Button(
            frame,
            text=t("stories.browse"),
            command=lambda: _browse_directory(window, inbox_var),
        ).grid(row=0, column=2, sticky="e")

        ttk.Label(frame, text=t("stories.db")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        db_entry = ttk.Entry(frame, textvariable=db_var)
        db_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        bind_edit_context_menu(db_entry)
        ttk.Button(
            frame,
            text=t("stories.browse"),
            command=lambda: _browse_file(window, db_var),
        ).grid(row=1, column=2, sticky="e", pady=(8, 0))

        ttk.Label(frame, text=t("stories.log")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(12, 0)
        )
        log = tk.Text(frame, wrap="word", height=12, undo=False)
        log.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=log.yview)
        scroll.grid(row=3, column=3, sticky="ns", pady=(4, 0))
        log.configure(yscrollcommand=scroll.set)
        frame.rowconfigure(3, weight=1)

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(
            actions,
            text=t("stories.save"),
            command=lambda: self._save_stories_inbox_paths(inbox_var.get(), db_var.get()),
        ).pack(side=tk.LEFT)
        run_button = ttk.Button(actions, text=t("stories.run"))
        run_button.configure(
            command=lambda: self._run_stories_inbox(
                window, log, run_button, inbox_var.get(), db_var.get()
            )
        )
        run_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text=t("stories.close"), command=window.destroy).pack(
            side=tk.RIGHT
        )

        def _on_close() -> None:
            self._stories_inbox_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_close)

    def _save_stories_inbox_paths(self, inbox: str, accounts_db: str) -> None:
        save_story_inbox_settings(
            self.connection, inbox=inbox, accounts_db=accounts_db
        )
        self._set_status(t("stories.saved"))

    def _run_stories_inbox(
        self,
        window: tk.Toplevel,
        log: tk.Text,
        run_button: ttk.Button,
        inbox: str,
        accounts_db: str,
    ) -> None:
        inbox_path = inbox.strip()
        db_path = accounts_db.strip()
        if not inbox_path or not db_path:
            messagebox.showerror(t("stories.title"), t("stories.paths_required"), parent=window)
            return
        save_story_inbox_settings(
            self.connection, inbox=inbox_path, accounts_db=db_path
        )
        run_button.configure(state="disabled")
        window.update_idletasks()
        try:
            results = organize_story_inbox(
                inbox=Path(inbox_path),
                accounts_db=Path(db_path),
            )
        except StoryInboxError as exc:
            run_button.configure(state="normal")
            messagebox.showerror(t("stories.title"), str(exc), parent=window)
            return
        except Exception as exc:
            run_button.configure(state="normal")
            messagebox.showerror(t("stories.title"), str(exc), parent=window)
            return
        run_button.configure(state="normal")
        moved, errors = summarize_results(results)
        lines = [
            t("stories.summary", moved=moved, errors=errors, total=len(results)),
            "",
        ]
        for item in results:
            dest = str(item.destination) if item.destination is not None else "-"
            if item.status is StoryInboxStatus.MOVED:
                lines.append(f"MOVED  {item.source.name}  ->  {dest}")
            else:
                lines.append(
                    f"{item.status}  {item.source.name}  ({item.username or '-'})  {item.detail}"
                )
        body = "\n".join(lines) + "\n"
        log.configure(state="normal")
        log.delete("1.0", tk.END)
        log.insert("1.0", body)
        log.see(tk.END)
        log.configure(state="disabled")
        self._set_status(t("stories.summary", moved=moved, errors=errors, total=len(results)))
        self._write_console(body)


def _browse_directory(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askdirectory(parent=parent, initialdir=variable.get() or None)
    if chosen:
        variable.set(chosen)


def _browse_file(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askopenfilename(
        parent=parent,
        initialdir=str(Path(variable.get()).parent) if variable.get() else None,
        filetypes=[("SQLite", "*.sqlite *.db *.sqlite3"), ("All files", "*.*")],
    )
    if chosen:
        variable.set(chosen)
