"""
test_timeline_map.py — Unit tests for TimelineMap.

Coverage:
- 1.0x duration mapping
- 1.15x duration mapping (default TikTok profile)
- source_to_output() coordinate transform
- output_to_source() coordinate transform
- inverse round-trip
- speed clamping at min and max
- trim_offset handling
- to_dict() / from_dict() round-trip
"""
from __future__ import annotations

import pytest

from app.domain.timeline import TimelineMap, _SPEED_MIN, _SPEED_MAX


class TestTimelineMapBasicDuration:
    def test_1x_source_equals_output(self):
        tl = TimelineMap(source_start=10.0, source_end=40.0, effective_speed=1.0)
        assert tl.source_duration == pytest.approx(30.0)
        assert tl.output_duration == pytest.approx(30.0)

    def test_115x_output_shorter(self):
        tl = TimelineMap(source_start=10.0, source_end=40.0, effective_speed=1.15)
        assert tl.source_duration == pytest.approx(30.0)
        assert tl.output_duration == pytest.approx(30.0 / 1.15, rel=1e-6)

    def test_107_plus_008_tiktok_default(self):
        """Default TikTok: payload 1.07 + platform delta 0.08 = 1.15."""
        speed = 1.07 + 0.08
        tl = TimelineMap(source_start=0.0, source_end=60.0, effective_speed=speed)
        assert tl.output_duration == pytest.approx(60.0 / 1.15, rel=1e-6)

    def test_slow_speed_output_longer(self):
        tl = TimelineMap(source_start=0.0, source_end=30.0, effective_speed=0.75)
        assert tl.output_duration == pytest.approx(30.0 / 0.75)

    def test_zero_duration_clip(self):
        tl = TimelineMap(source_start=10.0, source_end=10.0, effective_speed=1.15)
        assert tl.source_duration == pytest.approx(0.0)
        assert tl.output_duration == pytest.approx(0.0)

    def test_source_end_before_start_clamps_to_zero(self):
        tl = TimelineMap(source_start=20.0, source_end=10.0, effective_speed=1.0)
        assert tl.source_duration == pytest.approx(0.0)
        assert tl.output_duration == pytest.approx(0.0)


class TestTimelineMapCoordinateTransforms:
    def _tl(self, speed: float) -> TimelineMap:
        return TimelineMap(source_start=10.0, source_end=40.0, effective_speed=speed)

    def test_source_to_output_at_1x(self):
        tl = self._tl(1.0)
        assert tl.source_to_output(0.0) == pytest.approx(0.0)
        assert tl.source_to_output(15.0) == pytest.approx(15.0)
        assert tl.source_to_output(30.0) == pytest.approx(30.0)

    def test_source_to_output_at_115x(self):
        tl = self._tl(1.15)
        assert tl.source_to_output(0.0) == pytest.approx(0.0)
        assert tl.source_to_output(15.0) == pytest.approx(15.0 / 1.15, rel=1e-6)
        assert tl.source_to_output(30.0) == pytest.approx(30.0 / 1.15, rel=1e-6)

    def test_output_to_source_at_1x(self):
        tl = self._tl(1.0)
        assert tl.output_to_source(0.0) == pytest.approx(0.0)
        assert tl.output_to_source(15.0) == pytest.approx(15.0)

    def test_output_to_source_at_115x(self):
        tl = self._tl(1.15)
        assert tl.output_to_source(10.0) == pytest.approx(10.0 * 1.15, rel=1e-6)

    def test_inverse_round_trip_at_115x(self):
        tl = self._tl(1.15)
        for t in [0.0, 5.0, 14.99, 30.0]:
            recovered = tl.output_to_source(tl.source_to_output(t))
            assert recovered == pytest.approx(t, rel=1e-9), (
                f"Round-trip failed for t={t}: got {recovered}"
            )

    def test_inverse_round_trip_at_075x(self):
        tl = self._tl(0.75)
        for t in [0.0, 10.0, 29.0]:
            recovered = tl.output_to_source(tl.source_to_output(t))
            assert recovered == pytest.approx(t, rel=1e-9)


class TestTimelineMapSpeedClamping:
    def test_speed_below_min_clamped(self):
        tl = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=0.1)
        assert tl.effective_speed == pytest.approx(_SPEED_MIN)

    def test_speed_above_max_clamped(self):
        tl = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=5.0)
        assert tl.effective_speed == pytest.approx(_SPEED_MAX)  # 1.5

    def test_speed_at_min_boundary(self):
        tl = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=_SPEED_MIN)
        assert tl.effective_speed == pytest.approx(_SPEED_MIN)

    def test_speed_at_max_boundary(self):
        tl = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=_SPEED_MAX)
        assert tl.effective_speed == pytest.approx(_SPEED_MAX)  # 1.5

    def test_output_duration_uses_clamped_speed(self):
        tl = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=999.0)
        assert tl.output_duration == pytest.approx(10.0 / _SPEED_MAX)  # 10.0 / 1.5


class TestTimelineMapTrimOffset:
    def test_trim_offset_reduces_source_duration(self):
        # segment: 10s–40s, 2s silence trim → effective_start = 12s
        tl = TimelineMap(source_start=12.0, source_end=40.0, effective_speed=1.0, trim_offset=2.0)
        assert tl.source_duration == pytest.approx(28.0)
        assert tl.trim_offset == pytest.approx(2.0)

    def test_zero_trim_offset_default(self):
        tl = TimelineMap(source_start=10.0, source_end=40.0, effective_speed=1.0)
        assert tl.trim_offset == pytest.approx(0.0)

    def test_trim_and_speed_together(self):
        tl = TimelineMap(source_start=12.0, source_end=40.0, effective_speed=1.15, trim_offset=2.0)
        assert tl.source_duration == pytest.approx(28.0)
        assert tl.output_duration == pytest.approx(28.0 / 1.15, rel=1e-6)


class TestTimelineMapSerialization:
    def _sample(self) -> TimelineMap:
        return TimelineMap(
            source_start=10.5,
            source_end=42.0,
            effective_speed=1.15,
            trim_offset=1.2,
        )

    def test_to_dict_contains_all_fields(self):
        d = self._sample().to_dict()
        required = {
            "source_start", "source_end", "source_duration",
            "effective_speed", "trim_offset", "output_duration",
        }
        assert required.issubset(d.keys())

    def test_to_dict_values_correct(self):
        tl = self._sample()
        d = tl.to_dict()
        assert d["source_start"] == pytest.approx(10.5)
        assert d["source_end"] == pytest.approx(42.0)
        assert d["effective_speed"] == pytest.approx(1.15)
        assert d["trim_offset"] == pytest.approx(1.2)
        assert d["source_duration"] == pytest.approx(31.5)
        assert d["output_duration"] == pytest.approx(31.5 / 1.15, rel=1e-6)

    def test_from_dict_round_trip(self):
        original = self._sample()
        restored = TimelineMap.from_dict(original.to_dict())
        assert restored.source_start == pytest.approx(original.source_start)
        assert restored.source_end == pytest.approx(original.source_end)
        assert restored.effective_speed == pytest.approx(original.effective_speed)
        assert restored.trim_offset == pytest.approx(original.trim_offset)
        assert restored.source_duration == pytest.approx(original.source_duration)
        assert restored.output_duration == pytest.approx(original.output_duration)

    def test_from_dict_missing_trim_offset_defaults_to_zero(self):
        d = self._sample().to_dict()
        del d["trim_offset"]
        tl = TimelineMap.from_dict(d)
        assert tl.trim_offset == pytest.approx(0.0)

    def test_to_dict_all_values_are_json_serializable(self):
        import json
        d = self._sample().to_dict()
        json.dumps(d)  # must not raise
