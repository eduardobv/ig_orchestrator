"""Tests for v2.2.0 new helpers: classify_log_level and compute_toolbar_state."""

from __future__ import annotations

import pytest

from ig_orchestrator.gui.shared.helpers import (
    classify_log_level,
    compute_toolbar_state,
)


class TestClassifyLogLevel:
    """Tests for log level classification."""

    def test_warning_detection(self):
        """Classify WARNING level."""
        line = "2026-10-06 12:00:00.123 | WARNING  | Some message"
        assert classify_log_level(line) == "warning"

    def test_error_detection(self):
        """Classify ERROR level."""
        line = "2026-10-06 12:00:00.123 | ERROR    | Some error"
        assert classify_log_level(line) == "error"

    def test_critical_detection(self):
        """Classify CRITICAL level as error."""
        line = "2026-10-06 12:00:00.123 | CRITICAL | Fatal error"
        assert classify_log_level(line) == "error"

    def test_normal_detection(self):
        """Classify normal (no level marker) as normal."""
        line = "Some GUI message without level marker"
        assert classify_log_level(line) == "normal"

    def test_info_as_normal(self):
        """INFO level treated as normal."""
        line = "2026-10-06 12:00:00.123 | INFO     | Information"
        assert classify_log_level(line) == "normal"


class TestComputeToolbarState:
    """Tests for button state computation."""

    def test_history_readonly_all_disabled(self):
        """In history mode, all buttons disabled except Stories."""
        state = compute_toolbar_state(
            batch_accounts_count=5,
            is_running=False,
            batch_ready_for_rename=True,
            history_readonly=True,
        )
        assert state["save"] == "disabled"
        assert state["run"] == "disabled"
        assert state["rename"] == "disabled"
        assert state["rename_manual"] == "disabled"
        assert state["stories"] == "normal"

    def test_running_batch_controls_enabled(self):
        """During batch execution, pause/stop enabled, others disabled."""
        state = compute_toolbar_state(
            batch_accounts_count=5,
            is_running=True,
            batch_ready_for_rename=False,
            history_readonly=False,
        )
        assert state["pause"] == "normal"
        assert state["stop"] == "normal"
        assert state["save"] == "disabled"
        assert state["run"] == "disabled"
        assert state["rename"] == "disabled"
        assert state["stories"] == "normal"

    def test_no_accounts_save_run_disabled(self):
        """With no accounts, Save and Run are disabled."""
        state = compute_toolbar_state(
            batch_accounts_count=0,
            is_running=False,
            batch_ready_for_rename=False,
            history_readonly=False,
        )
        assert state["save"] == "disabled"
        assert state["run"] == "disabled"
        assert state["pause"] == "disabled"
        assert state["stop"] == "disabled"

    def test_with_accounts_save_run_enabled(self):
        """With ≥1 account, Save and Run are enabled."""
        state = compute_toolbar_state(
            batch_accounts_count=1,
            is_running=False,
            batch_ready_for_rename=False,
            history_readonly=False,
        )
        assert state["save"] == "normal"
        assert state["run"] == "normal"

    def test_ready_for_rename_enables_rename_buttons(self):
        """When batch_ready_for_rename=True, Rename buttons enabled."""
        state = compute_toolbar_state(
            batch_accounts_count=3,
            is_running=False,
            batch_ready_for_rename=True,
            history_readonly=False,
        )
        assert state["rename"] == "normal"
        assert state["rename_manual"] == "normal"

    def test_stories_always_enabled(self):
        """Stories button always enabled (all scenarios)."""
        scenarios = [
            (0, False, False, False),
            (1, True, False, False),
            (0, False, True, False),
            (0, False, False, True),
            (5, True, True, True),
        ]
        for batch_count, is_running, ready, readonly in scenarios:
            state = compute_toolbar_state(batch_count, is_running, ready, readonly)
            assert state["stories"] == "normal"
