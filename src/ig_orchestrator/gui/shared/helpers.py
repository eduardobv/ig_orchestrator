from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import os
from pathlib import Path
import re
from sqlite3 import Connection
import tkinter as tk
from tkinter import ttk
import webbrowser

from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.catalog.colors import colors_for_entry
from ig_orchestrator.gui.catalog.service import AccountCatalogEntry
from ig_orchestrator.gui.draft.models import AccountDraft, BatchDraft
from ig_orchestrator.gui.batches.resume import AccountRuntimeProgress
from ig_orchestrator.gui.run.process_runner import NewAccountRenameParameters
from ig_orchestrator.gui.shared.i18n import t
from ig_orchestrator.settings import Settings


_CATALOG_COLORS = {
    "favorite": "#d9ead3",
    "inactive": "#fff2cc",
    "in_batch": "#f5c08c",
    "today": "#fff59d",
    "disabled": "#f4cccc",
}

_BATCH_COLUMNS = (
    ("username", "Username"),
    ("urls", "URLs"),
    ("status", "Estado"),
    ("stories", "Stories"),
    ("start_date", "Start date"),
)

_ACCOUNT_PROGRESS_RE = re.compile(
    r"\[(?P<current>\d+)/(?P<total>\d+)\s*\|\s*(?P<percentage>\d+)%\]"
)
_ITEM_PROGRESS_RE = re.compile(
    r"\[GUI_ITEM_PROGRESS\]\s+(?P<username>[^:]+):\s+"
    r"(?P<percentage>\d+)%\s+\((?P<current>\d+)/(?P<total>\d+)\)"
    r"(?P<retry>\s+retry)?"
)


def _gui_setting(connection: Connection, key: str, default: str) -> str:
    if not is_gui_schema(connection):
        return default
    try:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    except Exception:
        return default
    if row is None or not str(row["value"]).strip():
        return default
    return str(row["value"])


async def _send_test_telegram(settings: Settings, target: str) -> None:
    from ig_orchestrator.telegram.notify_service import send_ephemeral_notification

    await send_ephemeral_notification(
        settings, "Instagram Orchestrator: prueba de notificación", target=target
    )


def _suggest_batch_name() -> str:
    return f"descargas_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"


def _catalog_entry_colors(
    entry: AccountCatalogEntry,
    *,
    in_batch: bool = False,
    today: bool = False,
    palette: dict[str, str] | None = None,
) -> dict[str, str]:
    return colors_for_entry(
        entry,
        palette or _CATALOG_COLORS,
        in_batch=in_batch,
        today=today,
    )


def _batch_mode_details(
    *,
    saved_batch_id: int | None,
    active_batch_id: int | None,
    batch_name: str,
) -> tuple[str, str, str, bool]:
    """Return explicit GUI labels for new, editable and already-started batches."""

    normalized_name = batch_name.strip() or "(sin nombre)"
    if saved_batch_id is not None:
        return (
            "Modo: EDITANDO LOTE REGISTRADO — "
            f"{normalized_name} (ID: {saved_batch_id})",
            "Actualizar lote",
            f"Ejecutar lote ID {saved_batch_id}",
            True,
        )
    if active_batch_id is not None:
        return (
            "Modo: LOTE YA INICIADO — "
            f"{normalized_name} (ID: {active_batch_id}). "
            "Pulsa «Nuevo lote» para registrar otro.",
            "Lote no editable",
            "Ejecución iniciada",
            False,
        )
    return (
        "Modo: NUEVO LOTE (sin registrar y sin ID)",
        "Registrar lote nuevo",
        "Ejecutar lote nuevo",
        True,
    )


def _window_mode_title(
    context: str,
    batch_name: str,
    history_readonly: bool,
    saved_batch_id: int | None,
    active_batch_id: int | None,
) -> str:
    name = batch_name.strip() or "-"
    if history_readonly:
        return t("mode.history", name=name, id=active_batch_id or "-")
    if saved_batch_id is not None:
        return t("mode.editing", name=name, id=saved_batch_id)
    if active_batch_id is not None:
        return t("mode.running", name=name, id=active_batch_id)
    return t("mode.new")


def _half_screen_geometry(screen_width: int, screen_height: int) -> str:
    width = max(860, screen_width // 2)
    height = max(680, screen_height - 80)
    return f"{width}x{height}+0+0"


def catalog_focus_username(
    query: str,
    filtered: list[AccountCatalogEntry],
    previous: str | None,
) -> str | None:
    """Username to highlight after filtering the catalog.

    An exact query match (case-insensitive) wins so the searched account is
    selected in tree view even when folder peers are also shown. A single
    remaining match is highlighted next. Otherwise the previous selection is
    kept if it is still visible.
    """
    materialized = list(filtered)
    normalized = query.strip().casefold()
    if normalized:
        for entry in materialized:
            if entry.username.casefold() == normalized:
                return entry.username
        if len(materialized) == 1:
            return materialized[0].username
    if previous is None:
        return None
    visible = {entry.username for entry in materialized}
    if previous in visible:
        return previous
    return None


def batch_username_matches_filter(username: str, query: str) -> bool:
    normalized = query.strip().casefold()
    return not normalized or normalized in username.strip().casefold()


def filter_batch_accounts(
    accounts: list[AccountDraft],
    query: str,
) -> list[tuple[int, AccountDraft]]:
    """Return ``(original_index, account)`` pairs matching *query* on username."""
    return [
        (index, account)
        for index, account in enumerate(accounts)
        if batch_username_matches_filter(account.username, query)
    ]


def stories_cell_text(download_stories: bool) -> str:
    return "✅" if download_stories else "❌"


def _username_heading_title(ascending: bool | None) -> str:
    if ascending is True:
        return "Username ▲"
    if ascending is False:
        return "Username ▼"
    return "Username"


def _sort_accounts_by_username(
    accounts: list[AccountDraft],
    *,
    ascending: bool,
) -> list[AccountDraft]:
    return sorted(
        accounts,
        key=lambda account: account.username.casefold(),
        reverse=not ascending,
    )


def _catalog_width_chars(usernames: Iterable[str]) -> int:
    """Return the initial catalog width in Tk character units."""
    return max(
        (len(str(username)) for username in usernames),
        default=len("Catalogo"),
    )


def _batch_column_samples(usernames: Iterable[str]) -> dict[str, str]:
    """Return the longest expected visible value for every batch column."""
    username_values = ["Username", *(str(username) for username in usernames)]
    longest_username = max(username_values, key=lambda value: (len(value), value))
    return {
        "username": longest_username,
        "urls": "9999",
        "status": "Completada 9999/9999",
        "stories": "Stories",
        "start_date": "0000-00-00",
    }


def _play_completion_sound(root: tk.Misc) -> None:
    """Play the native Windows completion sound, with Tk's bell as fallback."""
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
        return
    except (ImportError, OSError, RuntimeError):
        pass
    try:
        root.bell()
    except tk.TclError:
        pass


def _instagram_profile_url(username: str) -> str:
    normalized = username.strip().lstrip("@").strip()
    return f"https://www.instagram.com/{normalized}/"


def _open_chrome_tab(url: str) -> bool:
    try:
        chrome = webbrowser.get("chrome")
    except webbrowser.Error:
        return webbrowser.open_new_tab(url)
    return chrome.open_new_tab(url)


def _open_path_in_explorer(path: Path) -> None:
    """Open a local directory in the OS file manager (Explorer on Windows)."""
    target = Path(path)
    if not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {target}")
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    import subprocess

    subprocess.run(["xdg-open", str(target)], check=False)


def _set_ttk_enabled(widget: ttk.Widget, enabled: bool) -> None:
    """Change a ttk state without using unsupported configure options."""
    widget.state(("!disabled",) if enabled else ("disabled",))


def _timestamp_console_text(text: str, *, now: datetime | None = None) -> str:
    """Prefix every GUI console line with a local timestamp including milliseconds."""
    if not text:
        return ""
    current = now or datetime.now()
    timestamp = current.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return "".join(f"{timestamp} {line}" for line in text.splitlines(keepends=True))


def _latest_executed_batch_name(connection: Connection) -> str | None:
    row = connection.execute(
        """
        SELECT input_batches.batch_name
        FROM runs
        JOIN input_batches ON input_batches.id = runs.batch_id
        WHERE runs.batch_id IS NOT NULL
        ORDER BY runs.started_at DESC, runs.id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        return str(row[0])

    row = connection.execute(
        """
        SELECT batch_name
        FROM input_batches
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _draft_signature(draft: BatchDraft) -> tuple[object, ...]:
    return (
        draft.batch_name,
        draft.default_start_now_date,
        tuple(
            (
                account.username,
                account.download_stories,
                tuple(account.urls),
                account.start_now_date,
                account.is_new_account,
                account.is_catalog_update,
                account.owner_id,
                account.start_init_date,
                account.destination_path,
            )
            for account in draft.accounts
        ),
    )


def _new_account_rename_parameters(
    accounts: list[AccountDraft],
) -> tuple[NewAccountRenameParameters, ...]:
    return tuple(
        NewAccountRenameParameters(
            username=account.username,
            owner_id=account.owner_id,
            start_init_date=account.start_init_date,
            destination_path=account.destination_path,
        )
        for account in accounts
        if account.is_new_account
    )


def _account_display_status(
    account: AccountDraft,
    runtime: AccountRuntimeProgress | None,
) -> tuple[str, str]:
    if runtime is None:
        if account.is_new_account:
            return "Nueva", "pending"
        if account.is_catalog_update:
            return "Catálogo", "pending"
        if account.download_stories or account.urls:
            return "Preparada", "pending"
        return "Vacia", "failed"
    if runtime.status == "COMPLETED":
        return f"Completada {runtime.completed_items}/{runtime.total_items}", "completed"
    if runtime.status == "INCOMPLETE":
        return (
            f"Incompleta {runtime.completed_items}/{runtime.total_items}",
            "processing",
        )
    if runtime.retry_items:
        return f"Reintento ({runtime.retry_items})", "retry"
    if runtime.status == "PROCESSING":
        return f"En curso {runtime.completed_items}/{runtime.total_items}", "processing"
    if runtime.status == "FAILED" or (
        runtime.failed_items and not runtime.pending_items
    ):
        return f"Fallida ({runtime.failed_items})", "failed"
    return f"Pendiente ({runtime.pending_items})", "pending"


__all__ = [
    "_ACCOUNT_PROGRESS_RE",
    "_BATCH_COLUMNS",
    "_CATALOG_COLORS",
    "_ITEM_PROGRESS_RE",
    "_account_display_status",
    "_batch_column_samples",
    "_batch_mode_details",
    "_catalog_entry_colors",
    "_catalog_width_chars",
    "_draft_signature",
    "_gui_setting",
    "_half_screen_geometry",
    "_instagram_profile_url",
    "_latest_executed_batch_name",
    "_new_account_rename_parameters",
    "_open_chrome_tab",
    "_open_path_in_explorer",
    "_play_completion_sound",
    "_send_test_telegram",
    "_set_ttk_enabled",
    "_sort_accounts_by_username",
    "_suggest_batch_name",
    "_timestamp_console_text",
    "_username_heading_title",
    "_window_mode_title",
    "batch_username_matches_filter",
    "catalog_focus_username",
    "filter_batch_accounts",
    "stories_cell_text",
]
