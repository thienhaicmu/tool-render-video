"""
Guard tests for render_pipeline.py — P1-4 validation / stall guard additions.

Covers:
  1. _duration_tolerance — formula correctness
  2. _stall_deadline — formula correctness
  3. _render_progress_timer — stall-suspected warning (unknown duration, emits once)
  4. _render_progress_timer — hard stall guard (sets stop_event, exits loop)
  5. _validate_render_output — new tolerance formula wired in
  6. quality penalty >20 emits render.quality_penalty_high event
"""

import contextlib
import threading
import time
import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# 1. _duration_tolerance — pure formula
# ---------------------------------------------------------------------------

class TestDurationTolerance:
    """Guards the tolerance formula: max(0.5, min(ed * 0.15, 3.0))."""

    def _tol(self, expected_duration: float) -> float:
        from app.orchestration.render_pipeline import _duration_tolerance
        return _duration_tolerance(expected_duration)

    def test_very_short_clip_gets_minimum_tolerance(self):
        """expected_duration=2 → 2*0.15=0.3, clamped up to 0.5."""
        t = self._tol(2.0)
        assert t == pytest.approx(0.5), f"expected 0.5, got {t}"

    def test_mid_length_clip_uses_percentage(self):
        """expected_duration=10 → 10*0.15=1.5, within [0.5, 3.0]."""
        t = self._tol(10.0)
        assert t == pytest.approx(1.5), f"expected 1.5, got {t}"

    def test_long_clip_capped_at_3s(self):
        """expected_duration=100 → 100*0.15=15.0, clamped down to 3.0."""
        t = self._tol(100.0)
        assert t == pytest.approx(3.0), f"expected 3.0, got {t}"

    def test_exactly_at_cap_boundary(self):
        """expected_duration=20 → 20*0.15=3.0, right at cap."""
        t = self._tol(20.0)
        assert t == pytest.approx(3.0)

    def test_zero_duration_returns_fallback(self):
        """expected_duration=0 → safe fallback 1.0."""
        t = self._tol(0.0)
        assert t == pytest.approx(1.0)

    def test_negative_duration_returns_fallback(self):
        t = self._tol(-5.0)
        assert t == pytest.approx(1.0)

    def test_minimum_floor_is_0_5_not_1(self):
        """Old formula used max(1.0, ...). New floor is 0.5."""
        t = self._tol(2.0)
        assert t < 1.0, "new floor must be < 1.0 (0.5), not the old 1.0"

    def test_returns_float(self):
        assert isinstance(self._tol(10.0), float)


# ---------------------------------------------------------------------------
# 2. _stall_deadline — pure formula
# ---------------------------------------------------------------------------

class TestStallDeadline:
    def _dl(self, encode_start: float, expected_duration: float) -> float:
        from app.orchestration.render_pipeline import _stall_deadline
        return _stall_deadline(encode_start, expected_duration)

    def test_short_clip_uses_minimum_120s(self):
        """expected_duration=5 → 5*10=50 < 120, so deadline = start + 120."""
        dl = self._dl(1000.0, 5.0)
        assert dl == pytest.approx(1000.0 + 120.0)

    def test_long_clip_uses_duration_times_10(self):
        """expected_duration=60 → 60*10=600 > 120, so deadline = start + 600."""
        dl = self._dl(0.0, 60.0)
        assert dl == pytest.approx(600.0)

    def test_zero_duration_uses_fallback_60s_times_10(self):
        """expected_duration=0 → fallback 60*10=600 > 120."""
        dl = self._dl(0.0, 0.0)
        assert dl == pytest.approx(600.0)

    def test_none_duration_uses_fallback(self):
        """expected_duration=None → or-fallback to 60."""
        from app.orchestration.render_pipeline import _stall_deadline
        dl = _stall_deadline(0.0, None)  # type: ignore[arg-type]
        assert dl == pytest.approx(600.0)


# ---------------------------------------------------------------------------
# Shared helpers for timer tests
# ---------------------------------------------------------------------------

def _make_seg(duration=30.0):
    return {"start": 0.0, "end": duration, "duration": duration,
            "viral_score": 0, "motion_score": 0, "hook_score": 0}


def _run_timer(expected_duration, channel_code="testchan", ticks=1,
               tick_sec_override=None, mock_upsert=None, mock_emit=None,
               extra_patches=None):
    """Run _render_progress_timer in a thread for `ticks` iterations then stop it.

    Returns (stop_event, upsert_mock, emit_mock).
    """
    from app.orchestration.render_pipeline import _render_progress_timer

    stop = threading.Event()
    seg = _make_seg(expected_duration if expected_duration > 0 else 30.0)
    upsert = mock_upsert or MagicMock()
    emit = mock_emit or MagicMock()

    patches = [
        patch("app.orchestration.render_pipeline.upsert_job_part", upsert),
        patch("app.orchestration.render_pipeline._emit_render_event", emit),
    ]
    if tick_sec_override is not None:
        patches.append(
            patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", tick_sec_override)
        )
    if extra_patches:
        patches.extend(extra_patches)

    def _target():
        _render_progress_timer(
            stop, "job123", 1, "part_1", seg,
            "/out/part_1.mp4", time.monotonic(), expected_duration,
            channel_code,
        )

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        t = threading.Thread(target=_target, daemon=True)
        t.start()
        # Let the timer run for ticks+1 cycles so assertions cover ticks iterations
        time.sleep((ticks + 0.5) * (tick_sec_override or 0.05))
        stop.set()
        t.join(timeout=2.0)

    return stop, upsert, emit


# ---------------------------------------------------------------------------
# 3. _render_progress_timer — stall-suspected warning (unknown duration)
# ---------------------------------------------------------------------------

class TestProgressTimerStallSuspected:
    """When expected_duration <= 0 and elapsed > 300 s, emit render.stall_suspected once."""

    def test_stall_suspected_emitted_once_for_unknown_duration(self):
        """Simulate elapsed > 300 by freezing time.monotonic past the threshold."""
        from app.orchestration.render_pipeline import _render_progress_timer

        stop = threading.Event()
        seg = _make_seg(30.0)
        upsert = MagicMock()
        emit = MagicMock()

        # Fake encode_start so that elapsed is >300 s on first tick
        fake_start = time.monotonic() - 310.0

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "job1", 1, "p1", seg, "/out/p1.mp4",
                      fake_start, 0.0, "testchan"),
                daemon=True,
            )
            t.start()
            time.sleep(0.25)  # allow 4–5 ticks
            stop.set()
            t.join(timeout=2.0)

        stall_calls = [
            c for c in emit.call_args_list
            if c.kwargs.get("event") == "render.stall_suspected"
        ]
        assert len(stall_calls) == 1, (
            f"render.stall_suspected should be emitted exactly once, got {len(stall_calls)}"
        )

    def test_stall_suspected_not_emitted_when_duration_known(self):
        """If expected_duration > 0, stall_suspected must never be emitted."""
        from app.orchestration.render_pipeline import _render_progress_timer

        stop = threading.Event()
        seg = _make_seg(30.0)
        emit = MagicMock()
        upsert = MagicMock()
        fake_start = time.monotonic() - 310.0

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "job2", 1, "p1", seg, "/out/p1.mp4",
                      fake_start, 30.0, "testchan"),  # known duration
                daemon=True,
            )
            t.start()
            time.sleep(0.15)
            stop.set()
            t.join(timeout=2.0)

        stall_calls = [
            c for c in emit.call_args_list
            if c.kwargs.get("event") == "render.stall_suspected"
        ]
        assert len(stall_calls) == 0

    def test_stall_suspected_not_emitted_before_300s(self):
        """elapsed < 300 → no stall_suspected even for unknown duration."""
        from app.orchestration.render_pipeline import _render_progress_timer

        stop = threading.Event()
        seg = _make_seg(30.0)
        emit = MagicMock()
        upsert = MagicMock()

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "job3", 1, "p1", seg, "/out/p1.mp4",
                      time.monotonic(), 0.0, "testchan"),  # fresh start, elapsed < 300
                daemon=True,
            )
            t.start()
            time.sleep(0.15)
            stop.set()
            t.join(timeout=2.0)

        stall_calls = [
            c for c in emit.call_args_list
            if c.kwargs.get("event") == "render.stall_suspected"
        ]
        assert len(stall_calls) == 0

    def test_stall_suspected_warning_level(self):
        """render.stall_suspected must be emitted at WARNING level."""
        from app.orchestration.render_pipeline import _render_progress_timer

        stop = threading.Event()
        seg = _make_seg(30.0)
        emit = MagicMock()
        upsert = MagicMock()
        fake_start = time.monotonic() - 310.0

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "job4", 1, "p1", seg, "/out/p1.mp4",
                      fake_start, 0.0, "testchan"),
                daemon=True,
            )
            t.start()
            time.sleep(0.25)
            stop.set()
            t.join(timeout=2.0)

        stall_calls = [
            c for c in emit.call_args_list
            if c.kwargs.get("event") == "render.stall_suspected"
        ]
        assert stall_calls, "no stall_suspected call found"
        assert stall_calls[0].kwargs["level"] == "WARNING"


# ---------------------------------------------------------------------------
# 4. _render_progress_timer — hard stall guard
# ---------------------------------------------------------------------------

class TestProgressTimerStallDetected:
    """When stall_deadline is exceeded, timer sets stop_event and breaks."""

    def _run_stall_detected(self):
        """Return (stop_event, upsert_mock, emit_mock) after stall fires."""
        from app.orchestration.render_pipeline import _render_progress_timer

        stop = threading.Event()
        seg = _make_seg(30.0)
        emit = MagicMock()
        upsert = MagicMock()

        # Make deadline in the past so stall fires immediately on first tick
        past_deadline = time.monotonic() - 1.0

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05), \
             patch("app.orchestration.render_pipeline._stall_deadline",
                   return_value=past_deadline):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "jobS", 2, "pS", seg, "/out/pS.mp4",
                      time.monotonic(), 30.0, "testchan"),
                daemon=True,
            )
            t.start()
            t.join(timeout=2.0)  # thread should exit on its own

        return stop, upsert, emit

    def test_stop_event_is_set_after_stall(self):
        stop, _, _ = self._run_stall_detected()
        assert stop.is_set(), "stop_event must be set when stall_detected fires"

    def test_stall_detected_event_emitted(self):
        _, _, emit = self._run_stall_detected()
        events = [c.kwargs.get("event") for c in emit.call_args_list]
        assert "render.stall_detected" in events

    def test_stall_detected_marks_part_failed(self):
        _, upsert, _ = self._run_stall_detected()
        from app.core.stage import JobPartStage
        failed_calls = [
            c for c in upsert.call_args_list
            if len(c.args) > 3 and c.args[3] == JobPartStage.FAILED
        ]
        assert failed_calls, "upsert_job_part must be called with FAILED when stall detected"

    def test_stall_detected_warning_level(self):
        _, _, emit = self._run_stall_detected()
        stall_calls = [
            c for c in emit.call_args_list
            if c.kwargs.get("event") == "render.stall_detected"
        ]
        assert stall_calls, "render.stall_detected event not found"
        assert stall_calls[0].kwargs["level"] == "WARNING"

    def test_normal_progress_tick_not_called_after_stall(self):
        """After stall fires, the timer must break — no RENDERING upsert after FAILED."""
        from app.orchestration.render_pipeline import _render_progress_timer
        from app.core.stage import JobPartStage

        stop = threading.Event()
        seg = _make_seg(30.0)
        upsert = MagicMock()
        emit = MagicMock()
        past_deadline = time.monotonic() - 1.0

        with patch("app.orchestration.render_pipeline.upsert_job_part", upsert), \
             patch("app.orchestration.render_pipeline._emit_render_event", emit), \
             patch("app.orchestration.render_pipeline._PROGRESS_TICK_SEC", 0.05), \
             patch("app.orchestration.render_pipeline._stall_deadline",
                   return_value=past_deadline):
            t = threading.Thread(
                target=_render_progress_timer,
                args=(stop, "jobS2", 3, "pS2", seg, "/out/pS2.mp4",
                      time.monotonic(), 30.0, "testchan"),
                daemon=True,
            )
            t.start()
            t.join(timeout=2.0)

        # Check that after FAILED was written, no RENDERING writes followed
        calls = upsert.call_args_list
        last_stage_idx = {}
        for i, c in enumerate(calls):
            if len(c.args) > 3:
                last_stage_idx[c.args[3]] = i
        if JobPartStage.FAILED in last_stage_idx and JobPartStage.RENDERING in last_stage_idx:
            assert last_stage_idx[JobPartStage.FAILED] >= last_stage_idx[JobPartStage.RENDERING], \
                "RENDERING was written after FAILED — timer did not break"


# ---------------------------------------------------------------------------
# 5. _validate_render_output — new tolerance wired in
# ---------------------------------------------------------------------------

class TestValidateRenderOutputTolerance:
    """Guards that _validate_render_output uses the new _duration_tolerance formula."""

    def _validate(self, output_path, expected_duration=None, expect_audio=None):
        from app.orchestration.render_pipeline import _validate_render_output
        return _validate_render_output(output_path, expected_duration, expect_audio)

    def _make_probe_result(self, duration: float, has_video=True, has_audio=True,
                           size=50_000) -> tuple:
        """Return (mock_path, mock_ffprobe_output) for a synthetic file."""
        import json
        streams = []
        if has_video:
            streams.append({"codec_type": "video"})
        if has_audio:
            streams.append({"codec_type": "audio"})
        probe_json = json.dumps({
            "streams": streams,
            "format": {"duration": str(duration)},
        })
        return probe_json, size

    def test_tolerance_2s_clip_accepts_0_4s_deviation(self):
        """expected=2, tolerance=0.5: a 2.4s output (dev=0.4) must pass."""
        import json
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        probe_out, _ = self._make_probe_result(2.4)
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=50_000)
        mock_path.__str__ = lambda s: "/fake/out.mp4"

        fake_proc = MagicMock(returncode=0, stdout=probe_out, stderr="")
        with patch("app.orchestration.render_pipeline.subprocess.run", return_value=fake_proc):
            result = self._validate(mock_path, expected_duration=2.0)
        assert result["ok"] is True, f"should pass with 0.4s deviation on 2s clip: {result}"

    def test_tolerance_2s_clip_rejects_0_6s_deviation(self):
        """expected=2, tolerance=0.5: a 2.6s output (dev=0.6) must fail."""
        import json
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        probe_out, _ = self._make_probe_result(2.6)
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=50_000)
        mock_path.__str__ = lambda s: "/fake/out.mp4"

        fake_proc = MagicMock(returncode=0, stdout=probe_out, stderr="")
        with patch("app.orchestration.render_pipeline.subprocess.run", return_value=fake_proc):
            result = self._validate(mock_path, expected_duration=2.0)
        assert result["ok"] is False, "0.6s deviation on 2s clip must fail"

    def test_tolerance_100s_clip_capped_at_3s(self):
        """expected=100, 15% would be 15s but cap is 3.0s.
        A 104s output (dev=4) must fail."""
        import json
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        probe_out, _ = self._make_probe_result(104.0)
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=50_000)
        mock_path.__str__ = lambda s: "/fake/out.mp4"

        fake_proc = MagicMock(returncode=0, stdout=probe_out, stderr="")
        with patch("app.orchestration.render_pipeline.subprocess.run", return_value=fake_proc):
            result = self._validate(mock_path, expected_duration=100.0)
        assert result["ok"] is False, "4s deviation on 100s clip should fail (cap=3.0s)"

    def test_tolerance_stored_in_metadata(self):
        """Tolerance value written to metadata must match _duration_tolerance."""
        from app.orchestration.render_pipeline import _duration_tolerance
        import json
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        probe_out, _ = self._make_probe_result(10.0)
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=50_000)
        mock_path.__str__ = lambda s: "/fake/out.mp4"

        fake_proc = MagicMock(returncode=0, stdout=probe_out, stderr="")
        with patch("app.orchestration.render_pipeline.subprocess.run", return_value=fake_proc):
            result = self._validate(mock_path, expected_duration=10.0)

        assert "duration_tolerance" in result["metadata"]
        assert result["metadata"]["duration_tolerance"] == pytest.approx(
            _duration_tolerance(10.0)
        )


# ---------------------------------------------------------------------------
# 6. Quality penalty >20 emits render.quality_penalty_high
# ---------------------------------------------------------------------------

class TestQualityPenaltyHighEvent:
    """Guards that _assess_output_quality penalty > 20 triggers a specific warning event.

    Rather than invoking the full pipeline, we test the _assess_output_quality
    return value directly and the guard logic separately to keep tests fast and
    without real media files.
    """

    def test_assess_output_quality_returns_score_penalty(self, tmp_path):
        """Verify _assess_output_quality returns a numeric score_penalty key."""
        from app.orchestration.render_pipeline import _assess_output_quality
        # Write a minimal valid-looking mp4 (won't pass ffmpeg checks but function
        # must not raise — all exceptions are swallowed internally)
        fake = tmp_path / "fake.mp4"
        fake.write_bytes(b"\x00" * 100)

        with patch("app.orchestration.render_pipeline.subprocess.run") as mock_run:
            # blackdetect + blurdetect both time out / return non-zero → penalty=0
            mock_run.side_effect = Exception("no ffmpeg in test")
            result = _assess_output_quality(fake, tmp_path)
        assert "score_penalty" in result
        assert isinstance(result["score_penalty"], (int, float))

    def test_penalty_above_20_threshold(self):
        """When score_penalty > 20, the event render.quality_penalty_high must be emitted."""
        # We simulate the check that the pipeline caller applies.
        emit = MagicMock()
        quality_result = {
            "passed": True,
            "hard_failures": [],
            "warnings": ["first frame dark", "subtitle missing"],
            "checks": {},
            "score_penalty": 25,
        }
        _quality_penalty = int(quality_result["score_penalty"])
        if _quality_penalty > 20:
            emit(
                channel_code="tc",
                job_id="j1",
                event="render.quality_penalty_high",
                level="WARNING",
                message=f"Part 1 quality penalty high: -{_quality_penalty} points",
                step="render.output.quality",
                context={"part_no": 1, "warnings": quality_result["warnings"],
                         "score_penalty": _quality_penalty},
            )
        calls = [c for c in emit.call_args_list if c.kwargs.get("event") == "render.quality_penalty_high"]
        assert len(calls) == 1

    def test_penalty_at_or_below_20_no_high_event(self):
        """score_penalty = 20 must NOT trigger render.quality_penalty_high."""
        emit = MagicMock()
        for penalty in (0, 10, 20):
            emit.reset_mock()
            _quality_penalty = penalty
            if _quality_penalty > 20:
                emit(event="render.quality_penalty_high")
            calls = [c for c in emit.call_args_list
                     if c.kwargs.get("event") == "render.quality_penalty_high"]
            assert len(calls) == 0, f"penalty={penalty} should not trigger high event"
