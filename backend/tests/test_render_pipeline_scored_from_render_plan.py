"""Sprint 7.6 FULL — tests for `_scored_from_render_plan` helper.

Pins:
- Helper returns fallback list unchanged when `render_plan is None` or
  `render_plan.clips` is empty (no-op fallback path).
- Helper never raises — Sacred Contract #3 spirit. Any attribute error
  on a malformed clip object returns the fallback.
- Dual-path parity: derivation produces the SAME field-shape as
  `llm_stage._to_scored_dict` key-for-key, value-for-value, except the
  documented `source` discriminator (`"render_plan"` vs `"llm"`).
- `ClipPlan.subtitle_style` is the only schema addition (Sacred Contract
  #2 compliant — defaults to `""` = inherit).
- `cover_hint_ratio` maps `0.0 → None` exactly like `_to_scored_dict`
  line 291.
- `total_parts = len(scored)` invariant holds after derivation.
"""
from __future__ import annotations

import pytest

from app.ai.llm.parser import LLMSegment
from app.domain.render_plan import ClipPlan, RenderPlan
from app.orchestration.llm_stage import _to_scored_dict
from app.orchestration.render_pipeline import _scored_from_render_plan


# ---------------------------------------------------------------------------
# Section 1: fallback semantics — never raise, return fallback unchanged
# ---------------------------------------------------------------------------


class TestFallbackSemantics:
    def test_helper_returns_fallback_when_render_plan_is_none(self):
        fb = [{"start": 0.0, "end": 1.0, "source": "llm"}]
        out = _scored_from_render_plan(None, fallback_scored=fb)
        assert out is fb

    def test_helper_returns_fallback_when_clips_empty(self):
        fb = [{"start": 0.0, "end": 1.0, "source": "llm"}]
        plan = RenderPlan(clips=[])
        out = _scored_from_render_plan(plan, fallback_scored=fb)
        assert out is fb

    def test_helper_returns_fallback_on_attribute_error(self):
        """Sacred Contract #3 spirit — any unexpected exception returns
        the fallback rather than crashing the render."""
        class _Boom:
            @property
            def clips(self):
                raise RuntimeError("synthetic")

        fb = [{"start": 0.0, "end": 1.0, "source": "llm"}]
        out = _scored_from_render_plan(_Boom(), fallback_scored=fb)
        assert out is fb

    def test_helper_returns_fallback_on_per_clip_failure(self):
        """If iterating clips itself raises, fallback returned — not a
        partial list. Pins the OUTER try/except boundary."""
        class _BadList:
            def __iter__(self):
                raise RuntimeError("synthetic")

        class _BadPlan:
            clips = _BadList()

        fb = [{"start": 0.0}]
        out = _scored_from_render_plan(_BadPlan(), fallback_scored=fb)
        assert out is fb


# ---------------------------------------------------------------------------
# Section 2: dual-path parity — derivation matches _to_scored_dict
# ---------------------------------------------------------------------------


def _llm_seg() -> LLMSegment:
    return LLMSegment(
        start=10.0, end=40.0, score=0.8,
        clip_name="hook-clip", title="Hook Title", reason="strong hook",
        hook_type="reveal", content_type="vlog",
        subtitle_style="viral",
        viral_score=0.9, hook_score=0.85, retention_score=0.75,
        speech_density=0.6, duration_fit=0.95,
        cover_offset_ratio=0.3,
    )


def _clip_plan_mirror(seg: LLMSegment) -> ClipPlan:
    """Build a ClipPlan with the same scalar values as the LLMSegment."""
    return ClipPlan(
        start=seg.start, end=seg.end, rank=1, score=seg.score,
        clip_name=seg.clip_name, title=seg.title, reason=seg.reason,
        hook_type=seg.hook_type, content_type=seg.content_type,
        subtitle_style=seg.subtitle_style,
        viral_score=seg.viral_score, hook_score=seg.hook_score,
        retention_score=seg.retention_score,
        speech_density=seg.speech_density, duration_fit=seg.duration_fit,
        cover_offset_ratio=seg.cover_offset_ratio,
    )


class TestDualPathParity:
    def test_helper_field_shape_matches_to_scored_dict(self):
        """CRITICAL — derivation must produce IDENTICAL field shape to
        _to_scored_dict, except the documented `source` discriminator.

        Any divergence here = silent break of downstream consumers."""
        seg = _llm_seg()
        legacy = _to_scored_dict(seg)
        plan = RenderPlan(clips=[_clip_plan_mirror(seg)])
        derived = _scored_from_render_plan(plan, fallback_scored=[])
        assert len(derived) == 1

        # All keys must match.
        assert set(legacy.keys()) == set(derived[0].keys()), (
            f"key set diverged: legacy={set(legacy.keys()) - set(derived[0].keys())}, "
            f"derived={set(derived[0].keys()) - set(legacy.keys())}"
        )

        for key in legacy:
            if key == "source":
                assert legacy[key] == "llm"
                assert derived[0][key] == "render_plan"
                continue
            assert legacy[key] == derived[0][key], (
                f"parity break at key={key!r}: legacy={legacy[key]!r} "
                f"derived={derived[0][key]!r}"
            )

    def test_helper_preserves_zero_score_neutral_fallback(self):
        """Mirror _to_scored_dict's `_base` fallback: when viral_score==0,
        derived viral_score == score*100. Same for hook/retention."""
        seg = LLMSegment(
            start=0.0, end=30.0, score=0.5,
            clip_name="x", title="t", reason="r",
            hook_type="", content_type="", subtitle_style="",
            viral_score=0.0, hook_score=0.0, retention_score=0.0,
            speech_density=0.0, duration_fit=0.0,
            cover_offset_ratio=0.0,
        )
        legacy = _to_scored_dict(seg)
        plan = RenderPlan(clips=[_clip_plan_mirror(seg)])
        derived = _scored_from_render_plan(plan, fallback_scored=[])
        assert legacy["viral_score"] == derived[0]["viral_score"] == 50.0
        assert legacy["hook_score"] == derived[0]["hook_score"] == 50.0
        assert legacy["retention_score"] == derived[0]["retention_score"] == 50.0

    def test_helper_cover_hint_ratio_zero_becomes_none(self):
        """Mirror _to_scored_dict line 291: cover_hint_ratio is None when
        cover_offset_ratio is 0, the original float otherwise."""
        seg_zero = _llm_seg()
        seg_zero.cover_offset_ratio = 0.0
        plan_zero = RenderPlan(clips=[_clip_plan_mirror(seg_zero)])
        derived_zero = _scored_from_render_plan(plan_zero, fallback_scored=[])
        assert derived_zero[0]["cover_hint_ratio"] is None

        seg_set = _llm_seg()
        seg_set.cover_offset_ratio = 0.42
        plan_set = RenderPlan(clips=[_clip_plan_mirror(seg_set)])
        derived_set = _scored_from_render_plan(plan_set, fallback_scored=[])
        assert derived_set[0]["cover_hint_ratio"] == pytest.approx(0.42)

    def test_helper_source_field_is_render_plan(self):
        """Telemetry discriminator — derivation must tag `render_plan`,
        not `llm`. Grep audit confirmed zero string-match consumers."""
        seg = _llm_seg()
        plan = RenderPlan(clips=[_clip_plan_mirror(seg)])
        derived = _scored_from_render_plan(plan, fallback_scored=[])
        assert derived[0]["source"] == "render_plan"

    def test_helper_subtitle_style_round_trips_from_clip(self):
        """ClipPlan.subtitle_style (Sprint 7.6 FULL additive field) must
        surface as `ai_subtitle_style` in the derived dict — same key
        downstream consumers (part_asset_planner:478) read."""
        seg = _llm_seg()
        seg.subtitle_style = "story"
        plan = RenderPlan(clips=[_clip_plan_mirror(seg)])
        derived = _scored_from_render_plan(plan, fallback_scored=[])
        assert derived[0]["ai_subtitle_style"] == "story"


# ---------------------------------------------------------------------------
# Section 3: ClipPlan additive field (Sacred Contract #2 pin)
# ---------------------------------------------------------------------------


class TestClipPlanSubtitleStyle:
    def test_clipplan_subtitle_style_defaults_to_empty_string(self):
        """Sacred Contract #2: new field defaults to most conservative
        state. Empty string = inherit (no behaviour change)."""
        clip = ClipPlan()
        assert clip.subtitle_style == ""

    def test_clipplan_subtitle_style_round_trips_through_json(self):
        """Sprint 4.A schema contract — RenderPlan.from_json must preserve
        the new field across persist/load."""
        plan = RenderPlan(clips=[ClipPlan(start=0.0, end=10.0, subtitle_style="viral")])
        round_tripped = RenderPlan.from_json(plan.to_json())
        assert round_tripped is not None
        assert round_tripped.clips[0].subtitle_style == "viral"


# ---------------------------------------------------------------------------
# Section 4: total_parts invariant
# ---------------------------------------------------------------------------


class TestTotalPartsInvariant:
    def test_helper_total_parts_reflects_len_scored(self):
        """When derivation replaces scored, the count must match
        len(render_plan.clips) — pipeline_render_loop trusts total_parts
        equals len(scored)."""
        plan = RenderPlan(clips=[
            _clip_plan_mirror(_llm_seg()),
            _clip_plan_mirror(_llm_seg()),
            _clip_plan_mirror(_llm_seg()),
        ])
        derived = _scored_from_render_plan(plan, fallback_scored=[])
        assert len(derived) == 3
        assert len(derived) == len(plan.clips)


# ---------------------------------------------------------------------------
# Section 5: source-pin — derivation lives in render_pipeline namespace
# ---------------------------------------------------------------------------


class TestSourceLevelPins:
    def test_scored_from_render_plan_is_importable(self):
        """The helper must be reachable at module scope so a typo /
        circular import fails at import time, not at first render."""
        import app.orchestration.render_pipeline as rp
        assert hasattr(rp, "_scored_from_render_plan")
        assert callable(rp._scored_from_render_plan)

    def test_legacy_scored_path_unchanged_when_render_plan_none(self):
        """Source-grep pin: the conditional `if _render_plan is not None:`
        guards the derivation. When the flag is OFF or AI fallback fires,
        the helper is not invoked and `scored` flows through unchanged."""
        import inspect
        import app.orchestration.render_pipeline as rp
        src = inspect.getsource(rp.run_render_pipeline)
        assert "_scored_from_render_plan" in src
        assert "if _render_plan is not None:" in src
        # The derivation block must mention scored reassignment with the
        # fallback semantics — confirms not a no-op call.
        assert "fallback_scored=scored" in src

    def test_total_parts_reassigned_in_derivation_block(self):
        """Pin: when derivation replaces scored, total_parts is updated
        to match. pipeline_render_loop relies on this invariant."""
        import inspect
        import app.orchestration.render_pipeline as rp
        src = inspect.getsource(rp.run_render_pipeline)
        assert "total_parts = len(scored)" in src
