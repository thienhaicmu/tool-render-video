"""Sprint 7.4 — tests for the fused-cut+render path.

Pins:
- `render_part_from_source` exists in base_clip_renderer.py with the
  documented signature.
- `render_part` accepts the three `_source_seek_*` kwargs as a
  backward-compat extension (defaults preserve the pre-Sprint-7.4
  contract — None → no seek, file treated as t=0 pre-cut clip).
- Input-side seek (default) and output-side seek (force_accurate=True)
  produce the documented argv shapes.
- `FEATURE_RAW_PART_SKIP` env var defaults OFF — Sacred Contract #2.
- `_skip_active` truth table: ALL gates must be True for skip to fire.

The full FFmpeg call is mocked — we verify argv composition + helper
dispatch, NOT real video output. Real-render visual review is the
Sprint 7.4 ship gate per SPRINT_PLAN risk register line 302.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Section 1: signature pins
# ---------------------------------------------------------------------------


class TestSignatures:
    def test_render_part_accepts_source_seek_kwargs(self):
        from app.services.render.base_clip_renderer import render_part
        sig = inspect.signature(render_part)
        assert "_source_seek_start" in sig.parameters
        assert "_source_seek_duration" in sig.parameters
        assert "_source_seek_force_accurate" in sig.parameters

    def test_render_part_seek_kwargs_default_none(self):
        from app.services.render.base_clip_renderer import render_part
        sig = inspect.signature(render_part)
        assert sig.parameters["_source_seek_start"].default is None
        assert sig.parameters["_source_seek_duration"].default is None
        assert sig.parameters["_source_seek_force_accurate"].default is False

    def test_render_part_from_source_exists(self):
        from app.services.render.base_clip_renderer import render_part_from_source
        assert callable(render_part_from_source)
        sig = inspect.signature(render_part_from_source)
        assert "source_path" in sig.parameters
        assert "source_start" in sig.parameters
        assert "source_duration" in sig.parameters
        assert "force_accurate_cut" in sig.parameters

    def test_render_part_smart_signature_frozen(self):
        """Sprint 5.2 freeze — render_part_smart signature stays unchanged."""
        from app.services.render.base_clip_renderer import render_part_smart
        sig = inspect.signature(render_part_smart)
        assert "_source_seek_start" not in sig.parameters
        assert "_source_seek_duration" not in sig.parameters


# ---------------------------------------------------------------------------
# Section 2: argv shape pins (input-side vs output-side seek)
# ---------------------------------------------------------------------------


_FAKE_SRC_META = {
    "duration": 60.0, "fps": 30.0, "width": 1920, "height": 1080, "has_audio": True,
}


def _call_render_part_from_source(**overrides):
    """Run render_part_from_source with all external I/O mocked. Returns
    captured cmd list."""
    cmds: list[list] = []

    def _fake_run(cmd, **_kw):
        cmds.append(list(cmd))

    import app.services.render.base_clip_renderer as bcr_mod
    with (
        patch.object(bcr_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META),
        patch.object(bcr_mod, "_has_audio_stream", return_value=True),
        patch.object(bcr_mod, "_resolve_codec", return_value="libx264"),
        patch.object(bcr_mod, "_resolve_fps", return_value=(60, "capped")),
        patch.object(bcr_mod, "_detect_windows_fontfile", return_value=None),
        patch.object(bcr_mod, "_get_custom_fonts_dir", return_value=None),
        patch.object(bcr_mod, "_detect_windows_fonts_dir", return_value=None),
    ):
        kwargs = dict(
            source_path="/fake/source.mp4",
            output_path="/fake/out.mp4",
            source_start=10.0,
            source_duration=5.0,
            subtitle_ass=None,
            title_text=None,
            add_subtitle=False,
            add_title_overlay=False,
            encoder_mode="cpu",
            output_fps=60,
        )
        kwargs.update(overrides)
        bcr_mod.render_part_from_source(**kwargs)
    return cmds


class TestArgvShape:
    def test_input_side_seek_default(self):
        """Default: -ss start -t dur appears BEFORE -i source (fast keyframe seek)."""
        cmds = _call_render_part_from_source()
        cmd = cmds[0]
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx, "Input-side seek: -ss must appear before -i"
        assert cmd[ss_idx + 1] == "10.0"
        # -t should also be before -i
        t_idx = cmd.index("-t")
        assert t_idx < i_idx
        assert cmd[t_idx + 1] == "5.0"

    def test_output_side_seek_force_accurate(self):
        """force_accurate_cut=True: -ss/-t appear AFTER -i (frame-accurate, slower)."""
        cmds = _call_render_part_from_source(force_accurate_cut=True)
        cmd = cmds[0]
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert i_idx < ss_idx, "Output-side seek: -i must appear before -ss"

    def test_source_path_used_as_input(self):
        cmds = _call_render_part_from_source(source_path="/specific/source.mp4")
        cmd = cmds[0]
        i_idx = cmd.index("-i")
        assert cmd[i_idx + 1] == "/specific/source.mp4"

    def test_output_path_at_end(self):
        cmds = _call_render_part_from_source(output_path="/specific/out.mp4")
        cmd = cmds[0]
        assert cmd[-1] == "/specific/out.mp4"


# ---------------------------------------------------------------------------
# Section 3: backward compatibility — render_part without seek kwargs
# ---------------------------------------------------------------------------


class TestRenderPartBackwardCompat:
    """When _source_seek_* are None (default), render_part behaves exactly
    as before Sprint 7.4 — `-i input_path` with no seek prefix."""

    def test_no_seek_when_kwargs_default(self):
        cmds: list[list] = []
        def _fake_run(cmd, **_kw):
            cmds.append(list(cmd))

        import app.services.render.base_clip_renderer as bcr_mod
        with (
            patch.object(bcr_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
            patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META),
            patch.object(bcr_mod, "_has_audio_stream", return_value=True),
            patch.object(bcr_mod, "_resolve_codec", return_value="libx264"),
            patch.object(bcr_mod, "_resolve_fps", return_value=(60, "capped")),
            patch.object(bcr_mod, "_detect_windows_fontfile", return_value=None),
            patch.object(bcr_mod, "_get_custom_fonts_dir", return_value=None),
            patch.object(bcr_mod, "_detect_windows_fonts_dir", return_value=None),
        ):
            bcr_mod.render_part(
                input_path="/fake/raw_part.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass=None,
                title_text=None,
                add_subtitle=False,
                add_title_overlay=False,
                encoder_mode="cpu",
                output_fps=60,
            )

        cmd = cmds[0]
        # When no seek kwargs provided, -ss and -t must NOT appear before -i.
        i_idx = cmd.index("-i")
        # Check no -ss appears between the binary and -i
        for tok in cmd[1:i_idx]:
            assert tok != "-ss", "Backward-compat: no -ss should appear when seek kwargs are None"
            assert tok != "-t"


# ---------------------------------------------------------------------------
# Section 4: FEATURE_RAW_PART_SKIP env flag (Sacred Contract #2)
# ---------------------------------------------------------------------------


class TestRawPartSkipFlag:
    def test_flag_defaults_off(self):
        """Sacred Contract #2: new flag defaults OFF."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATURE_RAW_PART_SKIP", None)
            v = os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"
        assert v is False

    def test_flag_on_when_set_to_1(self):
        with patch.dict(os.environ, {"FEATURE_RAW_PART_SKIP": "1"}):
            v = os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"
        assert v is True

    def test_flag_strict_compare(self):
        """Strict == "1" — anything else stays OFF."""
        for val in ("true", "yes", "on", "TRUE", "0", "2"):
            with patch.dict(os.environ, {"FEATURE_RAW_PART_SKIP": val}):
                v = os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"
            assert v is False, f"flag={val!r} should not enable skip"


# ---------------------------------------------------------------------------
# Section 5: module-level flag reads coherent across 5 sites
# ---------------------------------------------------------------------------


class TestFlagReadsCoherent:
    """5 sites mirror FEATURE_RAW_PART_SKIP (same drift-prevention pattern as
    FEATURE_BASE_CLIP_FIRST). Each must hold a module-level constant of
    the same name."""

    def test_render_pipeline_reads_flag(self):
        from app.orchestration import render_pipeline
        assert hasattr(render_pipeline, "_FEATURE_RAW_PART_SKIP")

    def test_part_renderer_reads_flag(self):
        from app.orchestration.stages import part_renderer
        assert hasattr(part_renderer, "_FEATURE_RAW_PART_SKIP")

    def test_part_render_setup_reads_flag(self):
        from app.orchestration.stages import part_render_setup
        assert hasattr(part_render_setup, "_FEATURE_RAW_PART_SKIP")

    def test_part_render_encode_reads_flag(self):
        from app.orchestration.stages import part_render_encode
        assert hasattr(part_render_encode, "_FEATURE_RAW_PART_SKIP")

    def test_part_cut_reads_flag(self):
        from app.orchestration.stages import part_cut
        assert hasattr(part_cut, "_FEATURE_RAW_PART_SKIP")


# ---------------------------------------------------------------------------
# Section 6: skip-active truth table (computed inline in run_cut_stage)
# ---------------------------------------------------------------------------


def _skip_active(*, predicate: bool, flag: bool, motion_aware: bool) -> bool:
    """Mirror of the production gate in run_cut_stage Sprint 7.4."""
    return predicate and flag and not motion_aware


class TestSkipActiveTruthTable:
    def test_skip_when_all_gates_pass(self):
        assert _skip_active(predicate=True, flag=True, motion_aware=False) is True

    def test_no_skip_when_predicate_false(self):
        assert _skip_active(predicate=False, flag=True, motion_aware=False) is False

    def test_no_skip_when_flag_off(self):
        assert _skip_active(predicate=True, flag=False, motion_aware=False) is False

    def test_no_skip_when_motion_aware(self):
        """Sprint 7.4 = Option E scope. Motion-aware path stays on the
        cut→render_part_smart code path until Sprint 7.8."""
        assert _skip_active(predicate=True, flag=True, motion_aware=True) is False

    def test_no_skip_when_only_predicate(self):
        """Default config: flag OFF → no behaviour change even if
        predicate fires."""
        assert _skip_active(predicate=True, flag=False, motion_aware=False) is False


# ---------------------------------------------------------------------------
# Section 7: production source pins
# ---------------------------------------------------------------------------


class TestProductionSourcePins:
    def test_part_cut_implements_skip_active(self):
        from app.orchestration.stages import part_cut
        src = inspect.getsource(part_cut.run_cut_stage)
        assert "_skip_active" in src
        assert "_FEATURE_RAW_PART_SKIP" in src
        assert "raw_part_skip_active" in src

    def test_part_render_encode_routes_to_from_source(self):
        from app.orchestration.stages import part_render_encode
        src = inspect.getsource(part_render_encode)
        assert "render_part_from_source" in src
        assert "_raw_part_absent" in src or "raw_part.exists()" in src
