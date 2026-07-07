"""test_content_resume_keep.py — CM-4 preserve resumable job work dirs.

prune_render_temp_dirs removes TEMP_DIR/{job_id} for non-active jobs. CM-4 keeps
a resumable job's dir (status interrupted/paused) for a bounded window (by dir
mtime) so /resume can reuse its already-rendered scenes, while still pruning
finished/failed/orphan dirs and stale resumable ones. get_job is mocked so the
test never touches the DB.
"""
from __future__ import annotations

import os
import time
import uuid

import app.services.maintenance as maint


def _job_dir(root, status_map, status: str | None):
    """Create a UUID-named dir under root and register its status in status_map
    (None = orphan / not in DB). Returns the dir path."""
    jid = str(uuid.uuid4())
    d = root / jid
    d.mkdir()
    status_map[jid] = status
    return d


def _age_dir(d, hours: float):
    old = time.time() - hours * 3600
    os.utime(d, (old, old))


def _run(monkeypatch, root, status_map, **kwargs):
    monkeypatch.setattr(
        "app.db.jobs_repo.get_job",
        lambda jid: ({"status": status_map[jid]} if status_map.get(jid) is not None else None),
    )
    return maint.prune_render_temp_dirs(root, **kwargs)


def test_active_and_recent_resumable_kept_stale_removed(monkeypatch, tmp_path):
    status: dict[str, str | None] = {}
    running = _job_dir(tmp_path, status, "running")
    queued = _job_dir(tmp_path, status, "queued")
    interrupted_recent = _job_dir(tmp_path, status, "interrupted")
    paused_recent = _job_dir(tmp_path, status, "paused")
    interrupted_stale = _job_dir(tmp_path, status, "interrupted")
    done = _job_dir(tmp_path, status, "completed")
    failed = _job_dir(tmp_path, status, "failed")
    orphan = _job_dir(tmp_path, status, None)

    # Age the stale one well past the 72h window; recents stay fresh.
    _age_dir(interrupted_stale, 100)

    _run(monkeypatch, tmp_path, status, resume_keep_hours=72)

    assert running.exists() and queued.exists()          # active → kept
    assert interrupted_recent.exists()                   # resumable + recent → kept
    assert paused_recent.exists()                        # resumable + recent → kept
    assert not interrupted_stale.exists()                # resumable but stale → removed
    assert not done.exists() and not failed.exists()     # terminal → removed
    assert not orphan.exists()                            # not in DB → removed


def test_resume_keep_zero_restores_pre_cm4(monkeypatch, tmp_path):
    status: dict[str, str | None] = {}
    interrupted = _job_dir(tmp_path, status, "interrupted")
    _run(monkeypatch, tmp_path, status, resume_keep_hours=0)
    assert not interrupted.exists()  # preservation disabled → pruned like before


def test_non_uuid_dir_untouched(monkeypatch, tmp_path):
    status: dict[str, str | None] = {}
    (tmp_path / "preview").mkdir()
    (tmp_path / "downloads").mkdir()
    res = _run(monkeypatch, tmp_path, status, resume_keep_hours=72)
    assert (tmp_path / "preview").exists() and (tmp_path / "downloads").exists()
    assert res["skipped"] == 2


def test_return_counts(monkeypatch, tmp_path):
    status: dict[str, str | None] = {}
    _job_dir(tmp_path, status, "running")        # kept
    _job_dir(tmp_path, status, "interrupted")    # kept (recent)
    _job_dir(tmp_path, status, "completed")      # removed
    res = _run(monkeypatch, tmp_path, status, resume_keep_hours=72)
    assert res["kept"] == 2 and res["removed"] == 1 and res["skipped"] == 0
