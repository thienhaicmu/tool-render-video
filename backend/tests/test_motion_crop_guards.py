"""
Guard tests for motion_crop.py — covers:
  1. _subject_to_crop_center — body vs face vertical bias
  2. _codec_flags — maxrate/bufsize present for libx264 and libx265, absent for NVENC
"""

import pytest


# ---------------------------------------------------------------------------
# 1. _subject_to_crop_center — body / face center guard
# ---------------------------------------------------------------------------

class TestSubjectToCropCenter:
    """Guard against silent regression of the body-center formula.

    The body formula must use h * 0.50 (mid-body), not h * 0.34 (face bias).
    A regression here causes the body subject to be cropped to the wrong vertical region.
    """

    # Signature: _subject_to_crop_center(subject, crop_w, crop_h, frame_w, frame_h, padding,
    #                                    subtitle_safe_ratio=0.0, subject_kind="face")
    # crop_w=608, crop_h=1080 chosen so clamp bounds are [304, 776] (cx) and [540, 1380] (cy).
    # Subject (200, 600, 300, 400): ratio≈0.058 (neutral band, no ratio-correction applied);
    # face cy = 600 + 400*0.34 = 736  ∈ [540, 1380] ✓
    # body cy = 600 + 400*0.50 = 800  ∈ [540, 1380] ✓
    _SUBJECT = (200, 600, 300, 400)

    def _call(self, subject_kind: str = "face", subject=None,
              crop_w=608, crop_h=1080, frame_w=1080, frame_h=1920, padding=0.1):
        from app.services.motion_crop import _subject_to_crop_center
        s = subject if subject is not None else self._SUBJECT
        return _subject_to_crop_center(s, crop_w, crop_h, frame_w, frame_h, padding,
                                       subject_kind=subject_kind)

    def test_body_cy_uses_h_times_0_50(self):
        """Body center-y must equal y + h * 0.50 (pre-clamp formula correct).

        Subject (200, 600, 300, 400) in 1080×1920 frame: ratio≈0.058 — neutral
        band, no ratio-correction branch triggered.  Both cy values fall inside
        the [crop_h/2, frame_h-crop_h/2] clamp window so the raw formula survives.
        """
        x, y, w, h = self._SUBJECT
        _, cy = self._call("body")
        expected_cy = y + h * 0.50
        assert abs(cy - expected_cy) < 1.0, (
            f"body cy={cy:.1f}, expected y + h*0.50 = {expected_cy:.1f}"
        )

    def test_face_cy_uses_h_times_0_34(self):
        """Face center-y must equal y + h * 0.34 for the same bounding box."""
        x, y, w, h = self._SUBJECT
        _, cy = self._call("face")
        expected_cy = y + h * 0.34
        assert abs(cy - expected_cy) < 1.0, (
            f"face cy={cy:.1f}, expected y + h*0.34 = {expected_cy:.1f}"
        )

    def test_body_cy_strictly_greater_than_face_cy(self):
        """For the same bounding box, body center must be lower than face center."""
        _, cy_b = self._call("body")
        _, cy_f = self._call("face")
        assert cy_b > cy_f, (
            f"body cy={cy_b:.1f} should be > face cy={cy_f:.1f}"
        )

    def test_cx_is_horizontal_center_of_box(self):
        """Horizontal center must always be x + w/2, after clamp stays the same."""
        x, y, w, h = self._SUBJECT
        cx, _ = self._call("body")
        # cx = x + w/2 = 350, clamp bounds [304, 776] → stays at 350
        assert abs(cx - (x + w / 2.0)) < 0.01

    @pytest.mark.parametrize("kind", ["body", "face"])
    def test_returns_two_floats(self, kind):
        cx, cy = self._call(kind)
        assert isinstance(cx, float)
        assert isinstance(cy, float)


# ---------------------------------------------------------------------------
# 2. _codec_flags — maxrate / bufsize guard
# ---------------------------------------------------------------------------

class TestCodecFlags:
    """Guard that -maxrate 20M -bufsize 40M are always present for software encoders.

    These flags prevent unbounded VBR spikes on social-media delivery.
    NVENC uses a different rate-control model and must NOT have these flags.
    """

    def _flags(self, codec: str, crf: int = 18) -> list[str]:
        from app.services.motion_crop import _codec_flags
        return _codec_flags(codec, crf)

    def test_libx264_contains_maxrate(self):
        flags = self._flags("libx264")
        assert "-maxrate" in flags

    def test_libx264_maxrate_value_is_20M(self):
        flags = self._flags("libx264")
        idx = flags.index("-maxrate")
        assert flags[idx + 1] == "20M"

    def test_libx264_contains_bufsize(self):
        flags = self._flags("libx264")
        assert "-bufsize" in flags

    def test_libx264_bufsize_value_is_40M(self):
        flags = self._flags("libx264")
        idx = flags.index("-bufsize")
        assert flags[idx + 1] == "40M"

    def test_libx265_contains_maxrate(self):
        flags = self._flags("libx265")
        assert "-maxrate" in flags

    def test_libx265_maxrate_value_is_20M(self):
        flags = self._flags("libx265")
        idx = flags.index("-maxrate")
        assert flags[idx + 1] == "20M"

    def test_libx265_contains_bufsize(self):
        flags = self._flags("libx265")
        assert "-bufsize" in flags

    def test_libx265_bufsize_value_is_40M(self):
        flags = self._flags("libx265")
        idx = flags.index("-bufsize")
        assert flags[idx + 1] == "40M"

    def test_h264_nvenc_no_maxrate(self):
        """NVENC uses vbr_hq rate-control; -maxrate would conflict."""
        flags = self._flags("h264_nvenc")
        assert "-maxrate" not in flags

    def test_h264_nvenc_no_bufsize(self):
        flags = self._flags("h264_nvenc")
        assert "-bufsize" not in flags

    def test_hevc_nvenc_no_maxrate(self):
        flags = self._flags("hevc_nvenc")
        assert "-maxrate" not in flags

    @pytest.mark.parametrize("codec", ["libx264", "libx265"])
    def test_maxrate_before_bufsize(self, codec):
        """Ordering matters: FFmpeg requires -maxrate before -bufsize."""
        flags = self._flags(codec)
        assert flags.index("-maxrate") < flags.index("-bufsize")
