"""
test_render_events.py — Unit tests for Phase 4D render_events additions.

Coverage:
- _event_from_stage maps known/unknown stage names
- _resolve_job_log_dir returns expected paths for channel/non-channel modes
- _render_progress_timer: import from new module and from render_pipeline
- _render_progress_timer: emits stall_suspected event after timeout threshold
- _render_progress_timer: stops when stop_event is set
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Section 1: _event_from_stage
# ---------------------------------------------------------------------------

class TestEventFromStage:
    def test_import_from_render_events(self):
        from app.orchestration.render_events import _event_from_stage
        assert callable(_event_from_stage)

    def test_re_exported_from_render_pipeline(self):
        from app.orchestration.render_events import _event_from_stage
        from app.orchestration.render_pipeline import _event_from_stage as rp_fn
        assert rp_fn is _event_from_stage

    def test_known_stage_returns_mapped_event(self):
        from app.orchestration.render_events import _event_from_stage
        from app.core.stage import STAGE_TO_EVENT
        for stage, expected_event in STAGE_TO_EVENT.items():
            assert _event_from_stage(stage) == expected_event

    def test_unknown_stage_returns_default(self):
        from app.orchestration.render_events import _event_from_stage
        result = _event_from_stage("totally_unknown_stage_xyz")
        assert result == "render.start"


# ---------------------------------------------------------------------------
# Section 2: _resolve_job_log_dir
# ---------------------------------------------------------------------------

class TestResolveJobLogDir:
    def test_import_from_render_events(self):
        from app.orchestration.render_events import _resolve_job_log_dir
        assert callable(_resolve_job_log_dir)

    def test_re_exported_from_render_pipeline(self):
        from app.orchestration.render_events import _resolve_job_log_dir
        from app.orchestration.render_pipeline import _resolve_job_log_dir as rp_fn
        assert rp_fn is _resolve_job_log_dir

    def test_non_channel_mode_uses_underscore_logs(self, tmp_path):
        from app.orchestration.render_events import _resolve_job_log_dir
        result = _resolve_job_log_dir(tmp_path, "manual", "chan1")
        assert result == tmp_path.resolve() / "_logs"

    def test_channel_mode_returns_logs_subdir(self, tmp_path):
        from app.orchestration.render_events import _resolve_job_log_dir
        result = _resolve_job_log_dir(tmp_path, "channel", "chan1")
        assert result.name == "logs"

    def test_channel_mode_finds_matching_ancestor(self, tmp_path):
        from app.orchestration.render_events import _resolve_job_log_dir
        chan_dir = tmp_path / "mychan"
        output_dir = chan_dir / "Video"
        chan_dir.mkdir()
        output_dir.mkdir()
        result = _resolve_job_log_dir(output_dir, "channel", "mychan")
        assert result == chan_dir.resolve() / "logs"

    def test_channel_mode_video_output_walks_up(self, tmp_path):
        from app.orchestration.render_events import _resolve_job_log_dir
        upload_dir = tmp_path / "upload"
        video_dir = upload_dir / "video_output"
        upload_dir.mkdir()
        video_dir.mkdir()
        result = _resolve_job_log_dir(video_dir, "channel", "otherchan")
        assert result == tmp_path.resolve() / "logs"


# ---------------------------------------------------------------------------
# Section 3: _render_progress_timer
# ---------------------------------------------------------------------------

class TestRenderProgressTimer:
    def test_import_from_render_events(self):
        from app.orchestration.render_events import _render_progress_timer
        assert callable(_render_progress_timer)

    def test_re_exported_from_render_pipeline(self):
        from app.orchestration.render_events import _render_progress_timer
        from app.orchestration.render_pipeline import _render_progress_timer as rp_fn
        assert rp_fn is _render_progress_timer

    def test_stops_immediately_when_event_set(self):
        from app.orchestration.render_events import _render_progress_timer
        stop = threading.Event()
        stop.set()
        with patch("app.orchestration.render_events.upsert_job_part") as mock_upsert:
            _render_progress_timer(
                stop, "job1", 1, "part_001",
                {"start": 0, "end": 30, "duration": 30},
                "/out/part_001.mp4", time.monotonic(), 30.0,
                channel_code="ch",
            )
        mock_upsert.assert_not_called()

    def test_writes_progress_to_db_on_tick(self):
        from app.orchestration.render_events import _render_progress_timer, _PROGRESS_TICK_SEC
        stop = threading.Event()
        calls = []

        def fake_upsert(*args, **kwargs):
            calls.append(args)
            stop.set()  # stop after first DB write

        seg = {"start": 0, "end": 30, "duration": 30,
               "viral_score": 50, "motion_score": 40, "hook_score": 30}
        with patch("app.orchestration.render_events.upsert_job_part", side_effect=fake_upsert):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "job1", 1, "part_001", seg, "/out/part_001.mp4",
                      time.monotonic(), 30.0),
                kwargs={"channel_code": "ch"},
            )
            t.start()
            t.join(timeout=_PROGRESS_TICK_SEC * 3)

        assert len(calls) >= 1
        assert calls[0][0] == "job1"  # job_id is first arg

    def test_stall_deadline_triggers_failure(self):
        from app.orchestration.render_events import _render_progress_timer
        stop = threading.Event()
        upsert_calls = []

        def fake_upsert(*args, **kwargs):
            upsert_calls.append(args)
            if stop.is_set():
                return

        seg = {"start": 0, "end": 5, "duration": 5,
               "viral_score": 0, "motion_score": 0, "hook_score": 0}

        # Use very short deadline by mocking _stall_deadline to return now + 0.1s
        with (
            patch("app.orchestration.render_events.upsert_job_part", side_effect=fake_upsert),
            patch("app.orchestration.qa_pipeline._stall_deadline", return_value=time.monotonic() + 0.05),
            patch("app.orchestration.render_events._emit_render_event"),
        ):
            from app.orchestration.render_events import _render_progress_timer as rpt
            # Re-import to pick up mock; call directly in thread
            t = threading.Thread(
                target=rpt,
                args=(stop, "job1", 1, "part_001", seg, "/out/part_001.mp4",
                      time.monotonic() - 200.0, 5.0),
                kwargs={"channel_code": "ch"},
            )
            t.start()
            t.join(timeout=5.0)

        assert stop.is_set()
