"""Settings tab «Ejecución»: every ``run.*`` key of the download process.

Values are validated before saving (``RunSettingSpec.parse``) and stored in
``app_settings``; the run child process reads them at start, so changes apply
to the next execution. Precedence: this tab > ``.env`` > built-in default.
"""

from __future__ import annotations

import tkinter as tk
from sqlite3 import Connection
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.theme import Tooltip
from ig_orchestrator.orchestration.run_settings import (
    GROUPS,
    KIND_BOOL,
    KIND_CHOICE,
    KIND_INT,
    KIND_PATH,
    RUN_SETTING_SPECS,
    RunSettingSpec,
    load_run_settings,
    reset_run_settings,
    save_run_settings,
)
from ig_orchestrator.settings import Settings


class RunSettingsTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, connection: Connection, env_settings: Settings):
        super().__init__(parent, padding=8)
        self.connection = connection
        self.env_settings = env_settings
        self.variables: dict[str, tk.Variable] = {}

        canvas = tk.Canvas(self, highlightthickness=0, height=380)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)
        self.body.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._wheel(canvas)

        self._build_rows()
        footer = ttk.Frame(self)
        ttk.Button(
            footer, text=t("run.reset"), command=self._on_reset
        ).pack(side=tk.LEFT)
        ttk.Label(footer, text=t("run.apply_note"), wraplength=420).pack(
            side=tk.LEFT, padx=8
        )
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0), before=canvas)

    # -- construction ----------------------------------------------------
    def _wheel(self, canvas: tk.Canvas) -> None:
        def on_wheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        self.body.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", on_wheel))
        self.body.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    def _build_rows(self) -> None:
        current = load_run_settings(self.connection, self.env_settings)
        row = 0
        for group in GROUPS:
            specs = [spec for spec in RUN_SETTING_SPECS if spec.group == group]
            frame = ttk.LabelFrame(self.body, text=t(f"run.group.{group}"), padding=8)
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 8), padx=(0, 8))
            row += 1
            for index, spec in enumerate(specs):
                self._build_spec_row(frame, index, spec, getattr(current, spec.field))
        self.body.columnconfigure(0, weight=1)

    def _build_spec_row(
        self, frame: ttk.Frame, index: int, spec: RunSettingSpec, value: object
    ) -> None:
        label = ttk.Label(frame, text=t(f"run.{spec.field}"))
        label.grid(row=index, column=0, sticky="w", pady=2)
        text = spec.format(value)
        if spec.kind == KIND_BOOL:
            variable: tk.Variable = tk.BooleanVar(value=bool(value))
            widget: tk.Widget = ttk.Checkbutton(frame, variable=variable)
        elif spec.kind == KIND_CHOICE:
            variable = tk.StringVar(value=text)
            widget = ttk.Combobox(
                frame, textvariable=variable, values=spec.choices, state="readonly", width=12
            )
        elif spec.kind == KIND_PATH:
            variable = tk.StringVar(value=text)
            widget = ttk.Frame(frame)
            ttk.Entry(widget, textvariable=variable, width=30).pack(side=tk.LEFT)
            ttk.Button(
                widget,
                text="…",
                width=3,
                command=lambda v=variable: self._browse(v),
            ).pack(side=tk.LEFT, padx=(2, 0))
        else:
            variable = tk.StringVar(value=text)
            widget = ttk.Spinbox(
                frame,
                textvariable=variable,
                from_=spec.minimum if spec.minimum is not None else 0,
                to=spec.maximum if spec.maximum is not None else 100000,
                width=8,
            )
        widget.grid(row=index, column=1, sticky="w", padx=(12, 0), pady=2)
        self.variables[spec.key] = variable
        help_text = t(f"run.{spec.field}.help")
        Tooltip(label, help_text)
        Tooltip(widget, help_text)

    def _browse(self, variable: tk.Variable) -> None:
        folder = filedialog.askdirectory(parent=self)
        if folder:
            variable.set(folder)

    # -- actions ---------------------------------------------------------
    def collect(self) -> dict[str, str]:
        collected: dict[str, str] = {}
        for spec in RUN_SETTING_SPECS:
            variable = self.variables[spec.key]
            if spec.kind == KIND_BOOL:
                collected[spec.key] = "1" if variable.get() else "0"
            else:
                collected[spec.key] = str(variable.get()).strip()
        return collected

    def validate(self) -> tuple[RunSettingSpec, str] | None:
        """Return (spec, reason) of the first invalid value, or None."""

        for key, text in self.collect().items():
            spec = next(s for s in RUN_SETTING_SPECS if s.key == key)
            try:
                spec.parse(text)
            except ValueError as exc:
                return spec, str(exc)
        return None

    def save(self) -> bool:
        """Validate and persist; shows the problem and returns False if invalid."""

        problem = self.validate()
        if problem is not None:
            spec, reason = problem
            messagebox.showerror(
                t("settings.title"),
                t("run.invalid", name=t(f"run.{spec.field}"), reason=reason),
                parent=self,
            )
            return False
        save_run_settings(self.connection, self.collect(), self.env_settings)
        return True

    def _on_reset(self) -> None:
        if not messagebox.askyesno(
            t("run.reset"), t("run.reset_confirm"), parent=self
        ):
            return
        reset_run_settings(self.connection)
        loaded = load_run_settings(self.connection, self.env_settings)
        for spec in RUN_SETTING_SPECS:
            value = getattr(loaded, spec.field)
            variable = self.variables[spec.key]
            if spec.kind == KIND_BOOL:
                variable.set(bool(value))
            else:
                variable.set(spec.format(value))


__all__ = ["RunSettingsTab"]
