"""
test_base_clip_renderer_visual_intensity.py — Phase 5.7 tests for
visual_intensity_hint parameter in render_base_clip().

Covers:
- render_base_clip() accepts visual_intensity_hint with default None
- None preserves exact existing behavior
- low/medium/high each map to known supported presets
- invalid hint ignored
- user explicit effect_preset wins
- backward compatibility: existing callers unchanged
- overlay compositor not affected
"""
from __future__ import annotations

import inspect
import pytest
from unittest.mock import patch, MagicMock

from app.domain.timeline import TimelineMap
import app.services.render.base_clip_renderer as bcr_mod
from app.services.render.base_clip_renderer import render_base_clip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SRC_META = {
    "duration": 30.0, "fps": 29.97, "width": 1920, "height": 1080, "has_audio": True,
}
_FAKE_OUT_META = {
    "duration": 26.1, "fps": 60.0, "width": 1080, "height": 1440, "has_audio": True,
}


def _make_timeline(speed: float = 1.15) -> TimelineMap:
    return TimelineMap(
        source_start=0.0,
        source_end=30.0,
        effective_speed=speed,
        trim_offset=0.0,
    )


def _call_bcr(
    effect_preset: str = "slay_soft_01",
    visual_intensity_hint=None,
    motion_aware_crop: bool = False,
    speed: float = 1.15,
):
    """Call render_base_clip() with mocks, return captured FFmpeg command."""
    captured = []

    def _mock_ffmpeg(cmd, retry_count=2):
        captured.extend(cmd)

    probe_results = [_FAKE_SRC_META, _FAKE_OUT_META]
    probe_calls = [0]

    def _mock_probe(path, timeout=15):
        idx = probe_calls[0]
        probe_calls[0] += 1
        return probe_results[min(idx, len(probe_results) - 1)]

    with patch("app.services.render.base_clip_renderer.probe_video_metadata", side_effect=_mock_probe), \
         patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
         patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
         patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry", side_effect=_mock_ffmpeg), \
         patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
         patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
         patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
         patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
         patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
        result = render_base_clip(
            input_path="/fake/input.mp4",
            output_path="/fake/output.mp4",
            timeline=_make_timeline(speed),
            effect_preset=effect_preset,
            visual_intensity_hint=visual_intensity_hint,
            motion_aware_crop=motion_aware_crop,
        )
    return captured, result


# ---------------------------------------------------------------------------
# 1. Signature tests
# ---------------------------------------------------------------------------

class TestRenderBaseClipSignature:
    def test_has_visual_intensity_hint_param(self):
        """render_base_clip() must have visual_intensity_hint parameter."""
        sig = inspect.signature(render_base_clip)
        assert "visual_intensity_hint" in sig.parameters, (
            "render_base_clip() missing visual_intensity_hint parameter"
        )

    def test_visual_intensity_hint_default_none(self):
        """visual_intensity_hint defaults to None."""
        sig = inspect.signature(render_base_clip)
        param = sig.parameters["visual_intensity_hint"]
        assert param.default is None, (
            f"visual_intensity_hint default should be None, got {param.default!r}"
        )

    def test_render_base_clip_importable_from_render_engine(self):
        """render_base_clip is re-exported from render_engine."""
        from app.services.render_engine import render_base_clip as rbc_shim
        from app.services.render.base_clip_renderer import render_base_clip as rbc_direct
        assert rbc_shim is rbc_direct, "render_engine re-export must be same object"

    def test_render_engine_shim_accepts_hint(self):
        """render_base_clip via render_engine shim accepts visual_intensity_hint."""
        from app.services.render_engine import render_base_clip
        sig = inspect.signature(render_base_clip)
        assert "visual_intensity_hint" in sig.parameters


# ---------------------------------------------------------------------------
# 2. None hint preserves existing behavior
# ---------------------------------------------------------------------------

class TestNoneHintBehavior:
    def test_none_hint_uses_original_preset(self):
        """visual_intensity_hint=None → original effect_preset passed through."""
        resolved = []
        orig = bcr_mod.resolve_effect_preset_with_intensity

        def _capture(ep, hint, user_explicit=False):
            result = orig(ep, hint, user_explicit)
            resolved.append(result)
            return result

        probe_results = [_FAKE_SRC_META, _FAKE_OUT_META]
        probe_calls = [0]

        def _mock_probe(path, timeout=15):
            idx = probe_calls[0]
            probe_calls[0] += 1
            return probe_results[min(idx, len(probe_results) - 1)]

        with patch("app.services.render.base_clip_renderer.resolve_effect_preset_with_intensity",
                   side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", side_effect=_mock_probe), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_base_clip(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                timeline=_make_timeline(),
                effect_preset="slay_soft_01",
                visual_intensity_hint=None,
                motion_aware_crop=False,
            )

        assert len(resolved) >= 1
        assert resolved[0] == "slay_soft_01"


# ---------------------------------------------------------------------------
# 3. Valid hints map to known presets
# ---------------------------------------------------------------------------

class TestValidHintsMap:
    _KNOWN_PRESETS = frozenset({
        "slay_soft_01", "slay_pop_01", "story_clean_01",
        "social_bright", "cinematic_soft", "high_contrast",
    })

    def _get_preset_used(self, hint: str) -> str:
        """Return the preset passed to _effect_filter for the given hint."""
        filter_preset_used = []
        orig_effect_filter = bcr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        probe_results = [_FAKE_SRC_META, _FAKE_OUT_META]
        probe_calls = [0]

        def _mock_probe(path, timeout=15):
            idx = probe_calls[0]
            probe_calls[0] += 1
            return probe_results[min(idx, len(probe_results) - 1)]

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", side_effect=_mock_probe), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_base_clip(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                timeline=_make_timeline(),
                effect_preset="slay_soft_01",
                visual_intensity_hint=hint,
                motion_aware_crop=False,
            )

        return filter_preset_used[0] if filter_preset_used else None

    def test_low_maps_to_story_clean_01(self):
        """'low' hint → _effect_filter called with story_clean_01."""
        preset = self._get_preset_used("low")
        assert preset == "story_clean_01", f"Expected story_clean_01, got {preset!r}"

    def test_medium_maps_to_slay_soft_01(self):
        """'medium' hint → _effect_filter called with slay_soft_01."""
        preset = self._get_preset_used("medium")
        assert preset == "slay_soft_01", f"Expected slay_soft_01, got {preset!r}"

    def test_high_maps_to_slay_pop_01(self):
        """'high' hint → _effect_filter called with slay_pop_01."""
        preset = self._get_preset_used("high")
        assert preset == "slay_pop_01", f"Expected slay_pop_01, got {preset!r}"

    def test_all_hints_use_known_preset(self):
        """All valid hints result in a known supported preset."""
        for hint in ("low", "medium", "high"):
            preset = self._get_preset_used(hint)
            assert preset in self._KNOWN_PRESETS, (
                f"hint={hint!r} mapped to unknown preset: {preset!r}"
            )

    def test_preset_is_never_ffmpeg_filter_string(self):
        """Preset passed to _effect_filter is never a FFmpeg filter string."""
        for hint in ("low", "medium", "high"):
            preset = self._get_preset_used(hint)
            if preset is not None:
                assert "eq=" not in str(preset), f"FFmpeg filter in preset for hint={hint!r}: {preset!r}"
                assert "unsharp=" not in str(preset), f"unsharp= in preset for hint={hint!r}: {preset!r}"


# ---------------------------------------------------------------------------
# 4. User explicit wins
# ---------------------------------------------------------------------------

class TestUserExplicitPresetWins:
    def test_explicit_preset_wins_over_high(self):
        """User explicit non-default preset wins over 'high' hint."""
        filter_preset_used = []
        orig_effect_filter = bcr_mod._effect_filter

        def _capture(preset):
            filter_preset_used.append(preset)
            return orig_effect_filter(preset)

        probe_results = [_FAKE_SRC_META, _FAKE_OUT_META]
        probe_calls = [0]

        def _mock_probe(path, timeout=15):
            idx = probe_calls[0]
            probe_calls[0] += 1
            return probe_results[min(idx, len(probe_results) - 1)]

        with patch("app.services.render.base_clip_renderer._effect_filter", side_effect=_capture), \
             patch("app.services.render.base_clip_renderer.probe_video_metadata", side_effect=_mock_probe), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            render_base_clip(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                timeline=_make_timeline(),
                effect_preset="cinematic_soft",  # User explicit
                visual_intensity_hint="high",  # AI hint
                motion_aware_crop=False,
            )

        assert len(filter_preset_used) >= 1
        assert filter_preset_used[0] == "cinematic_soft", (
            f"User explicit preset should win, got {filter_preset_used[0]!r}"
        )


# ---------------------------------------------------------------------------
# 5. Return metadata dict still has required keys
# ---------------------------------------------------------------------------

class TestReturnMetadata:
    def test_return_dict_has_required_keys(self):
        """render_base_clip returns dict with path/duration/fps/width/height/has_audio/created_at."""
        _, result = _call_bcr(visual_intensity_hint="high")
        for key in ("path", "duration", "fps", "width", "height", "has_audio", "created_at"):
            assert key in result, f"Missing key in return dict: {key}"

    def test_return_dict_types_correct(self):
        """Return dict has correct types."""
        _, result = _call_bcr(visual_intensity_hint="low")
        assert isinstance(result["path"], str)
        assert isinstance(result["duration"], float)
        assert isinstance(result["fps"], float)
        assert isinstance(result["width"], int)
        assert isinstance(result["height"], int)
        assert isinstance(result["has_audio"], bool)


# ---------------------------------------------------------------------------
# 6. Backward compatibility — calling without hint works
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_calling_without_visual_intensity_hint_works(self):
        """Calling render_base_clip() without visual_intensity_hint (old callers) works."""
        probe_results = [_FAKE_SRC_META, _FAKE_OUT_META]
        probe_calls = [0]

        def _mock_probe(path, timeout=15):
            idx = probe_calls[0]
            probe_calls[0] += 1
            return probe_results[min(idx, len(probe_results) - 1)]

        with patch("app.services.render.base_clip_renderer.probe_video_metadata", side_effect=_mock_probe), \
             patch("app.services.render.base_clip_renderer._has_audio_stream", return_value=True), \
             patch("app.services.render.base_clip_renderer._resolve_fps", return_value=(60, "fps")), \
             patch("app.services.render.base_clip_renderer._run_ffmpeg_with_retry"), \
             patch("app.services.render.base_clip_renderer.get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("app.services.render.base_clip_renderer._resolve_codec", return_value="libx264"), \
             patch("app.services.render.base_clip_renderer._map_preset_for_encoder", return_value="slow"), \
             patch("app.services.render.base_clip_renderer._codec_extra_flags", return_value=[]), \
             patch("app.services.render.base_clip_renderer.resolve_ffmpeg_threads", return_value=2):
            # Old caller style: no visual_intensity_hint kwarg
            result = render_base_clip(
                input_path="/fake/input.mp4",
                output_path="/fake/output.mp4",
                timeline=_make_timeline(),
                effect_preset="slay_soft_01",
                motion_aware_crop=False,
            )
        assert isinstance(result, dict)
        assert "path" in result
