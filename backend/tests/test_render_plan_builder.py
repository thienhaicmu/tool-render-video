"""
Sprint 2.2 — test the render_plan_builder shim.

Pins the SHIM contract: given the current LLM output + RenderRequest
payload, the builder produces a stable RenderPlan with the same
scattered decisions the existing pipeline already uses. Sprint 4 will
move those decisions up into the AI layer; the *shape* the builder
returns must not change in the meantime.

The builder is in the AI / orchestration tier, so it MUST NOT raise.
Errors return None so the caller falls back to the legacy path.
"""
from dataclasses import dataclass, field
from typing import Optional
from unittest import mock

from app.ai.llm.parser import LLMSegment
from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)
from app.orchestration.render_plan_builder import build_render_plan


# ── Minimal RenderRequest stand-in ───────────────────────────────────────
# Using a frozen dataclass instead of the real RenderRequest keeps the
# tests fast and decoupled from the Pydantic surface — the builder reads
# attributes via getattr() so any object shape works.


@dataclass
class FakePayload:
    subtitle_style: str = ""
    subtitle_only_viral_high: bool = False
    motion_aware_crop: bool = False
    reframe_mode: str = ""
    voice_enabled: bool = False
    tts_engine: str = ""
    reup_bgm_enable: bool = False
    video_codec: str = ""
    video_preset: Optional[str] = None
    video_crf: Optional[int] = None
    output_fps: int = 0
    add_title_overlay: bool = False
    title_overlay_text: str = ""
    cta_enabled: bool = False
    cta_type: str = "auto"
    hook_overlay_enabled: bool = False
    hook_applied_text: str = ""
    viral_market: Optional[str] = None
    ai_target_market: Optional[str] = None


def _seg(**kw) -> LLMSegment:
    """Build an LLMSegment with sensible defaults for fields we don't care about in a given test."""
    defaults = dict(start=10.0, end=40.0, score=0.8, clip_name="clip", title="title", reason="reason")
    defaults.update(kw)
    return LLMSegment(**defaults)


# ── Tests ────────────────────────────────────────────────────────────────


class TestClipMapping:
    def test_empty_segments_returns_plan_with_empty_clips(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.clips == []

    def test_none_segments_treated_as_empty(self):
        plan = build_render_plan(None, FakePayload())
        assert plan is not None
        assert plan.clips == []

    def test_segments_become_ranked_clipplans(self):
        segs = [
            _seg(start=10.0, end=40.0, score=0.95, clip_name="hook one"),
            _seg(start=120.0, end=160.0, score=0.80, clip_name="hook two"),
            _seg(start=200.0, end=240.0, score=0.65, clip_name="hook three"),
        ]
        plan = build_render_plan(segs, FakePayload())
        assert plan is not None
        assert [c.rank for c in plan.clips] == [1, 2, 3]
        assert plan.clips[0].clip_name == "hook one"
        assert plan.clips[0].start == 10.0
        assert plan.clips[2].score == 0.65

    def test_segment_extended_metadata_propagates(self):
        seg = _seg(
            hook_type="reveal",
            content_type="tutorial",
            viral_score=0.92,
            hook_score=0.85,
            retention_score=0.71,
            speech_density=0.6,
            duration_fit=0.95,
            cover_offset_ratio=0.18,
        )
        plan = build_render_plan([seg], FakePayload())
        assert plan is not None
        cp = plan.clips[0]
        assert cp.hook_type == "reveal"
        assert cp.content_type == "tutorial"
        assert cp.viral_score == 0.92
        assert cp.hook_score == 0.85
        assert cp.retention_score == 0.71
        assert cp.speech_density == 0.6
        assert cp.duration_fit == 0.95
        assert cp.cover_offset_ratio == 0.18

    def test_malformed_segment_is_skipped_not_raised(self):
        """A bad segment doesn't sink the whole plan."""
        good = _seg(clip_name="good")
        bad = mock.MagicMock(spec=LLMSegment)
        # Make a numeric coercion blow up
        bad.start = "not a number"
        bad.end = "also not a number"
        # Other attribute accesses fall through to MagicMock defaults — float() on those WILL raise.
        plan = build_render_plan([bad, good], FakePayload())
        assert plan is not None
        # Only the good one survived. Rank is the rank within the kept list,
        # so 'good' gets rank=2 because the bad seg was tried at rank=1 first.
        assert [c.clip_name for c in plan.clips] == ["good"]


class TestSubtitlePolicy:
    def test_style_pass_through(self):
        plan = build_render_plan([], FakePayload(subtitle_style="tiktok_bounce_v1"))
        assert plan is not None
        assert plan.subtitle_policy.style == "tiktok_bounce_v1"

    def test_empty_style_default(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.subtitle_policy.style == ""

    def test_emphasis_pass_from_viral_high_flag(self):
        plan = build_render_plan([], FakePayload(subtitle_only_viral_high=True))
        assert plan is not None
        assert plan.subtitle_policy.emphasis_pass is True

    def test_market_resolution_prefers_ai_target_market(self):
        plan = build_render_plan([], FakePayload(ai_target_market="us", viral_market="vn"))
        assert plan is not None
        assert plan.subtitle_policy.market == "us"

    def test_market_resolution_falls_back_to_viral_market(self):
        plan = build_render_plan([], FakePayload(viral_market="vn"))
        assert plan is not None
        assert plan.subtitle_policy.market == "vn"

    def test_market_empty_when_neither_set(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.subtitle_policy.market == ""


class TestCameraStrategy:
    def test_motion_aware_flag_pass_through(self):
        plan = build_render_plan([], FakePayload(motion_aware_crop=True, reframe_mode="track"))
        assert plan is not None
        assert plan.camera_strategy.motion_aware_crop is True
        assert plan.camera_strategy.reframe_mode == "track"

    def test_legacy_subject_label_normalised_to_track(self):
        """The pre-Sprint-2 RenderRequest used 'subject' for what
        RenderPlan calls 'track'. Normalise so downstream consumers
        only speak one vocabulary."""
        plan = build_render_plan([], FakePayload(reframe_mode="subject"))
        assert plan is not None
        assert plan.camera_strategy.reframe_mode == "track"

    def test_tracker_default_empty(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.camera_strategy.tracker == ""


class TestAudioPlan:
    def test_voice_enabled_pass_through(self):
        plan = build_render_plan([], FakePayload(voice_enabled=True, tts_engine="xtts"))
        assert plan is not None
        assert plan.audio_plan.voice_enabled is True
        assert plan.audio_plan.voice_provider == "xtts"

    def test_bgm_from_reup_bgm_enable(self):
        plan = build_render_plan([], FakePayload(reup_bgm_enable=True))
        assert plan is not None
        assert plan.audio_plan.bgm_enabled is True

    def test_default_audio_disabled(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.audio_plan == AudioPlan()  # all defaults


class TestOutputConfig:
    def test_codec_preset_crf_fps_pass_through(self):
        plan = build_render_plan(
            [],
            FakePayload(video_codec="h264_nvenc", video_preset="medium", video_crf=22, output_fps=30),
        )
        assert plan is not None
        oc = plan.output_config
        assert oc.codec == "h264_nvenc"
        assert oc.preset == "medium"
        assert oc.crf == 22
        assert oc.fps == 30

    def test_none_crf_coerces_to_zero(self):
        plan = build_render_plan([], FakePayload(video_crf=None))
        assert plan is not None
        assert plan.output_config.crf == 0


class TestOverlays:
    def test_no_overlays_default(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.overlays == []

    def test_title_overlay_included(self):
        plan = build_render_plan([], FakePayload(add_title_overlay=True, title_overlay_text="Hello"))
        assert plan is not None
        assert {"kind": "title", "text": "Hello"} in plan.overlays

    def test_title_overlay_without_text_is_skipped(self):
        plan = build_render_plan([], FakePayload(add_title_overlay=True, title_overlay_text=""))
        assert plan is not None
        assert plan.overlays == []

    def test_cta_overlay_with_type(self):
        plan = build_render_plan([], FakePayload(cta_enabled=True, cta_type="comment"))
        assert plan is not None
        assert {"kind": "cta", "type": "comment"} in plan.overlays

    def test_hook_overlay_with_text(self):
        plan = build_render_plan([], FakePayload(hook_overlay_enabled=True, hook_applied_text="What if…"))
        assert plan is not None
        assert any(o.get("kind") == "hook" and o.get("text") == "What if…" for o in plan.overlays)


class TestCreatorContextId:
    def test_creator_context_threaded_through(self):
        plan = build_render_plan([], FakePayload(), creator_context_id="creator-vn-1")
        assert plan is not None
        assert plan.creator_context_id == "creator-vn-1"

    def test_creator_context_default_empty(self):
        plan = build_render_plan([], FakePayload())
        assert plan is not None
        assert plan.creator_context_id == ""


class TestNeverRaises:
    def test_payload_with_no_relevant_attrs_returns_default_plan(self):
        """A payload missing every attribute the builder reads must not
        raise — getattr defaults take over and we get a plan full of
        safe defaults."""
        class Bare:
            pass
        plan = build_render_plan([_seg()], Bare())
        assert plan is not None
        assert plan.subtitle_policy == SubtitlePolicy()
        assert plan.camera_strategy == CameraStrategy()
        assert plan.audio_plan == AudioPlan()
        assert plan.output_config == OutputConfig()

    def test_internal_failure_returns_none(self):
        """If something deeper down does raise (e.g. import-level
        breakage), the top-level catch returns None so the caller can
        fall back to the legacy path."""
        with mock.patch(
            "app.orchestration.render_plan_builder._build_clips",
            side_effect=RuntimeError("boom"),
        ):
            plan = build_render_plan([_seg()], FakePayload())
        assert plan is None


class TestEndToEndRoundTrip:
    """Smoke: builder output round-trips through to_json / from_json."""

    def test_built_plan_roundtrips(self):
        segs = [_seg(start=12.5, end=45.0, score=0.91)]
        payload = FakePayload(
            subtitle_style="tiktok_bounce_v1",
            motion_aware_crop=True,
            reframe_mode="subject",
            voice_enabled=True,
            tts_engine="edge",
            video_codec="h264_nvenc",
            video_crf=22,
            output_fps=60,
            cta_enabled=True,
            cta_type="part_2",
            ai_target_market="us",
        )
        plan = build_render_plan(segs, payload, creator_context_id="creator-en-1")
        assert plan is not None
        restored = RenderPlan.from_json(plan.to_json())
        assert restored == plan
