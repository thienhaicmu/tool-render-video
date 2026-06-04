"""
Sprint 2.1 — test the RenderPlan dataclass contract:

- defaults are safe (every field has a default; Sacred Contract #2)
- to_json / from_json round-trip is lossless
- from_json is strictly defensive: returns None on unparseable input,
  drops unknown fields, coerces primitives, never raises
- schema_version is the stable forward-compat anchor
"""
from app.domain.render_plan import (
    SCHEMA_VERSION,
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)


class TestDefaults:
    def test_render_plan_default_is_safe(self):
        rp = RenderPlan()
        assert rp.schema_version == SCHEMA_VERSION
        assert rp.clips == []
        assert rp.subtitle_policy == SubtitlePolicy()
        assert rp.camera_strategy == CameraStrategy()
        assert rp.audio_plan == AudioPlan()
        assert rp.output_config == OutputConfig()
        assert rp.overlays == []
        assert rp.creator_context_id == ""

    def test_subtitle_policy_defaults_inherit(self):
        sp = SubtitlePolicy()
        assert sp.style == ""
        assert sp.market == ""
        assert sp.emphasis_pass is False
        assert sp.line_break_rule == ""

    def test_camera_strategy_defaults_inherit(self):
        cs = CameraStrategy()
        assert cs.motion_aware_crop is False
        assert cs.reframe_mode == ""
        assert cs.tracker == ""

    def test_audio_plan_defaults_disabled(self):
        ap = AudioPlan()
        assert ap.voice_enabled is False
        assert ap.bgm_enabled is False
        assert ap.voice_provider == ""
        assert ap.cta_audio == ""

    def test_output_config_defaults_inherit(self):
        oc = OutputConfig()
        assert oc.codec == ""
        assert oc.preset == ""
        assert oc.crf == 0
        assert oc.fps == 0
        assert oc.width == 0
        assert oc.height == 0

    def test_clip_plan_default(self):
        cp = ClipPlan()
        assert cp.start == 0.0
        assert cp.end == 0.0
        assert cp.rank == 0
        assert cp.clip_name == ""


class TestRoundTrip:
    def test_default_plan_roundtrip(self):
        original = RenderPlan()
        restored = RenderPlan.from_json(original.to_json())
        assert restored == original

    def test_populated_plan_roundtrip(self):
        original = RenderPlan(
            clips=[
                ClipPlan(start=12.5, end=45.0, rank=1, score=0.9, clip_name="hook one", title="Hook One"),
                ClipPlan(start=200.0, end=240.0, rank=2, score=0.75, clip_name="hook two"),
            ],
            subtitle_policy=SubtitlePolicy(style="viral", market="vn", emphasis_pass=True),
            camera_strategy=CameraStrategy(motion_aware_crop=True, reframe_mode="track", tracker="bytetrack"),
            audio_plan=AudioPlan(voice_enabled=True, voice_provider="xtts"),
            output_config=OutputConfig(codec="h264_nvenc", preset="medium", crf=22, fps=30, width=1080, height=1920),
            overlays=[{"id": "cta1", "text": "Subscribe"}],
            creator_context_id="creator-vn-cooking",
        )
        restored = RenderPlan.from_json(original.to_json())
        assert restored == original

    def test_json_is_compact_and_sorted(self):
        rp = RenderPlan(creator_context_id="abc")
        raw = rp.to_json()
        # No whitespace between members.
        assert ", " not in raw and ": " not in raw
        # Keys sorted alphabetically at the top level.
        # The first three sorted top-level keys of an empty RenderPlan are
        # "audio_plan", "camera_strategy", "clips".
        assert raw.index('"audio_plan"') < raw.index('"camera_strategy"') < raw.index('"clips"')


class TestDefensiveFromJson:
    def test_none_returns_none(self):
        assert RenderPlan.from_json(None) is None

    def test_empty_string_returns_none(self):
        assert RenderPlan.from_json("") is None

    def test_malformed_json_returns_none(self):
        assert RenderPlan.from_json("not json at all") is None
        assert RenderPlan.from_json("{not: valid}") is None

    def test_array_top_level_returns_none(self):
        # RenderPlan expects an object, not an array.
        assert RenderPlan.from_json("[1,2,3]") is None

    def test_unknown_top_level_keys_are_dropped(self):
        raw = '{"clips":[],"unknown_field":42,"creator_context_id":"abc"}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.creator_context_id == "abc"
        assert not hasattr(plan, "unknown_field")

    def test_unknown_nested_keys_are_dropped(self):
        raw = '{"subtitle_policy":{"style":"viral","invented":"nope"}}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.subtitle_policy.style == "viral"

    def test_missing_subblocks_use_defaults(self):
        raw = '{"clips":[]}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.subtitle_policy == SubtitlePolicy()
        assert plan.camera_strategy == CameraStrategy()
        assert plan.audio_plan == AudioPlan()
        assert plan.output_config == OutputConfig()

    def test_subblock_wrong_type_falls_back_to_default(self):
        # subtitle_policy is given as a string instead of an object — should
        # silently fall back to the default sub-dataclass.
        raw = '{"subtitle_policy":"viral"}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.subtitle_policy == SubtitlePolicy()

    def test_clip_entry_not_a_dict_is_skipped(self):
        raw = '{"clips":[{"start":1.0,"end":2.0}, "garbage", 42]}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert len(plan.clips) == 1
        assert plan.clips[0].start == 1.0

    def test_primitive_coercion_int_from_string(self):
        raw = '{"output_config":{"crf":"22","fps":"30"}}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.output_config.crf == 22
        assert plan.output_config.fps == 30

    def test_primitive_coercion_bool_from_string(self):
        raw = '{"audio_plan":{"voice_enabled":"true","bgm_enabled":"false"}}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.audio_plan.voice_enabled is True
        assert plan.audio_plan.bgm_enabled is False

    def test_primitive_coercion_garbage_falls_back_to_default(self):
        # crf default is 0; "abc" cannot coerce to int → keep default
        raw = '{"output_config":{"crf":"abc"}}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.output_config.crf == 0

    def test_schema_version_explicit(self):
        raw = '{"schema_version":7}'
        plan = RenderPlan.from_json(raw)
        assert plan is not None
        assert plan.schema_version == 7

    def test_schema_version_missing_uses_current(self):
        plan = RenderPlan.from_json("{}")
        assert plan is not None
        assert plan.schema_version == SCHEMA_VERSION

    def test_bytes_input_accepted(self):
        rp = RenderPlan(creator_context_id="abc")
        raw = rp.to_json().encode("utf-8")
        restored = RenderPlan.from_json(raw)
        assert restored == rp


class TestVietnameseCharsPreserved:
    def test_vietnamese_in_clip_name_roundtrip(self):
        original = RenderPlan(
            clips=[ClipPlan(start=1.0, end=10.0, clip_name="Khoảnh khắc bất ngờ", title="Hấp dẫn ngay tức thì")]
        )
        restored = RenderPlan.from_json(original.to_json())
        assert restored is not None
        assert restored.clips[0].clip_name == "Khoảnh khắc bất ngờ"
        assert restored.clips[0].title == "Hấp dẫn ngay tức thì"
