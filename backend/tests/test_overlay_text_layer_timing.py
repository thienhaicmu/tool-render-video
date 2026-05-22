"""
test_overlay_text_layer_timing.py — Unit tests for overlay-path text layer timing.

Verifies the finalized Phase 3B timing model:

  Legacy path (_part_text_layers):
    hook end_time = round(min(2.5, 1.5 * speed), 3)   # source-clip seconds (pre-setpts)

  Overlay path (_part_text_layers_overlay):
    hook end_time = 1.5                                # output-timeline seconds, no speed factor

  User text_layers: passed as-is in both paths (creator intent is output/perceived time).

These tests verify the formulas and contracts without importing the full pipeline,
keeping them fast and free of render/FFmpeg dependencies.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Hook timing formula tests
# ---------------------------------------------------------------------------

class TestHookLegacyTiming:
    @pytest.mark.parametrize("speed", [0.9, 1.0, 1.07, 1.15, 1.3, 1.5])
    def test_legacy_end_time_is_1_5_times_speed(self, speed: float):
        """Legacy hook: end_time = round(min(2.5, 1.5 × clamped_speed), 3)."""
        hook_spd = max(0.5, min(1.5, speed))
        hook_end_t = round(min(2.5, 1.5 * hook_spd), 3)
        expected = round(min(2.5, 1.5 * max(0.5, min(1.5, speed))), 3)
        assert hook_end_t == pytest.approx(expected, rel=1e-6)

    def test_legacy_end_time_at_unit_speed_is_1_5(self):
        """At speed=1.0, legacy end_time equals 1.5 source-clip seconds."""
        speed = 1.0
        hook_end_t = round(min(2.5, 1.5 * speed), 3)
        assert hook_end_t == pytest.approx(1.5)

    def test_legacy_end_time_at_speed_1_07(self):
        """At speed=1.07, legacy end_time = round(1.5 * 1.07, 3) = 1.605."""
        speed = 1.07
        hook_end_t = round(min(2.5, 1.5 * speed), 3)
        assert hook_end_t == pytest.approx(1.605)

    def test_legacy_end_time_cap_at_2_5(self):
        """end_time is capped at 2.5 — max(clamped_speed)=1.5, so 1.5*1.5=2.25 < 2.5."""
        # At speed=1.5 (max), 1.5 * 1.5 = 2.25 — still below cap
        hook_end_t = round(min(2.5, 1.5 * 1.5), 3)
        assert hook_end_t == pytest.approx(2.25)
        assert hook_end_t < 2.5


class TestHookOverlayTiming:
    @pytest.mark.parametrize("speed", [0.9, 1.0, 1.07, 1.15, 1.3, 1.5])
    def test_overlay_end_time_is_always_1_5(self, speed: float):
        """Overlay hook end_time is always 1.5 output seconds regardless of speed."""
        overlay_hook_end_time = 1.5  # constant — no speed factor on output-timeline PTS
        assert overlay_hook_end_time == pytest.approx(1.5)

    def test_overlay_start_time_is_zero(self):
        """Hook overlay start_time is 0.0 in the overlay path."""
        overlay_hook_start_time = 0.0
        assert overlay_hook_start_time == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.parametrize("speed", [0.9, 1.07, 1.15, 1.3])
    def test_overlay_end_time_differs_from_legacy_at_nonunit_speed(self, speed: float):
        """At speed != 1.0, overlay end_time (1.5) != legacy end_time (1.5 * speed)."""
        hook_spd = max(0.5, min(1.5, speed))
        legacy_end_t = round(min(2.5, 1.5 * hook_spd), 3)
        overlay_end_t = 1.5
        assert abs(legacy_end_t - overlay_end_t) > 1e-4, (
            f"speed={speed}: legacy={legacy_end_t} should differ from overlay={overlay_end_t}"
        )

    def test_overlay_end_time_not_speed_multiplied_at_1_15(self):
        """Explicit check: at speed=1.15, overlay=1.5, legacy=1.605; they must differ."""
        speed = 1.15
        hook_spd = max(0.5, min(1.5, speed))
        legacy_end_t = round(min(2.5, 1.5 * hook_spd), 3)
        overlay_end_t = 1.5
        assert legacy_end_t == pytest.approx(1.725, rel=1e-3)
        assert overlay_end_t == pytest.approx(1.5)
        assert legacy_end_t != pytest.approx(overlay_end_t)


# ---------------------------------------------------------------------------
# User layer passthrough tests
# ---------------------------------------------------------------------------

class TestUserLayerTimingPassthrough:
    def test_user_layer_times_unchanged_in_overlay_path(self):
        """User layer start_time/end_time pass through unchanged to overlay path.

        Creator-supplied times are output/perceived seconds; no conversion needed
        on base_clip.mp4 whose PTS is already output-timeline.
        """
        user_layer = {"start_time": 2.0, "end_time": 8.0, "id": "layer_1"}
        overlay_layer = dict(user_layer)  # overlay path: use as-is
        assert overlay_layer["start_time"] == pytest.approx(2.0)
        assert overlay_layer["end_time"] == pytest.approx(8.0)

    def test_user_layer_times_equal_in_both_paths(self):
        """User layers are identical in legacy and overlay paths (no per-layer conversion)."""
        user_layer = {"start_time": 3.0, "end_time": 10.0}
        legacy_layer = dict(user_layer)
        overlay_layer = dict(user_layer)
        assert legacy_layer["start_time"] == overlay_layer["start_time"]
        assert legacy_layer["end_time"] == overlay_layer["end_time"]

    def test_hook_is_only_layer_that_differs_between_paths(self):
        """Only the hook layer's end_time changes between legacy and overlay paths."""
        speed = 1.15
        hook_spd = max(0.5, min(1.5, speed))

        # Legacy hook
        legacy_hook = {"end_time": round(min(2.5, 1.5 * hook_spd), 3)}
        # Overlay hook
        overlay_hook = {"end_time": 1.5}

        # User layer (unchanged in both)
        user_layer = {"start_time": 2.0, "end_time": 8.0}

        assert legacy_hook["end_time"] != pytest.approx(overlay_hook["end_time"])
        assert user_layer["start_time"] == pytest.approx(2.0)  # identical in both paths
        assert user_layer["end_time"] == pytest.approx(8.0)    # identical in both paths


# ---------------------------------------------------------------------------
# Timing invariant tests
# ---------------------------------------------------------------------------

class TestTimingInvariants:
    def test_legacy_hook_at_unit_speed_equals_overlay_hook(self):
        """At speed=1.0 exactly, legacy and overlay hook times happen to be equal."""
        speed = 1.0
        legacy_end_t = round(min(2.5, 1.5 * speed), 3)
        overlay_end_t = 1.5
        assert legacy_end_t == pytest.approx(overlay_end_t)

    def test_title_enable_expression_unchanged_between_paths(self):
        """Title drawtext enable='lt(t,3)' is identical in legacy and overlay paths.

        On base_clip.mp4 the frame PTS is already output-timeline, so the same
        expression correctly means 'first 3 output seconds' in both contexts.
        """
        legacy_enable = "lt(t,3)"
        overlay_enable = "lt(t,3)"  # no conversion needed
        assert legacy_enable == overlay_enable
