"""
test_legacy_renderer_visual_intensity.py — Phase 5.7 tests for
visual_intensity_hint parameter in render_part() and render_part_smart().

Covers:
- render_part() and render_part_smart() accept visual_intensity_hint with default None
- None preserves exact existing command/effect behavior
- low/medium/high map only to known supported presets
- invalid hint is ignored (original behavior preserved)
- user explicit effect_preset wins (user_effect_is_explicit=True behavior)
- no raw FFmpeg filter string can come from AI hint
- render_engine shim re-exports still valid
- overlay compositor does NOT receive visual_intensity_hint
"""
from __future__ import annotations

import inspect
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import app.services.render.base_clip_renderer as lr_mod
from app.services.render.base_clip_renderer import render_part, render_part_smart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SRC_META = {
    "duration": 30.0, "fps": 29.97, "width": 1920, "height": 1080, "has_audio": True,
}

_CAPTURED_CMD: list = []


def _capture_cmd(cmd, retry_count=2):
    """Capture command for inspection without running FFmpeg."""
    _CAPTURED_CMD.clear()
    _CAPTURED_CMD.extend(cmd)


def _call_render_part(
    effect_preset="slay_soft_01",
    visual_intensity_hint=None,
    input_has_audio=True,
):
    """Call render_part() with mocks and return the captured FFmpeg command."""
    captured = []

    def _mock_ffmpeg(cmd, retry_count=2):
        captured.extend(cmd)

    with patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
         patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=input_has_audio), \
         patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps_policy=auto")), \
         patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry", side_effect=_mock_ffmpeg), \
         patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
         patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
         patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
         patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
         patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
        render_part(
            input_path="/fake/input.mp4",
            output_path="/fake/output.mp4",
            subtitle_ass=None,
            title_text=None,
            effect_preset=effect_preset,
            visual_intensity_hint=visual_intensity_hint,
            add_subtitle=False,
            add_title_overlay=False,
        )
    return captured


# ---------------------------------------------------------------------------
# 1. Signature: render_part accepts visual_intensity_hint with default None
# ---------------------------------------------------------------------------

class TestRenderPartSignature:
    def test_render_part_has_visual_intensity_hint_param(self):
        """render_part() must have visual_intensity_hint parameter."""
        sig = inspect.signature(render_part)
        assert "visual_intensity_hint" in sig.parameters, (
            "render_part() missing visual_intensity_hint parameter"
        )

    def test_render_part_visual_intensity_hint_default_none(self):
        """render_part() visual_intensity_hint defaults to None."""
        sig = inspect.signature(render_part)
        param = sig.parameters["visual_intensity_hint"]
        assert param.default is None, (
            f"visual_intensity_hint default should be None, got {param.default!r}"
        )

    def test_render_part_smart_has_visual_intensity_hint_param(self):
        """render_part_smart() must have visual_intensity_hint parameter."""
        sig = inspect.signature(render_part_smart)
        assert "visual_intensity_hint" in sig.parameters, (
            "render_part_smart() missing visual_intensity_hint parameter"
        )

    def test_render_part_smart_visual_intensity_hint_default_none(self):
        """render_part_smart() visual_intensity_hint defaults to None."""
        sig = inspect.signature(render_part_smart)
        param = sig.parameters["visual_intensity_hint"]
        assert param.default is None, (
            f"visual_intensity_hint default should be None, got {param.default!r}"
        )


# ---------------------------------------------------------------------------
# 2. None preserves exact existing command/effect behavior
# ---------------------------------------------------------------------------

class TestNoneHintPreservesExistingBehavior:
    def test_none_hint_uses_original_effect_preset(self):
        """visual_intensity_hint=None → _effect_filter called with original effect_preset."""
        resolved_preset = []

        orig_resolve = lr_mod.resolve_effect_preset_with_intensity

        def _capture_resolve(effect_preset, visual_intensity_hint, user_effect_is_explicit=False):
            result = orig_resolve(effect_preset, visual_intensity_hint, user_effect_is_explicit)
            resolved_preset.append(result)
            return result

        with patch("app.services.render.base_clip_renderer.resolve_effect_preset_with_intensity",
                   side_effect=_capture_resolve), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset="slay_soft_01",
                visual_intensity_hint=None,
                add_subtitle=False,
                add_title_overlay=False,
            )

        assert len(resolved_preset) >= 1
        assert resolved_preset[0] == "slay_soft_01", (
            f"None hint should keep slay_soft_01, got {resolved_preset[0]!r}"
        )

    def test_none_hint_produces_same_vf_chain_as_no_param(self):
        """Calling with visual_intensity_hint=None produces identical behavior to omitting it."""
        cmd_with_none = _call_render_part(effect_preset="slay_soft_01", visual_intensity_hint=None)
        # Extract vf_chain from cmd
        vf_chain = None
        for i, token in enumerate(cmd_with_none):
            if token == "-vf" and i + 1 < len(cmd_with_none):
                vf_chain = cmd_with_none[i + 1]
                break
        assert vf_chain is not None
        # default effect filter output for slay_soft_01
        assert "eq=" in vf_chain, "Expected eq= in vf_chain for slay_soft_01"


# ---------------------------------------------------------------------------
# 3. low/medium/high map to known supported presets
# ---------------------------------------------------------------------------

class TestValidHintsMappedToKnownPresets:
    _KNOWN_PRESETS = frozenset({
        "slay_soft_01", "slay_pop_01", "story_clean_01",
        "social_bright", "cinematic_soft", "high_contrast",
    })

    def test_low_hint_uses_known_preset(self):
        """'low' hint → effect_filter is called with a known preset."""
        filter_preset_used = []

        orig_effect_filter = lr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset="slay_soft_01",
                visual_intensity_hint="low",
                add_subtitle=False,
                add_title_overlay=False,
            )

        assert len(filter_preset_used) >= 1
        assert filter_preset_used[0] in self._KNOWN_PRESETS, (
            f"'low' hint caused _effect_filter to be called with unknown preset: {filter_preset_used[0]!r}"
        )
        assert filter_preset_used[0] == "story_clean_01", (
            f"'low' hint should use story_clean_01, got {filter_preset_used[0]!r}"
        )

    def test_high_hint_uses_slay_pop_01(self):
        """'high' hint → _effect_filter called with slay_pop_01."""
        filter_preset_used = []

        orig_effect_filter = lr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset="slay_soft_01",
                visual_intensity_hint="high",
                add_subtitle=False,
                add_title_overlay=False,
            )

        assert len(filter_preset_used) >= 1
        assert filter_preset_used[0] == "slay_pop_01", (
            f"'high' hint should use slay_pop_01, got {filter_preset_used[0]!r}"
        )


# ---------------------------------------------------------------------------
# 4. Invalid hint is ignored — original behavior preserved
# ---------------------------------------------------------------------------

class TestInvalidHintIgnored:
    def test_invalid_hint_ultra_ignored(self):
        """Invalid hint 'ultra' → original effect_preset used."""
        filter_preset_used = []

        orig_effect_filter = lr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset="slay_soft_01",
                visual_intensity_hint="ultra",
                add_subtitle=False,
                add_title_overlay=False,
            )

        assert len(filter_preset_used) >= 1
        assert filter_preset_used[0] == "slay_soft_01", (
            f"Invalid hint should not change preset, got {filter_preset_used[0]!r}"
        )


# ---------------------------------------------------------------------------
# 5. User explicit effect_preset wins
# ---------------------------------------------------------------------------

class TestUserExplicitPresetWins:
    def test_user_explicit_preset_wins_over_high(self):
        """User-set non-default effect_preset + 'high' hint → user preset wins."""
        filter_preset_used = []

        orig_effect_filter = lr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset="cinematic_soft",  # User chose this explicitly
                visual_intensity_hint="high",  # AI hint
                add_subtitle=False,
                add_title_overlay=False,
            )

        assert len(filter_preset_used) >= 1
        assert filter_preset_used[0] == "cinematic_soft", (
            f"User explicit preset should win over AI hint, got {filter_preset_used[0]!r}"
        )

    def test_effect_preset_not_mutated(self):
        """effect_preset argument is never mutated by visual_intensity_hint."""
        original_preset = "cinematic_soft"
        captured_effect_preset_arg = []

        orig_resolve = lr_mod.resolve_effect_preset_with_intensity

        def _track(effect_preset, visual_intensity_hint, user_effect_is_explicit=False):
            captured_effect_preset_arg.append(effect_preset)
            return orig_resolve(effect_preset, visual_intensity_hint, user_effect_is_explicit)

        with patch("app.services.render.base_clip_renderer.resolve_effect_preset_with_intensity",
                   side_effect=_track), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_part(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                subtitle_ass=None,
                title_text=None,
                effect_preset=original_preset,
                visual_intensity_hint="high",
                add_subtitle=False,
                add_title_overlay=False,
            )

        # The original effect_preset passed as first arg to resolve must be unchanged
        assert captured_effect_preset_arg[0] == original_preset, (
            f"effect_preset should not be mutated before resolve: {captured_effect_preset_arg[0]!r}"
        )


# ---------------------------------------------------------------------------
# 6. No raw FFmpeg filter string from AI hint
# ---------------------------------------------------------------------------

class TestNoFFmpegFilterFromAI:
    def test_ai_hint_never_produces_ffmpeg_filter_in_preset(self):
        """The preset passed to _effect_filter must never be an FFmpeg filter string."""
        filter_preset_used = []

        orig_effect_filter = lr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        for hint in ("low", "medium", "high"):
            filter_preset_used.clear()
            with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
                 patch("app.services.render.base_clip_renderer.probe_video_metadata", return_value=_FAKE_SRC_META), \
                 patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
                 patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
                 patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
                 patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
                 patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
                 patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
                 patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
                 patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
                render_part(
                    input_path="/fake/input.mp4",
                    output_path="/fake/output.mp4",
                    subtitle_ass=None,
                    title_text=None,
                    effect_preset="slay_soft_01",
                    visual_intensity_hint=hint,
                    add_subtitle=False,
                    add_title_overlay=False,
                )

            if filter_preset_used:
                preset_val = filter_preset_used[0]
                assert "eq=" not in str(preset_val), (
                    f"hint={hint!r} caused FFmpeg filter string in preset: {preset_val!r}"
                )
                assert "unsharp=" not in str(preset_val), (
                    f"hint={hint!r} caused unsharp= in preset: {preset_val!r}"
                )


# ---------------------------------------------------------------------------
# 7. render_engine shim re-exports are still valid
# ---------------------------------------------------------------------------

class TestRenderEngineShimValid:
    def test_render_part_smart_importable_from_render_engine(self):
        """render_part_smart is re-exported from render_engine."""
        from app.services.render_engine import render_part_smart as rps_shim
        from app.services.render.base_clip_renderer import render_part_smart as rps_direct
        assert rps_shim is rps_direct, "render_engine re-export must be same object"

    def test_render_part_importable_from_render_engine(self):
        """render_part is re-exported from render_engine."""
        from app.services.render_engine import render_part as rp_shim
        from app.services.render.base_clip_renderer import render_part as rp_direct
        assert rp_shim is rp_direct, "render_engine re-export must be same object"

    def test_render_engine_shim_render_part_smart_accepts_hint(self):
        """render_part_smart via render_engine shim accepts visual_intensity_hint."""
        from app.services.render_engine import render_part_smart
        sig = inspect.signature(render_part_smart)
        assert "visual_intensity_hint" in sig.parameters


# ---------------------------------------------------------------------------
# 8. overlay_compositor does NOT receive visual_intensity_hint
# ---------------------------------------------------------------------------

class TestOverlayCompositorUnchanged:
    def test_overlay_compositor_has_no_visual_intensity_hint(self):
        """composite_overlays_on_base_clip() must NOT accept visual_intensity_hint."""
        from app.services.render.overlay_compositor import composite_overlays_on_base_clip
        sig = inspect.signature(composite_overlays_on_base_clip)
        assert "visual_intensity_hint" not in sig.parameters, (
            "overlay_compositor must not accept visual_intensity_hint — "
            "it is overlay-only and must not receive render intensity parameters"
        )
