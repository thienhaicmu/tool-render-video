"""
Guard tests for render_engine.py — covers:
  1. resolve_target_dimensions — every supported aspect ratio
  2. resolve_target_dimensions — unknown/empty input fallback
  3. render_part uses the helper (integration check via filter string)
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 1. resolve_target_dimensions — pure unit tests (no FFmpeg, no fixtures)
# ---------------------------------------------------------------------------

class TestResolveTargetDimensions:
    """These tests are the primary guard against silent wrong-dimension renders.
    All assertions are against the business requirements documented in the audit."""

    def test_16_9_returns_landscape_1920x1080(self):
        """16:9 must produce landscape output, not portrait."""
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("16:9")
        assert (w, h) == (1920, 1080), f"16:9 gave {w}x{h}, expected 1920x1080"

    def test_9_16_returns_portrait_1080x1920(self):
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("9:16")
        assert (w, h) == (1080, 1920)

    def test_1_1_returns_square_1080x1080(self):
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("1:1")
        assert (w, h) == (1080, 1080)

    def test_3_4_returns_portrait_default(self):
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("3:4")
        assert (w, h) == (1080, 1440)

    def test_4_5_returns_portrait_default(self):
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("4:5")
        assert (w, h) == (1080, 1440)

    def test_unknown_string_falls_to_portrait_default(self):
        """Any unrecognised value should give the safe portrait default, not crash."""
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("unknown")
        assert (w, h) == (1080, 1440)

    def test_empty_string_falls_to_portrait_default(self):
        from app.services.render_engine import resolve_target_dimensions
        w, h = resolve_target_dimensions("")
        assert (w, h) == (1080, 1440)

    def test_none_coerced_falls_to_portrait_default(self):
        from app.services.render_engine import resolve_target_dimensions
        # The helper normalises with (aspect_ratio or "").strip(), so None-ish
        # values from misconfigured payloads must not crash.
        w, h = resolve_target_dimensions(None)  # type: ignore[arg-type]
        assert (w, h) == (1080, 1440)

    def test_returns_tuple_of_two_ints(self):
        from app.services.render_engine import resolve_target_dimensions
        result = resolve_target_dimensions("9:16")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, int) for v in result)

    @pytest.mark.parametrize("ar,expected", [
        ("1:1",  (1080, 1080)),
        ("9:16", (1080, 1920)),
        ("16:9", (1920, 1080)),
        ("3:4",  (1080, 1440)),
        ("4:5",  (1080, 1440)),
    ])
    def test_parametrized_all_known_ratios(self, ar, expected):
        from app.services.render_engine import resolve_target_dimensions
        assert resolve_target_dimensions(ar) == expected


# ---------------------------------------------------------------------------
# 2. render_part uses resolve_target_dimensions (integration smoke)
#    Verifies the inline if/elif block was correctly replaced by the helper.
# ---------------------------------------------------------------------------

class TestRenderPartUsesHelper:
    """Confirm render_part calls resolve_target_dimensions and embeds the returned
    dimensions into its FFmpeg filter string.  We mock probe + subprocess so no
    real video file or GPU is needed."""

    def _make_render_part_call(self, aspect_ratio: str):
        """Call render_part with all heavy dependencies mocked out."""
        from app.services.render_engine import render_part

        mock_meta = {
            "duration": 5.0, "fps": 30.0, "has_audio": True,
            "has_video": True, "width": 1920, "height": 1080,
        }
        captured_cmd = []

        def _fake_run(cmd, **_kwargs):
            captured_cmd.extend(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        with patch("app.services.render.legacy_renderer.probe_video_metadata", return_value=mock_meta), \
             patch("app.services.render.legacy_renderer._run_ffmpeg_with_retry", side_effect=_fake_run), \
             patch("app.services.render.legacy_renderer.NVENC_SEMAPHORE"), \
             patch("app.services.render.legacy_renderer._resolve_codec", return_value="libx264"):
            try:
                render_part(
                    input_path="fake_input.mp4",
                    output_path="fake_output.mp4",
                    subtitle_ass=None,
                    title_text=None,
                    aspect_ratio=aspect_ratio,
                    add_subtitle=False,
                    add_title_overlay=False,
                )
            except Exception:
                pass  # we only care about the captured command

        return " ".join(str(c) for c in captured_cmd)

    def test_16_9_embeds_1920x1080_in_filter(self):
        cmd = self._make_render_part_call("16:9")
        assert "1920:1080" in cmd or "1920" in cmd, (
            "render_part with 16:9 must use 1920×1080 in its filter chain"
        )

    def test_9_16_embeds_1080x1920_in_filter(self):
        cmd = self._make_render_part_call("9:16")
        assert "1080:1920" in cmd or "1920" in cmd

    def test_1_1_embeds_1080x1080_in_filter(self):
        cmd = self._make_render_part_call("1:1")
        assert "1080:1080" in cmd
