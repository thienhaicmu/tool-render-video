"""
test_base_clip_manifest.py — Unit tests for BaseClipManifest.

Coverage:
- Construction with all required fields
- to_dict() contains all expected keys
- from_dict() round-trip fidelity
- Optional fields (None paths) serialize correctly
- Progressive path field assignment
- Embedded TimelineMap survives serialization
"""
from __future__ import annotations

import json

import pytest

from app.domain.timeline import TimelineMap
from app.domain.manifests import BaseClipManifest


def _sample_timeline() -> TimelineMap:
    return TimelineMap(
        source_start=12.0,
        source_end=44.0,
        effective_speed=1.15,
        trim_offset=2.0,
    )


def _sample_manifest(**overrides) -> BaseClipManifest:
    defaults = dict(
        job_id="job_abc123",
        part_no=1,
        source_path="/tmp/render_job/source.mp4",
        source_start=12.0,
        source_end=44.0,
        payload_speed=1.07,
        platform="tiktok",
        platform_delta=0.08,
        effective_speed=1.15,
        variant_type=None,
        variant_speed=None,
        silence_trim_offset=1.5,
        visual_trim_offset=0.5,
        timeline=_sample_timeline(),
        ai_enabled=False,
        ai_mode=None,
        ai_selected=False,
        ai_speed_hint=None,
    )
    defaults.update(overrides)
    return BaseClipManifest(**defaults)


class TestBaseClipManifestConstruction:
    def test_construction_succeeds(self):
        m = _sample_manifest()
        assert m.job_id == "job_abc123"
        assert m.part_no == 1
        assert m.platform == "tiktok"
        assert m.cut_path is None
        assert m.srt_path is None
        assert m.ass_path is None
        assert m.narration_path is None
        assert m.rendered_path is None

    def test_timeline_embedded(self):
        m = _sample_manifest()
        assert m.timeline.source_duration == pytest.approx(32.0)
        assert m.timeline.output_duration == pytest.approx(32.0 / 1.15, rel=1e-6)

    def test_variant_type_none_by_default(self):
        m = _sample_manifest()
        assert m.variant_type is None
        assert m.variant_speed is None

    def test_variant_type_set(self):
        m = _sample_manifest(variant_type="aggressive", variant_speed=1.12)
        assert m.variant_type == "aggressive"
        assert m.variant_speed == pytest.approx(1.12)


class TestBaseClipManifestSerialization:
    def test_to_dict_contains_all_required_keys(self):
        d = _sample_manifest().to_dict()
        required = {
            "job_id", "part_no", "source_path",
            "source_start", "source_end",
            "payload_speed", "platform", "platform_delta", "effective_speed",
            "variant_type", "variant_speed",
            "silence_trim_offset", "visual_trim_offset",
            "timeline",
            "ai_enabled", "ai_mode", "ai_selected", "ai_speed_hint",
            "cut_path", "srt_path", "ass_path", "narration_path", "rendered_path",
        }
        assert required.issubset(d.keys())

    def test_none_artifact_paths_serialize_as_none(self):
        d = _sample_manifest().to_dict()
        for key in ("cut_path", "srt_path", "ass_path", "narration_path", "rendered_path"):
            assert d[key] is None, f"Expected None for {key}, got {d[key]!r}"

    def test_timeline_dict_embedded(self):
        d = _sample_manifest().to_dict()
        tl = d["timeline"]
        assert isinstance(tl, dict)
        assert "source_duration" in tl
        assert "output_duration" in tl

    def test_to_dict_is_json_serializable(self):
        json.dumps(_sample_manifest().to_dict())  # must not raise

    def test_from_dict_round_trip_identity(self):
        original = _sample_manifest()
        restored = BaseClipManifest.from_dict(original.to_dict())
        assert restored.job_id == original.job_id
        assert restored.part_no == original.part_no
        assert restored.source_path == original.source_path
        assert restored.platform == original.platform
        assert restored.effective_speed == pytest.approx(original.effective_speed)
        assert restored.silence_trim_offset == pytest.approx(original.silence_trim_offset)
        assert restored.visual_trim_offset == pytest.approx(original.visual_trim_offset)
        assert restored.ai_enabled == original.ai_enabled
        assert restored.ai_selected == original.ai_selected
        assert restored.cut_path is None
        assert restored.rendered_path is None

    def test_from_dict_timeline_round_trip(self):
        original = _sample_manifest()
        restored = BaseClipManifest.from_dict(original.to_dict())
        assert restored.timeline.source_duration == pytest.approx(
            original.timeline.source_duration
        )
        assert restored.timeline.output_duration == pytest.approx(
            original.timeline.output_duration
        )
        assert restored.timeline.effective_speed == pytest.approx(
            original.timeline.effective_speed
        )

    def test_from_dict_variant_fields_none(self):
        restored = BaseClipManifest.from_dict(_sample_manifest().to_dict())
        assert restored.variant_type is None
        assert restored.variant_speed is None

    def test_from_dict_variant_fields_set(self):
        m = _sample_manifest(variant_type="balanced", variant_speed=1.07)
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.variant_type == "balanced"
        assert restored.variant_speed == pytest.approx(1.07)

    def test_from_dict_optional_float_fields_none(self):
        m = _sample_manifest(ai_speed_hint=None)
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.ai_speed_hint is None

    def test_from_dict_optional_float_fields_set(self):
        m = _sample_manifest(ai_speed_hint=1.10)
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.ai_speed_hint == pytest.approx(1.10)


class TestBaseClipManifestProgressiveUpdate:
    def test_path_fields_set_after_construction(self):
        m = _sample_manifest()
        m.cut_path = "/tmp/render_job/part_1/cut.mp4"
        assert m.cut_path == "/tmp/render_job/part_1/cut.mp4"

    def test_path_field_update_serializes_correctly(self):
        m = _sample_manifest()
        m.cut_path = "/tmp/render_job/part_1/cut.mp4"
        m.srt_path = "/tmp/render_job/part_1/part_1.srt"
        d = m.to_dict()
        assert d["cut_path"] == "/tmp/render_job/part_1/cut.mp4"
        assert d["srt_path"] == "/tmp/render_job/part_1/part_1.srt"
        assert d["ass_path"] is None

    def test_all_paths_set_round_trip(self):
        m = _sample_manifest()
        m.cut_path = "/tmp/cut.mp4"
        m.srt_path = "/tmp/part.srt"
        m.ass_path = "/tmp/part.ass"
        m.narration_path = "/tmp/narration.mp3"
        m.rendered_path = "/tmp/output.mp4"
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.cut_path == "/tmp/cut.mp4"
        assert restored.srt_path == "/tmp/part.srt"
        assert restored.ass_path == "/tmp/part.ass"
        assert restored.narration_path == "/tmp/narration.mp3"
        assert restored.rendered_path == "/tmp/output.mp4"


class TestBaseClipManifestBaseClipFields:
    def test_base_clip_fields_none_by_default(self):
        m = _sample_manifest()
        assert m.base_clip_path is None
        assert m.base_clip_duration is None
        assert m.base_clip_fps is None
        assert m.base_clip_width is None
        assert m.base_clip_height is None
        assert m.base_clip_has_audio is None
        assert m.base_clip_created_at is None

    def test_base_clip_fields_in_to_dict(self):
        d = _sample_manifest().to_dict()
        base_keys = {
            "base_clip_path", "base_clip_duration", "base_clip_fps",
            "base_clip_width", "base_clip_height", "base_clip_has_audio",
            "base_clip_created_at",
        }
        assert base_keys.issubset(d.keys())

    def test_base_clip_fields_none_serialize_as_none(self):
        d = _sample_manifest().to_dict()
        for key in ("base_clip_path", "base_clip_duration", "base_clip_fps",
                    "base_clip_width", "base_clip_height", "base_clip_has_audio",
                    "base_clip_created_at"):
            assert d[key] is None, f"Expected None for {key}, got {d[key]!r}"

    def test_base_clip_fields_round_trip(self):
        m = _sample_manifest()
        m.base_clip_path = "/tmp/base_clip.mp4"
        m.base_clip_duration = 27.826
        m.base_clip_fps = 60.0
        m.base_clip_width = 1080
        m.base_clip_height = 1440
        m.base_clip_has_audio = True
        m.base_clip_created_at = 1716374400.0
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.base_clip_path == "/tmp/base_clip.mp4"
        assert restored.base_clip_duration == pytest.approx(27.826)
        assert restored.base_clip_fps == pytest.approx(60.0)
        assert restored.base_clip_width == 1080
        assert restored.base_clip_height == 1440
        assert restored.base_clip_has_audio is True
        assert restored.base_clip_created_at == pytest.approx(1716374400.0)

    def test_from_dict_backward_compat_missing_base_clip_fields(self):
        """Old manifest dicts without base_clip_* keys deserialize with None defaults."""
        old_dict = _sample_manifest().to_dict()
        for key in ("base_clip_path", "base_clip_duration", "base_clip_fps",
                    "base_clip_width", "base_clip_height", "base_clip_has_audio",
                    "base_clip_created_at"):
            old_dict.pop(key, None)
        restored = BaseClipManifest.from_dict(old_dict)
        assert restored.base_clip_path is None
        assert restored.base_clip_duration is None
        assert restored.base_clip_fps is None
        assert restored.base_clip_width is None
        assert restored.base_clip_height is None
        assert restored.base_clip_has_audio is None
        assert restored.base_clip_created_at is None

    def test_base_clip_has_audio_false_round_trip(self):
        m = _sample_manifest()
        m.base_clip_has_audio = False
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.base_clip_has_audio is False


class TestBaseClipManifestOverlayFields:
    def test_overlay_fields_none_by_default(self):
        m = _sample_manifest()
        assert m.overlay_srt_path is None
        assert m.overlay_ass_path is None
        assert m.overlay_rendered_path is None

    def test_overlay_fields_in_to_dict(self):
        d = _sample_manifest().to_dict()
        overlay_keys = {"overlay_srt_path", "overlay_ass_path", "overlay_rendered_path"}
        assert overlay_keys.issubset(d.keys())

    def test_overlay_fields_none_serialize_as_none(self):
        d = _sample_manifest().to_dict()
        for key in ("overlay_srt_path", "overlay_ass_path", "overlay_rendered_path"):
            assert d[key] is None, f"Expected None for {key}, got {d[key]!r}"

    def test_overlay_fields_round_trip(self):
        m = _sample_manifest()
        m.overlay_srt_path = "/tmp/part_1/subtitle_output_timeline.srt"
        m.overlay_ass_path = "/tmp/part_1/subtitle_output_timeline.ass"
        m.overlay_rendered_path = "/tmp/output/final_part_001.mp4"
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.overlay_srt_path == "/tmp/part_1/subtitle_output_timeline.srt"
        assert restored.overlay_ass_path == "/tmp/part_1/subtitle_output_timeline.ass"
        assert restored.overlay_rendered_path == "/tmp/output/final_part_001.mp4"

    def test_overlay_srt_in_to_dict_is_json_serializable(self):
        m = _sample_manifest()
        m.overlay_srt_path = "/tmp/subtitle_output_timeline.srt"
        m.overlay_ass_path = "/tmp/subtitle_output_timeline.ass"
        m.overlay_rendered_path = "/tmp/final.mp4"
        import json
        json.dumps(m.to_dict())  # must not raise

    def test_from_dict_backward_compat_missing_overlay_fields(self):
        """Old manifest dicts without overlay_* keys deserialize with None defaults."""
        old_dict = _sample_manifest().to_dict()
        for key in ("overlay_srt_path", "overlay_ass_path", "overlay_rendered_path"):
            old_dict.pop(key, None)
        restored = BaseClipManifest.from_dict(old_dict)
        assert restored.overlay_srt_path is None
        assert restored.overlay_ass_path is None
        assert restored.overlay_rendered_path is None

    def test_from_dict_backward_compat_missing_all_overlay_and_base_clip_fields(self):
        """Very old manifest dict (no base_clip_* or overlay_*) deserializes cleanly."""
        old_dict = _sample_manifest().to_dict()
        for key in (
            "base_clip_path", "base_clip_duration", "base_clip_fps",
            "base_clip_width", "base_clip_height", "base_clip_has_audio",
            "base_clip_created_at",
            "overlay_srt_path", "overlay_ass_path", "overlay_rendered_path",
        ):
            old_dict.pop(key, None)
        restored = BaseClipManifest.from_dict(old_dict)
        assert restored.base_clip_path is None
        assert restored.overlay_srt_path is None
        assert restored.overlay_ass_path is None
        assert restored.overlay_rendered_path is None

    def test_overlay_rendered_path_independent_of_rendered_path(self):
        """overlay_rendered_path and rendered_path can be set independently."""
        m = _sample_manifest()
        m.rendered_path = "/tmp/rendered_by_smart.mp4"
        m.overlay_rendered_path = "/tmp/rendered_by_composite.mp4"
        assert m.rendered_path != m.overlay_rendered_path
        restored = BaseClipManifest.from_dict(m.to_dict())
        assert restored.rendered_path == "/tmp/rendered_by_smart.mp4"
        assert restored.overlay_rendered_path == "/tmp/rendered_by_composite.mp4"
