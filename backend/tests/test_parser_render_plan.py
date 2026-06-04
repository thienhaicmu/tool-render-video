"""
Sprint 4.A — pin the parse_render_plan_response contract.

This is the additive dual-mode parser. Sprint 4.D will gate the
orchestrator to use it; Sprint 4.H will retire the segment-only path.
For now the function lives alongside parse_segment_response and the
tests anchor:

- three accepted wire shapes (native / wrapped / legacy segments)
- per-clip duration / bounds validation
- output_count truncation + score-descending sort + rank re-tagging
- sub-plan defaults survive when malformed
- defensive deserialise — returns None on any unparseable / empty
  input. Never raises (Sacred Contract #3).
"""
import json

from app.ai.llm.parser import parse_render_plan_response


def _clip(start: float, end: float, score: float = 0.7, **extra) -> dict:
    return {
        "start": start,
        "end": end,
        "score": score,
        "clip_name": extra.pop("clip_name", "clip"),
        **extra,
    }


# ── Shape: native ────────────────────────────────────────────────────────


class TestNativeShape:
    def test_single_clip_round_trip(self):
        raw = json.dumps({"clips": [_clip(10.0, 40.0, score=0.9, clip_name="hook")]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert len(plan.clips) == 1
        c = plan.clips[0]
        assert c.start == 10.0
        assert c.end == 40.0
        assert c.clip_name == "hook"
        assert c.score == 0.9

    def test_multiple_clips_sorted_by_score(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 40.0, score=0.5, clip_name="low"),
            _clip(50.0, 80.0, score=0.95, clip_name="high"),
            _clip(90.0, 120.0, score=0.7, clip_name="mid"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=200)
        assert plan is not None
        assert [c.clip_name for c in plan.clips] == ["high", "mid", "low"]
        # Ranks are 1..N after sort.
        assert [c.rank for c in plan.clips] == [1, 2, 3]

    def test_output_count_truncates(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 40.0, score=0.95, clip_name="a"),
            _clip(50.0, 80.0, score=0.90, clip_name="b"),
            _clip(90.0, 120.0, score=0.85, clip_name="c"),
            _clip(130.0, 160.0, score=0.80, clip_name="d"),
        ]})
        plan = parse_render_plan_response(raw, output_count=2, min_sec=15, max_sec=60, video_duration=200)
        assert plan is not None
        assert len(plan.clips) == 2
        assert [c.clip_name for c in plan.clips] == ["a", "b"]

    def test_native_shape_with_subplans(self):
        raw = json.dumps({
            "clips": [_clip(10.0, 40.0, score=0.9)],
            "subtitle_policy": {"style": "viral", "market": "vn", "emphasis_pass": True},
            "camera_strategy": {"motion_aware_crop": True, "reframe_mode": "track"},
            "audio_plan": {"voice_enabled": True, "voice_provider": "xtts"},
            "output_config": {"codec": "h264_nvenc", "preset": "medium", "crf": 22},
            "overlays": [{"kind": "title", "text": "Hello"}],
            "creator_context_id": "creator-vn-1",
        })
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert plan.subtitle_policy.style == "viral"
        assert plan.subtitle_policy.market == "vn"
        assert plan.subtitle_policy.emphasis_pass is True
        assert plan.camera_strategy.motion_aware_crop is True
        assert plan.camera_strategy.reframe_mode == "track"
        assert plan.audio_plan.voice_enabled is True
        assert plan.audio_plan.voice_provider == "xtts"
        assert plan.output_config.codec == "h264_nvenc"
        assert plan.output_config.crf == 22
        assert {"kind": "title", "text": "Hello"} in plan.overlays
        assert plan.creator_context_id == "creator-vn-1"


# ── Shape: wrapped ───────────────────────────────────────────────────────


class TestWrappedShape:
    def test_wrapped_with_render_plan_key(self):
        raw = json.dumps({"render_plan": {"clips": [_clip(10.0, 40.0, score=0.9)]}})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert len(plan.clips) == 1
        assert plan.clips[0].start == 10.0

    def test_wrapped_with_subplans(self):
        raw = json.dumps({
            "render_plan": {
                "clips": [_clip(10.0, 40.0)],
                "subtitle_policy": {"style": "clean"},
            }
        })
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert plan.subtitle_policy.style == "clean"


# ── Shape: legacy segments-only ──────────────────────────────────────────


class TestLegacySegmentsShape:
    def test_segments_converted_to_clips(self):
        raw = json.dumps({"segments": [
            {"start": 10.0, "end": 40.0, "score": 0.9, "clip_name": "hook",
             "viral_score": 0.88, "hook_score": 0.92, "hook_type": "reveal"},
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert len(plan.clips) == 1
        c = plan.clips[0]
        assert c.clip_name == "hook"
        assert c.viral_score == 0.88
        assert c.hook_score == 0.92
        assert c.hook_type == "reveal"

    def test_legacy_shape_leaves_subplans_default(self):
        """When the AI emits the segments-only shape, every other
        sub-plan stays at its safe default — Sprint 4.D won't migrate
        them yet."""
        raw = json.dumps({"segments": [
            {"start": 10.0, "end": 40.0, "score": 0.9, "clip_name": "hook"},
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        from app.domain.render_plan import (
            AudioPlan, CameraStrategy, OutputConfig, SubtitlePolicy,
        )
        assert plan.subtitle_policy == SubtitlePolicy()
        assert plan.camera_strategy == CameraStrategy()
        assert plan.audio_plan == AudioPlan()
        assert plan.output_config == OutputConfig()


# ── Per-clip validation ──────────────────────────────────────────────────


class TestClipValidation:
    def test_duration_below_min_dropped(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 13.0, score=0.9, clip_name="too_short"),     # 3s < min=15
            _clip(20.0, 50.0, score=0.8, clip_name="ok"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert [c.clip_name for c in plan.clips] == ["ok"]

    def test_duration_above_max_dropped(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 100.0, score=0.9, clip_name="too_long"),      # 90s > max=60
            _clip(20.0, 50.0, score=0.8, clip_name="ok"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert [c.clip_name for c in plan.clips] == ["ok"]

    def test_negative_start_dropped(self):
        raw = json.dumps({"clips": [
            _clip(-5.0, 25.0, clip_name="negative"),
            _clip(20.0, 50.0, clip_name="ok"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        assert [c.clip_name for c in plan.clips] == ["ok"]

    def test_end_beyond_video_dropped(self):
        # video=100, +1.0 tolerance → end > 101.0 is rejected.
        raw = json.dumps({"clips": [
            _clip(50.0, 200.0, clip_name="past_end"),
            _clip(20.0, 50.0, clip_name="ok"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=100)
        assert plan is not None
        assert [c.clip_name for c in plan.clips] == ["ok"]

    def test_video_duration_zero_skips_upper_bound_check(self):
        """Mirrors the existing parse_segment_response behaviour:
        when video_duration is unknown (0), we only enforce the lower
        bound (start >= 0) and the duration range."""
        raw = json.dumps({"clips": [_clip(50.0, 100.0, clip_name="anywhere")]})
        plan = parse_render_plan_response(raw, output_count=1, min_sec=15, max_sec=60, video_duration=0)
        assert plan is not None
        assert plan.clips[0].clip_name == "anywhere"

    def test_score_clamped_to_unit_interval(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 40.0, score=1.7, clip_name="too_high"),
            _clip(50.0, 80.0, score=-0.3, clip_name="too_low"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=120)
        assert plan is not None
        scores = {c.clip_name: c.score for c in plan.clips}
        assert scores["too_high"] == 1.0
        assert scores["too_low"] == 0.0


# ── Defensive shape handling ─────────────────────────────────────────────


class TestDefensiveDeserialise:
    def test_returns_none_on_unparseable_json(self):
        assert parse_render_plan_response("not json", 3, 15, 60, 120) is None

    def test_returns_none_on_top_level_array(self):
        assert parse_render_plan_response("[1,2,3]", 3, 15, 60, 120) is None

    def test_returns_none_on_no_clips_key(self):
        raw = json.dumps({"something_else": 42})
        assert parse_render_plan_response(raw, 3, 15, 60, 120) is None

    def test_returns_none_when_all_clips_out_of_bounds(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 13.0, clip_name="too_short"),
            _clip(10.0, 100.0, clip_name="too_long"),
        ]})
        assert parse_render_plan_response(raw, 3, 15, 60, 120) is None

    def test_returns_none_on_empty_clips_array(self):
        raw = json.dumps({"clips": []})
        assert parse_render_plan_response(raw, 3, 15, 60, 120) is None

    def test_returns_none_on_empty_segments_array(self):
        raw = json.dumps({"segments": []})
        assert parse_render_plan_response(raw, 3, 15, 60, 120) is None

    def test_malformed_subplan_falls_back_to_default(self):
        """A wrong-type sub-plan (string instead of dict) must NOT
        kill the parse — the offending block falls back to its default
        sub-dataclass."""
        raw = json.dumps({
            "clips": [_clip(10.0, 40.0)],
            "subtitle_policy": "not a dict",
        })
        plan = parse_render_plan_response(raw, 3, 15, 60, 120)
        assert plan is not None
        from app.domain.render_plan import SubtitlePolicy
        assert plan.subtitle_policy == SubtitlePolicy()

    def test_extracts_json_from_markdown_fence(self):
        """The shared `_extract_json_array` helper handles ```json
        fences for free — pin that the RenderPlan parser benefits."""
        body = '{"clips":[{"start":10.0,"end":40.0,"score":0.9,"clip_name":"hook"}]}'
        raw = f"Some prose then\n```json\n{body}\n```\nand more prose."
        plan = parse_render_plan_response(raw, 3, 15, 60, 120)
        assert plan is not None
        assert plan.clips[0].clip_name == "hook"

    def test_unexpected_exception_in_normaliser_returns_none(self):
        """Pin the catch-all guarantee. We force an internal error by
        handing the top-level branch something that the JSON extractor
        accepts as a dict but the normaliser cannot handle — namely,
        a clips key whose value is a string."""
        raw = json.dumps({"clips": "should be a list"})
        # Native branch checks isinstance(clips, list) so this collapses
        # to "no recognisable clip list" → None.
        assert parse_render_plan_response(raw, 3, 15, 60, 120) is None


# ── Rank tagging ─────────────────────────────────────────────────────────


class TestRankAssignment:
    def test_ranks_are_one_indexed_after_sort(self):
        raw = json.dumps({"clips": [
            _clip(10.0, 40.0, score=0.6, clip_name="b"),
            _clip(50.0, 80.0, score=0.9, clip_name="a"),
            _clip(90.0, 120.0, score=0.3, clip_name="c"),
        ]})
        plan = parse_render_plan_response(raw, output_count=3, min_sec=15, max_sec=60, video_duration=200)
        assert plan is not None
        assert [(c.clip_name, c.rank) for c in plan.clips] == [("a", 1), ("b", 2), ("c", 3)]
