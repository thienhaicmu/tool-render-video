"""Regression tests for the 2026-06-18 perf-review fixes.

Covers the two correctness regressions found reviewing commit 4a47ea2b:
  - batch_upsert_job_parts_queued must tolerate None segment scores
    (the per-row upsert_job_part it replaced bound them raw -> NULL).
  - probe_video_metadata must report the true fps for high-frame-rate
    sources (the old 120fps clamp silently zeroed 144/240fps, which made
    scene_detector fall back to 30fps and mis-scale scene timestamps).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# #1 — batch_upsert_job_parts_queued tolerates None scores
# ---------------------------------------------------------------------------

def test_batch_upsert_tolerates_none_scores():
    from app.db import jobs_repo

    captured = {}

    def _fake_executemany(_sql, payload):
        captured["payload"] = list(payload)

    fake_cur = MagicMock()
    fake_cur.executemany.side_effect = _fake_executemany
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    rows = [
        {
            "job_id": "job-x",
            "part_no": 1,
            "part_name": "part_001",
            "start_sec": 0.0,
            "end_sec": 5.0,
            "duration": 5.0,
            # Explicit None scores — must coerce to 0.0, not raise TypeError.
            "viral_score": None,
            "motion_score": None,
            "hook_score": None,
        }
    ]

    with patch.object(jobs_repo, "_thread_conn", return_value=fake_conn):
        count = jobs_repo.batch_upsert_job_parts_queued(rows)

    assert count == 1
    row = captured["payload"][0]
    # Tuple layout: (job_id, part_no, part_name, status, progress, start, end,
    #                duration, viral, motion, hook, output_file, message)
    assert row[8] == 0.0   # viral_score
    assert row[9] == 0.0   # motion_score
    assert row[10] == 0.0  # hook_score


def test_batch_upsert_empty_rows_short_circuits():
    from app.db import jobs_repo
    # Must not touch the DB at all for an empty seed list.
    with patch.object(jobs_repo, "_thread_conn") as _tc:
        assert jobs_repo.batch_upsert_job_parts_queued([]) == 0
        _tc.assert_not_called()


# ---------------------------------------------------------------------------
# #2 — probe_video_metadata reports true fps for high-frame-rate sources
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fps_str,expected", [("144/1", 144.0), ("240/1", 240.0), ("60/1", 60.0)])
def test_probe_reports_true_hfr_fps(fps_str, expected):
    from app.features.render.engine.encoder import ffmpeg_helpers

    probe_json = json.dumps({
        "format": {"duration": "10.0"},
        "streams": [{
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": fps_str,
            "r_frame_rate": fps_str,
        }],
    })
    fake_run = MagicMock(returncode=0, stdout=probe_json)

    # _file_probe_key returns "" for a non-existent path so the probe cache is
    # skipped — each call re-runs the (mocked) subprocess.
    with patch.object(ffmpeg_helpers.subprocess, "run", return_value=fake_run):
        meta = ffmpeg_helpers.probe_video_metadata("D:/nonexistent/hfr_clip.mp4")

    assert meta["fps"] == expected
