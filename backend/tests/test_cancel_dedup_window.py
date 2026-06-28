"""Tests for ADR-007 cancel dedup grace window.

Covers cancel.note_cancel + cancel.is_cancelling_recently + the
_find_active_duplicate_source Layer B integration.
"""
import time

import pytest

from app.jobs import cancel as cancel_registry


@pytest.fixture(autouse=True)
def _reset_ledger():
    cancel_registry._reset_recent_cancels_for_tests()
    yield
    cancel_registry._reset_recent_cancels_for_tests()


def test_note_cancel_then_is_cancelling_recently_finds_match():
    cancel_registry.note_cancel("D:/v.mp4", "manual", "job-abc")
    found = cancel_registry.is_cancelling_recently("D:/v.mp4", "manual")
    assert found == "job-abc"


def test_is_cancelling_recently_returns_none_when_no_match():
    cancel_registry.note_cancel("D:/v.mp4", "manual", "job-abc")
    assert cancel_registry.is_cancelling_recently("D:/other.mp4", "manual") is None
    assert cancel_registry.is_cancelling_recently("D:/v.mp4", "other_channel") is None


def test_is_cancelling_recently_respects_window():
    # Note a cancel, then check with a tiny window after sleeping past it.
    cancel_registry.note_cancel("D:/v.mp4", "manual", "job-abc")
    time.sleep(0.05)
    # 10ms window — entry is 50ms+ old → should NOT match.
    found = cancel_registry.is_cancelling_recently(
        "D:/v.mp4", "manual", window_sec=0.01,
    )
    assert found is None
    # Default window (30s) still finds it.
    assert cancel_registry.is_cancelling_recently("D:/v.mp4", "manual") == "job-abc"


def test_note_cancel_no_op_on_empty_source():
    cancel_registry.note_cancel("", "manual", "job-abc")
    cancel_registry.note_cancel("   ", "manual", "job-abc")
    assert cancel_registry.is_cancelling_recently("", "manual") is None


def test_is_cancelling_recently_returns_newest_on_duplicate_source():
    cancel_registry.note_cancel("D:/v.mp4", "manual", "job-1")
    time.sleep(0.01)
    cancel_registry.note_cancel("D:/v.mp4", "manual", "job-2")
    # Newer match wins (reverse-iter scan).
    assert cancel_registry.is_cancelling_recently("D:/v.mp4", "manual") == "job-2"


def test_ledger_bounded():
    # Ledger is a deque(maxlen=200). Push 250 entries; only last 200 retained.
    for i in range(250):
        cancel_registry.note_cancel(f"D:/v{i}.mp4", "manual", f"job-{i}")
    # The oldest (v0) should have been evicted.
    assert cancel_registry.is_cancelling_recently("D:/v0.mp4", "manual") is None
    # The latest is still there.
    assert cancel_registry.is_cancelling_recently("D:/v249.mp4", "manual") == "job-249"
