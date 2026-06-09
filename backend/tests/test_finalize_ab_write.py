"""Sprint I-C — pipeline_finalize best-effort A/B score write tests.

Verifies the G-3 block inside run_render_finalize:

1. upsert_ab_score is called once per rank_entries_ordered entry.
2. Exception from upsert_ab_score is swallowed — finalize still returns status.
3. channel_code from payload is forwarded to upsert_ab_score.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import call, patch


def _make_ctx(rank_entries_ordered=None, channel_code="test_ch"):
    from app.features.render.engine.pipeline.pipeline_finalize import FinalizeContext
    from app.models.render import RenderRequest

    payload = RenderRequest(
        channel_code=channel_code,
        source_mode="local",
        source_video_path="/nonexistent.mp4",
        output_dir="/nonexistent/out",
    )
    return FinalizeContext(
        job_id="job-ic",
        effective_channel=channel_code,
        payload=payload,
        started_at=datetime.utcnow(),
        output_dir=Path("/nonexistent/out"),
        output_stem="ic_stem",
        outputs=[],
        failed_parts=[],
        total_parts=0,
        scored=[],
        recovery_notes=[],
        rank_entries=[],
        rank_entries_ordered=rank_entries_ordered or [],
        best_rank_entry=None,
        partial_warning="",
        preset_name="",
        preset_id="",
        preset_label="",
        mv_parts=[],
        voice_summary=None,
        subtitle_translate_summary=None,
        render_plan=None,
        rank_source="fallback",
    )


def _run_finalize(ctx):
    from app.features.render.engine.pipeline import pipeline_finalize
    with patch.object(pipeline_finalize, "upsert_job"), \
         patch.object(pipeline_finalize, "_emit_render_event"), \
         patch.object(pipeline_finalize, "_job_log"), \
         patch("app.features.render.engine.pipeline.db_backup.maybe_snapshot_after_job"):
        try:
            return pipeline_finalize.run_render_finalize(ctx)
        except Exception:
            return None


# 1. upsert_ab_score is called once per rank_entries_ordered entry
def test_ab_write_called_for_each_entry():
    entries = [
        {"part_no": 1, "segment_viral_score": 80.0, "hook_score": 75.0,
         "retention_score": 70.0, "output_rank_score": 78.0,
         "output_rank": 1, "is_best_output": True},
        {"part_no": 2, "segment_viral_score": 60.0, "hook_score": 55.0,
         "retention_score": 50.0, "output_rank_score": 58.0,
         "output_rank": 2, "is_best_output": False},
    ]
    ctx = _make_ctx(rank_entries_ordered=entries)

    with patch("app.db.ab_scores_repo.upsert_ab_score") as mock_upsert:
        _run_finalize(ctx)

    assert mock_upsert.call_count == 2
    part_nos = [c.kwargs["part_no"] for c in mock_upsert.call_args_list]
    assert sorted(part_nos) == [1, 2]


# 2. Exception from upsert_ab_score is swallowed — finalize still completes
def test_ab_write_exception_swallowed():
    entries = [
        {"part_no": 1, "segment_viral_score": 50.0, "hook_score": 50.0,
         "retention_score": 50.0, "output_rank_score": 50.0,
         "output_rank": 1, "is_best_output": True},
    ]
    ctx = _make_ctx(rank_entries_ordered=entries)

    with patch("app.db.ab_scores_repo.upsert_ab_score", side_effect=RuntimeError("DB dead")):
        result = _run_finalize(ctx)

    # finalize must still return the status string, not None
    assert result in ("completed", "completed_with_errors")


# 3. channel_code from payload is forwarded to upsert_ab_score
def test_ab_write_forwards_channel_code():
    entries = [
        {"part_no": 1, "segment_viral_score": 70.0, "hook_score": 65.0,
         "retention_score": 60.0, "output_rank_score": 67.0,
         "output_rank": 1, "is_best_output": True},
    ]
    ctx = _make_ctx(rank_entries_ordered=entries, channel_code="vn_edu")

    with patch("app.db.ab_scores_repo.upsert_ab_score") as mock_upsert:
        _run_finalize(ctx)

    assert mock_upsert.call_count == 1
    assert mock_upsert.call_args.kwargs["channel_code"] == "vn_edu"
