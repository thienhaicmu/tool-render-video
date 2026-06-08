"""Strategic-6 closure regression guard — Audit 2026-06-08 (Batch A V9-F5).

Pre-Strategic-6 the cancel pipeline split state across two layers:

  - Persistent (DB): the cancel route at lifecycle.py:563 writes
    ``status="cancelling"`` via update_job_progress. This row state
    survives server restarts.

  - In-process (memory): jobs/cancel.py owns a ``_EVENTS`` dict of
    threading.Event objects + a ``_PENDING`` set. This evaporates at
    process death.

When the server restarted with a job in 'cancelling':
  - The in-process Event was lost.
  - The recovery loop at manager.py:328 only handled
    ``status in ("queued", "running")``.
  - The job sat at 'cancelling' forever — the operator's cancel
    intent was visible in the DB but the system never finalised it.

Strategic-6 closes V9-F5 with two changes:

  1. ``_VALID_JOB_STATUSES`` (jobs_repo.py) gains 'cancelling'.
     Pre-Strategic-6 the route wrote it but it was missing from the
     contract set, generating a WARN log line on every cancel. The
     transient label is now legitimate.

  2. ``recover_pending_render_jobs`` (manager.py) finalises jobs
     left in 'cancelling' at startup to the terminal 'cancelled'
     state. The operator's intent persists across server restarts
     even though the in-process Event is gone.

This file pins both behaviours.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. _VALID_JOB_STATUSES contract — 'cancelling' is a legitimate label.
# ---------------------------------------------------------------------------


def test_cancelling_is_in_valid_job_statuses():
    """Pre-Strategic-6 the cancel route wrote ``status="cancelling"``
    but the string was absent from the contract set. Every cancel
    triggered ``_warn_unknown_value`` (jobs_repo.py:61). Adding the
    transient label to the set silences the warn AND documents the
    state as part of the lifecycle."""
    from app.db.jobs_repo import _VALID_JOB_STATUSES

    assert "cancelling" in _VALID_JOB_STATUSES, (
        "Strategic-6 regression — 'cancelling' was removed from "
        "_VALID_JOB_STATUSES. The cancel route writes this status; "
        "without it every cancel logs a WARN about an unknown "
        "status value AND the documented status enumeration "
        "diverges from runtime reality."
    )


def test_cancelled_is_still_in_valid_job_statuses():
    """Belt-and-suspenders: ensure the terminal 'cancelled' state
    survived the Strategic-6 edit. The transition is
    cancelling -> cancelled; losing the destination breaks the
    finalisation path even with cancelling in the set."""
    from app.db.jobs_repo import _VALID_JOB_STATUSES

    assert "cancelled" in _VALID_JOB_STATUSES


# ---------------------------------------------------------------------------
# 2. recover_pending_render_jobs — cancelling → cancelled.
# ---------------------------------------------------------------------------


def test_recovery_finalises_cancelling_jobs_to_cancelled():
    """The Strategic-6 behavioural core: a job that was left in
    'cancelling' state when the server died MUST be transitioned to
    'cancelled' on the next startup. The in-process cancel event is
    gone but the operator's intent (cancel) is preserved by reading
    the DB row's last-known status."""
    fake_jobs = [
        {
            "job_id": "job-cancelling-1",
            "kind": "render",
            "status": "cancelling",
            "stage": "rendering",
            "progress_percent": 42,
        },
    ]
    update_calls: list[dict] = []

    def _fake_update(job_id, stage, progress_percent, message, status=None):
        update_calls.append({
            "job_id": job_id,
            "stage": stage,
            "progress_percent": progress_percent,
            "message": message,
            "status": status,
        })

    with patch("app.db.jobs_repo.list_jobs", return_value=fake_jobs), \
         patch("app.db.jobs_repo.update_job_progress", side_effect=_fake_update):
        from app.jobs.manager import recover_pending_render_jobs
        recover_pending_render_jobs()

    # Exactly one update call, transitioning the cancelling job to
    # cancelled. The progress_percent is preserved (forensic value).
    assert len(update_calls) == 1
    call = update_calls[0]
    assert call["job_id"] == "job-cancelling-1"
    assert call["status"] == "cancelled"
    assert call["stage"] == "cancelled", (
        f"Strategic-6 regression — the cancelling -> cancelled "
        f"transition must also flip the stage label so the WS feed "
        f"and FE state machine settle on a terminal stage. Got "
        f"stage={call['stage']!r}."
    )
    assert call["progress_percent"] == 42, (
        "The progress_percent at the cancel moment is preserved so "
        "operators can see how far the render got before cancelling. "
        "Resetting to 0 would lose that forensic signal."
    )


def test_recovery_still_marks_queued_and_running_as_interrupted():
    """Defence-in-depth: the pre-existing queued/running →
    interrupted behaviour MUST survive the Strategic-6 edit. The two
    transitions live in the same loop body; an editor that wires the
    new branch incorrectly could break the old one."""
    fake_jobs = [
        {
            "job_id": "job-queued",
            "kind": "render",
            "status": "queued",
            "stage": "queued",
            "progress_percent": 0,
        },
        {
            "job_id": "job-running",
            "kind": "render",
            "status": "running",
            "stage": "rendering",
            "progress_percent": 60,
        },
    ]
    update_calls: list[dict] = []

    def _fake_update(job_id, stage, progress_percent, message, status=None):
        update_calls.append({
            "job_id": job_id,
            "stage": stage,
            "progress_percent": progress_percent,
            "message": message,
            "status": status,
        })

    with patch("app.db.jobs_repo.list_jobs", return_value=fake_jobs), \
         patch("app.db.jobs_repo.update_job_progress", side_effect=_fake_update):
        from app.jobs.manager import recover_pending_render_jobs
        recover_pending_render_jobs()

    statuses_by_job = {c["job_id"]: c["status"] for c in update_calls}
    assert statuses_by_job == {
        "job-queued":   "interrupted",
        "job-running":  "interrupted",
    }, f"Pre-existing recovery behaviour regressed: {statuses_by_job}"


def test_recovery_skips_terminal_states():
    """Jobs that already reached a terminal state (completed,
    completed_with_errors, failed, cancelled, interrupted) MUST NOT
    be touched. The recovery loop only finalises transient states."""
    fake_jobs = [
        {"job_id": "job-completed",            "kind": "render", "status": "completed",            "stage": "done"},
        {"job_id": "job-completed-with-errs",  "kind": "render", "status": "completed_with_errors", "stage": "done"},
        {"job_id": "job-failed",               "kind": "render", "status": "failed",                "stage": "failed"},
        {"job_id": "job-cancelled",            "kind": "render", "status": "cancelled",             "stage": "cancelled"},
        {"job_id": "job-interrupted",          "kind": "render", "status": "interrupted",           "stage": "rendering"},
    ]
    update_calls: list[dict] = []

    def _fake_update(job_id, stage, progress_percent, message, status=None):
        update_calls.append({"job_id": job_id, "status": status})

    with patch("app.db.jobs_repo.list_jobs", return_value=fake_jobs), \
         patch("app.db.jobs_repo.update_job_progress", side_effect=_fake_update):
        from app.jobs.manager import recover_pending_render_jobs
        recover_pending_render_jobs()

    assert update_calls == [], (
        f"Strategic-6 regression — recovery touched terminal jobs. "
        f"Updates seen: {update_calls}. Terminal states must stay "
        f"frozen on restart."
    )


def test_recovery_skips_non_render_non_download_kinds():
    """The recovery loop only handles jobs of kind in {render,
    download}. Other job kinds (if any are added in the future) MUST
    be skipped to avoid unintended terminal transitions."""
    fake_jobs = [
        {"job_id": "job-other-cancelling", "kind": "rumble_strip", "status": "cancelling"},
        {"job_id": "job-render-cancelling", "kind": "render", "status": "cancelling"},
    ]
    update_calls: list[str] = []

    def _fake_update(job_id, stage, progress_percent, message, status=None):
        update_calls.append(job_id)

    with patch("app.db.jobs_repo.list_jobs", return_value=fake_jobs), \
         patch("app.db.jobs_repo.update_job_progress", side_effect=_fake_update):
        from app.jobs.manager import recover_pending_render_jobs
        recover_pending_render_jobs()

    assert update_calls == ["job-render-cancelling"], (
        f"Strategic-6 regression — recovery touched a non-render/"
        f"non-download job. Calls: {update_calls}. Other kinds must "
        f"be skipped to avoid unintended terminal transitions."
    )


# ---------------------------------------------------------------------------
# 3. Idempotency — a second startup is safe.
# ---------------------------------------------------------------------------


def test_recovery_is_idempotent_on_second_run():
    """A job that recovery already transitioned (cancelling →
    cancelled) on the FIRST startup must not be touched again on a
    SECOND startup. The terminal state is sticky."""
    fake_jobs_after_first_recovery = [
        {
            "job_id": "job-just-cancelled",
            "kind": "render",
            "status": "cancelled",
            "stage": "cancelled",
            "progress_percent": 42,
        },
    ]
    update_calls: list[dict] = []

    def _fake_update(job_id, stage, progress_percent, message, status=None):
        update_calls.append({"job_id": job_id, "status": status})

    with patch("app.db.jobs_repo.list_jobs", return_value=fake_jobs_after_first_recovery), \
         patch("app.db.jobs_repo.update_job_progress", side_effect=_fake_update):
        from app.jobs.manager import recover_pending_render_jobs
        recover_pending_render_jobs()

    assert update_calls == [], (
        "Strategic-6 regression — recovery re-touched an already-"
        "cancelled job. Idempotency broken; double restart could "
        "spam the DB with redundant writes."
    )
