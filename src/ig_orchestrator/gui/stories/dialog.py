"""Dialog to move dumped story files into each account's story folder.

After a run it shows only what matters: the total moved, the files with a
problem (duplicates, missing folder, unknown account…), what stayed in the
inbox, and a button to force-move duplicates (overwrite).
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.filesystem.story_inbox import (
    StoryInboxReport,
    StoryInboxResult,
    StoryInboxStatus,
    build_report,
    force_move_conflicts,
    organize_story_inbox,
)
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.gui.stories.settings import (
    load_story_inbox_settings,
    save_story_inbox_settings,
)
from ig_orchestrator.gui.text_edit import bind_edit_context_menu

_OK_COLOR = "#1b6e2e"
_WARN_COLOR = "#9a5b00"


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

        inbox_saved, _legacy_db = load_story_inbox_settings(self.connection)
        window = tk.Toplevel(self.root)
        window.title(t("stories.title"))
        window.geometry("820x560")
        window.minsize(620, 420)
        self._stories_inbox_window = window
        self._stories_last_report = None

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=3)
        frame.rowconfigure(5, weight=1)

        inbox_var = tk.StringVar(value=inbox_saved)

        ttk.Label(frame, text=t("stories.inbox")).grid(row=0, column=0, sticky="w")
        inbox_entry = ttk.Entry(frame, textvariable=inbox_var)
        inbox_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        bind_edit_context_menu(inbox_entry)
        ttk.Button(
            frame,
            text=t("stories.browse"),
            command=lambda: _browse_directory(window, inbox_var),
        ).grid(row=0, column=2, sticky="e")

        summary_var = tk.StringVar(value=t("stories.idle"))
        summary_label = tk.Label(
            frame, textvariable=summary_var, anchor="w", justify="left", padx=8, pady=6
        )
        summary_label.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(12, 0))

        ttk.Label(frame, text=t("stories.problems")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        columns = ("file", "user", "problem", "detail")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=7)
        for col, width in zip(columns, (230, 110, 170, 280)):
            tree.heading(col, text=t(f"stories.col.{col}"))
            tree.column(col, width=width, anchor="w")
        tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        tscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tscroll.grid(row=3, column=3, sticky="ns", pady=(4, 0))
        tree.configure(yscrollcommand=tscroll.set)

        ttk.Label(frame, text=t("stories.leftovers_title")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        left_box = tk.Text(frame, wrap="word", height=5, undo=False, state="disabled")
        left_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        lscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=left_box.yview)
        lscroll.grid(row=5, column=3, sticky="ns", pady=(4, 0))
        left_box.configure(yscrollcommand=lscroll.set)

        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(
            actions,
            text=t("stories.save"),
            command=lambda: self._save_stories_inbox_paths(inbox_var.get()),
        ).pack(side=tk.LEFT)
        run_button = ttk.Button(actions, text=t("stories.run"))
        run_button.pack(side=tk.LEFT, padx=(8, 0))
        force_button = ttk.Button(actions, text=t("stories.force"), state="disabled")
        force_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text=t("stories.close"), command=window.destroy).pack(
            side=tk.RIGHT
        )

        self._stories_widgets = {
            "summary_var": summary_var,
            "summary_label": summary_label,
            "tree": tree,
            "left_box": left_box,
            "force_button": force_button,
        }
        run_button.configure(
            command=lambda: self._run_stories_inbox(window, run_button, inbox_var.get())
        )
        force_button.configure(
            command=lambda: self._force_stories_inbox(window, inbox_var.get())
        )

        def _on_close() -> None:
            self._stories_inbox_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_close)
        bind_escape_close(window, on_close=_on_close)

    def _save_stories_inbox_paths(self, inbox: str) -> None:
        save_story_inbox_settings(self.connection, inbox=inbox)
        self._set_status(t("stories.saved"))

    def _run_stories_inbox(
        self,
        window: tk.Toplevel,
        run_button: ttk.Button,
        inbox: str,
    ) -> None:
        inbox_path = inbox.strip()
        if not inbox_path:
            messagebox.showerror(t("stories.title"), t("stories.paths_required"), parent=window)
            return
        save_story_inbox_settings(self.connection, inbox=inbox_path)
        run_button.configure(state="disabled")
        window.update_idletasks()
        try:
            results = organize_story_inbox(
                inbox=Path(inbox_path),
                app_connection=self.connection,
            )
        except Exception as exc:  # StoryInboxError and unexpected failures alike
            run_button.configure(state="normal")
            messagebox.showerror(t("stories.title"), str(exc), parent=window)
            return
        run_button.configure(state="normal")
        self._show_stories_report(build_report(inbox_path, results))

    def _force_stories_inbox(self, window: tk.Toplevel, inbox: str) -> None:
        previous: StoryInboxReport | None = getattr(self, "_stories_last_report", None)
        conflicts = list(previous.conflicts) if previous else []
        if not conflicts:
            return
        if not messagebox.askyesno(
            t("stories.title"), t("stories.force_confirm", count=len(conflicts)), parent=window
        ):
            return
        forced = force_move_conflicts(conflicts, app_connection=self.connection)
        # Problems that are not duplicates stay; the forced ones are replaced by their new result.
        kept = [p for p in previous.problems if p.status is not StoryInboxStatus.DESTINATION_EXISTS]
        fresh = build_report(inbox.strip(), forced)
        self._show_stories_report(
            StoryInboxReport(
                moved=previous.moved + fresh.moved,
                problems=tuple(kept) + fresh.problems,
                leftovers=fresh.leftovers,
            )
        )

    def _show_stories_report(self, report: StoryInboxReport) -> None:
        self._stories_last_report = report
        widgets = getattr(self, "_stories_widgets", None)
        if report.is_clean:
            text, color = t("stories.all_ok", moved=report.moved), _OK_COLOR
        else:
            text, color = (
                t(
                    "stories.partial",
                    moved=report.moved,
                    problems=len(report.problems),
                    left=len(report.leftovers),
                ),
                _WARN_COLOR,
            )
        if widgets is not None:
            try:
                widgets["summary_var"].set(text)
                widgets["summary_label"].configure(fg=color)
                tree = widgets["tree"]
                tree.delete(*tree.get_children())
                for item in report.problems:
                    tree.insert(
                        "",
                        tk.END,
                        values=(
                            item.source.name,
                            f"@{item.username}" if item.username else "-",
                            _problem_label(item),
                            item.detail,
                        ),
                    )
                box = widgets["left_box"]
                box.configure(state="normal")
                box.delete("1.0", tk.END)
                if report.leftovers:
                    box.insert(
                        "1.0",
                        t("stories.leftovers", count=len(report.leftovers))
                        + "\n"
                        + "\n".join(p.name for p in report.leftovers),
                    )
                else:
                    box.insert("1.0", t("stories.empty"))
                box.configure(state="disabled")
                widgets["force_button"].configure(
                    state="normal" if report.conflicts else "disabled"
                )
            except tk.TclError:
                pass  # the window was closed meanwhile
        self._set_status(text)
        self._write_console(
            text
            + "".join(f"\n  {p.status} {p.source.name} {p.detail}" for p in report.problems)
            + "\n"
        )


def _problem_label(item: StoryInboxResult) -> str:
    key = f"stories.status.{item.status.value}"
    label = t(key)
    return label if label != key else item.status.value


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
