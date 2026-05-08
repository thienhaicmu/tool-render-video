"""
test_render_audit_p0_fixes.py — P0 regression checklist tied to render_audit.md.

Verifies the three P0 bugs identified in docs/review/render_audit.md are fixed
and stay fixed. Each test cites the audit section that prompted the fix.

Audit reference: docs/review/render_audit.md — Top 5 Risks, items 1-3.
Patch: commit 88c67a1 "P0-P1 render stability, validation, encoder unification"

No real video file, FFmpeg subprocess, or GPU required.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fix 1 — 16:9 render dimension branch
# Audit ref: "render_part() aspect_ratio '16:9' falls to else branch → 1080×1440"
# Fix: resolve_target_dimensions() extracted from render_part() with explicit 16:9 branch.
# ---------------------------------------------------------------------------

class TestAspectRatioDimensions:
    """P0 guard: every supported aspect_ratio must produce the correct canvas size."""

    def _dims(self, ar: str):
        from app.services.render_engine import resolve_target_dimensions
        return resolve_target_dimensions(ar)

    def test_16_9_is_landscape_1920x1080(self):
        """Core P0 fix: '16:9' must NOT fall to the 1080×1440 else branch."""
        w, h = self._dims("16:9")
        assert (w, h) == (1920, 1080), (
            f"16:9 produced {w}x{h} — portrait fallback regression"
        )

    def test_9_16_is_portrait_1080x1920(self):
        w, h = self._dims("9:16")
        assert (w, h) == (1080, 1920)

    def test_1_1_is_square_1080x1080(self):
        w, h = self._dims("1:1")
        assert (w, h) == (1080, 1080)

    def test_3_4_is_portrait_default_1080x1440(self):
        w, h = self._dims("3:4")
        assert (w, h) == (1080, 1440)

    def test_unknown_falls_to_portrait_default(self):
        """Unrecognised values must silently fall to 1080×1440, not crash."""
        w, h = self._dims("unknown_ratio")
        assert (w, h) == (1080, 1440)

    @pytest.mark.parametrize("ar,expected", [
        ("1:1",  (1080, 1080)),
        ("9:16", (1080, 1920)),
        ("16:9", (1920, 1080)),
        ("3:4",  (1080, 1440)),
    ])
    def test_all_documented_ratios(self, ar, expected):
        assert self._dims(ar) == expected


# ---------------------------------------------------------------------------
# Fix 2 — motion_crop codec flags maxrate/bufsize
# Audit ref: "motion_crop._codec_flags() missing -maxrate 20M -bufsize 40M"
# Fix: _codec_flags() CPU paths delegate to encoder_helpers.codec_extra_flags
#      which includes -maxrate 20M -bufsize 40M for libx264 and libx265.
# ---------------------------------------------------------------------------

class TestMotionCropCodecFlags:
    """P0 guard: software encoder paths in motion_crop must include delivery-safe
    bitrate caps to prevent unbounded VBR spikes on social-media platforms."""

    def _flags(self, codec: str) -> list[str]:
        from app.services.motion_crop import _codec_flags
        return _codec_flags(codec, video_crf=18)

    def test_libx264_has_maxrate_20M(self):
        flags = self._flags("libx264")
        assert "-maxrate" in flags
        idx = flags.index("-maxrate")
        assert flags[idx + 1] == "20M"

    def test_libx264_has_bufsize_40M(self):
        flags = self._flags("libx264")
        assert "-bufsize" in flags
        idx = flags.index("-bufsize")
        assert flags[idx + 1] == "40M"

    def test_libx265_has_maxrate_20M(self):
        flags = self._flags("libx265")
        assert "-maxrate" in flags
        idx = flags.index("-maxrate")
        assert flags[idx + 1] == "20M"

    def test_libx265_has_bufsize_40M(self):
        flags = self._flags("libx265")
        assert "-bufsize" in flags
        idx = flags.index("-bufsize")
        assert flags[idx + 1] == "40M"

    def test_maxrate_comes_before_bufsize_libx264(self):
        """FFmpeg requires -maxrate before -bufsize in the argument list."""
        flags = self._flags("libx264")
        assert flags.index("-maxrate") < flags.index("-bufsize")

    def test_maxrate_comes_before_bufsize_libx265(self):
        flags = self._flags("libx265")
        assert flags.index("-maxrate") < flags.index("-bufsize")


# ---------------------------------------------------------------------------
# Fix 3 — body crop center formula
# Audit ref: "_subject_to_crop_center() uses cy = y + h * 0.34 for body (wrong)"
# Fix: body branch now uses h * 0.50 (visual mid-body), face keeps h * 0.34.
# ---------------------------------------------------------------------------

class TestBodyCropCenterFormula:
    """P0 guard: body subjects must be framed at mid-body (h*0.50), not face-bias (h*0.34)."""

    # Subject in a 1080×1920 frame — ratio≈0.058, no ratio-correction branch triggered.
    _SUBJECT = (200, 600, 300, 400)
    _CALL_KW = dict(crop_w=608, crop_h=1080, frame_w=1080, frame_h=1920, padding=0.1)

    def _cy(self, subject_kind: str) -> float:
        from app.services.motion_crop import _subject_to_crop_center
        x, y, w, h = self._SUBJECT
        _, cy = _subject_to_crop_center(
            self._SUBJECT, subject_kind=subject_kind, **self._CALL_KW
        )
        return cy

    def test_body_cy_is_y_plus_h_times_0_50(self):
        x, y, w, h = self._SUBJECT
        cy = self._cy("body")
        assert abs(cy - (y + h * 0.50)) < 1.0, (
            f"body cy={cy:.2f}, expected {y + h * 0.50:.2f}"
        )

    def test_face_cy_is_y_plus_h_times_0_34(self):
        x, y, w, h = self._SUBJECT
        cy = self._cy("face")
        assert abs(cy - (y + h * 0.34)) < 1.0, (
            f"face cy={cy:.2f}, expected {y + h * 0.34:.2f}"
        )

    def test_body_cy_strictly_greater_than_face_cy(self):
        """Body center must be lower in the frame than face center."""
        assert self._cy("body") > self._cy("face")
