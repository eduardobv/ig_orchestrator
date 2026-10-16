from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from ig_orchestrator.db import (
    AccountRepository,
    UrlJobRepository,
    connect,
    init_gui_database,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import (
    PauseAccountsError,
    activate_draft_batch,
    finish_batch,
    load_batch_draft,
)
from ig_orchestrator.gui.batches.manage import (
    BatchManageError,
    create_empty_draft_batch,
    delete_unstarted_batch,
    is_batch_unstarted,
    list_batch_accounts,
    list_draft_targets,
    rename_batch,
    restore_batch_to_draft,
)
from ig_orchestrator.gui.batches.pause import move_accounts_to_batch
from ig_orchestrator.models import AccountStatus, UrlJobStatus


def _conn(tmp_path: Path):
    db = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db)
    return connect(db)


def _batch(connection, name, users=("ana", "bea")):
    return save_batch_draft(
        BatchDraft(
            batch_name=name,
            default_start_now_date="2026-10-16",
            accounts=[
                AccountDraft(
                    username=u,
                    urls=[f"https://www.instagram.com/reel/{u}{n}/" for n in range(2)],
                    priority=3 if u == "ana" else 0,
                )
                for u in users
            ],
        ),
        connection,
    )


def _names(connection, batch_id):
    return [a.username for a in load_batch_draft(connection, batch_id).accounts]


def test_create_rename_and_list_accounts(tmp_path: Path) -> None:
    with _conn(tmp_path) as connection:
        empty = create_empty_draft_batch(connection, "  vacio ")
        assert list_batch_accounts(connection, empty) == []
        with pytest.raises(BatchManageError):
            create_empty_draft_batch(connection, "vacio")
        with pytest.raises(BatchManageError):
            create_empty_draft_batch(connection, "  ")

        full = _batch(connection, "lote")
        rows = list_batch_accounts(connection, full.batch.id)
        assert [(r.username, r.priority, r.url_count, r.download_stories, r.start_date) for r in rows] == [
            ("ana", 3, 2, False, "2026-10-16"),
            ("bea", 0, 2, False, "2026-10-16"),
        ]

        rename_batch(connection, full.batch.id, "lote_nuevo")
        assert load_batch_draft(connection, full.batch.id).batch_name == "lote_nuevo"
        with pytest.raises(BatchManageError):
            rename_batch(connection, full.batch.id, "vacio")
        assert list_draft_targets(connection, full.batch.id) == [(empty, "vacio")]


def test_move_between_drafts_can_empty_the_source_and_detects_clashes(tmp_path: Path) -> None:
    with _conn(tmp_path) as connection:
        a = _batch(connection, "a", ("ana", "bea"))
        b = _batch(connection, "b", ("cris",))
        c = _batch(connection, "c", ("ana",))

        moved = move_accounts_to_batch(
            connection,
            source_batch_id=a.batch.id,
            target_batch_id=b.batch.id,
            usernames=["ana", "bea"],
        )
        assert moved.url_count == 4
        assert _names(connection, a.batch.id) == []  # a draft may end up empty
        assert _names(connection, b.batch.id) == ["cris", "ana", "bea"]

        with pytest.raises(PauseAccountsError, match="ana"):
            move_accounts_to_batch(
                connection,
                source_batch_id=c.batch.id,
                target_batch_id=b.batch.id,
                usernames=["ana"],
            )
        assert _names(connection, c.batch.id) == ["ana"]
        with pytest.raises(PauseAccountsError):
            move_accounts_to_batch(
                connection,
                source_batch_id=b.batch.id,
                target_batch_id=b.batch.id,
                usernames=["ana"],
            )


def test_move_requires_draft_target_and_unstarted_accounts_from_a_running_batch(tmp_path: Path) -> None:
    with _conn(tmp_path) as connection:
        run = _batch(connection, "run", ("ana", "bea", "cris"))
        activate_draft_batch(connection, run.batch.id)
        saved = _batch(connection, "saved", ("dora",))
        other = _batch(connection, "other", ("eva",))
        activate_draft_batch(connection, other.batch.id)

        with pytest.raises(PauseAccountsError, match="GUARDADO"):
            move_accounts_to_batch(
                connection,
                source_batch_id=run.batch.id,
                target_batch_id=other.batch.id,
                usernames=["ana"],
            )
        accounts = {a.username: a for a in run.accounts}
        AccountRepository(connection).update_status(accounts["bea"].id, AccountStatus.PROCESSING)
        with pytest.raises(PauseAccountsError, match="bea"):
            move_accounts_to_batch(
                connection,
                source_batch_id=run.batch.id,
                target_batch_id=saved.batch.id,
                usernames=["bea"],
            )
        move_accounts_to_batch(
            connection,
            source_batch_id=run.batch.id,
            target_batch_id=saved.batch.id,
            usernames=["cris"],
        )
        assert _names(connection, saved.batch.id) == ["dora", "cris"]
        assert _names(connection, run.batch.id) == ["ana", "bea"]


def test_delete_empty_or_full_drafts_but_not_executed_batches(tmp_path: Path) -> None:
    with _conn(tmp_path) as connection:
        empty = create_empty_draft_batch(connection, "vacio")
        assert delete_unstarted_batch(connection, empty) == 0
        full = _batch(connection, "lleno")
        assert delete_unstarted_batch(connection, full.batch.id) == 2
        count = connection.execute(
            "SELECT (SELECT COUNT(*) FROM batches), (SELECT COUNT(*) FROM batch_urls),"
            " (SELECT COUNT(*) FROM batch_accounts)"
        ).fetchone()
        assert tuple(count) == (0, 0, 0)

        started = _batch(connection, "iniciado", ("ana",))
        activate_draft_batch(connection, started.batch.id)
        job = UrlJobRepository(connection).list_by_account(started.accounts[0].id)[0]
        UrlJobRepository(connection).update_status(job.id, UrlJobStatus.COMPLETED)
        with pytest.raises(BatchManageError):
            delete_unstarted_batch(connection, started.batch.id)
        assert _names(connection, started.batch.id) == ["ana"]


def test_restore_from_history_only_when_never_started(tmp_path: Path) -> None:
    with _conn(tmp_path) as connection:
        untouched = _batch(connection, "intacto", ("ana",))
        activate_draft_batch(connection, untouched.batch.id)
        finish_batch(connection, untouched.batch.id)  # closed without ever running
        assert is_batch_unstarted(connection, untouched.batch.id)

        restore_batch_to_draft(connection, untouched.batch.id)
        assert [t for t in list_draft_targets(connection, 0) if t[0] == untouched.batch.id]

        used = _batch(connection, "usado", ("bea",))
        activate_draft_batch(connection, used.batch.id)
        job = UrlJobRepository(connection).list_by_account(used.accounts[0].id)[0]
        UrlJobRepository(connection).update_status(job.id, UrlJobStatus.COMPLETED)
        finish_batch(connection, used.batch.id)
        assert not is_batch_unstarted(connection, used.batch.id)
        with pytest.raises(BatchManageError, match="inici"):
            restore_batch_to_draft(connection, used.batch.id)
        with pytest.raises(BatchManageError):
            restore_batch_to_draft(connection, untouched.batch.id)  # no longer COMPLETED


def test_batches_dialog_shows_the_accounts_of_the_selected_batch(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batches.dialog import BatchesDialogMixin

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    with _conn(tmp_path) as connection:
        batch = _batch(connection, "lote_a")
        calls: list[str] = []

        class App(BatchesDialogMixin):
            def __init__(self) -> None:
                self.root = root
                self.connection = connection
                self._batches_dialog = None
                self.process_runner = SimpleNamespace(is_running=lambda: False)
                self.saved_batch_id = None
                self.active_batch_id = None
                self.settings = None

            def _write_console(self, text: str) -> None:
                calls.append(text)

            def _update_pending_button_label(self) -> None:
                pass

            def _sync_editor_with_batches(self, changed, deleted) -> None:
                calls.append("sync")

        app = App()
        try:
            app._open_pending_batches()
            root.update()

            def walk(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from walk(child)

            trees = [w for w in walk(app._batches_dialog) if isinstance(w, ttk.Treeview)]
            active, detail = trees[0], trees[2]
            assert detail.cget("columns") == ("username", "prio", "urls", "stories", "start")
            active.selection_set(str(batch.batch.id))
            root.update()
            assert [detail.item(i, "values")[0] for i in detail.get_children()] == ["ana", "bea"]
            labels = {w.cget("text") for w in walk(app._batches_dialog) if isinstance(w, ttk.Button)}
            assert {"Editar", "Ejecutar", "Nuevo lote", "Borrar lote", "Mover cuentas a…"} <= labels
            assert not any("Pull" in text or "Traer" in text for text in labels)
            assert not any("cola" in text.lower() for text in labels)
        finally:
            root.destroy()
