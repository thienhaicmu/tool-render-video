"""Strategic-1c closure regression guard — Audit 2026-06-08.

Closes the remaining UP26 Pro Timeline Steering fields:

  - structure_bias ('hook' | 'balanced' | 'story') — re-weights the
    ranking formula in pipeline_ranking.py. Pre-Strategic-1c the
    formula was hardcoded at lines 204-211. Strategic-1c introduces
    STRUCTURE_BIAS_WEIGHTS with three weight sets that each sum to
    1.0; resolve_structure_bias_weights returns the set, and
    _compute_output_ranking_entry uses it instead of the hardcoded
    coefficients.

  - subtitle_emphasis ('subtle' | 'balanced' | 'aggressive') —
    multiplies the operator's sub_font_size by 0.85 / 1.0 / 1.20
    at the start of prepare_part_assets. The effective font size
    flows into both the ASS cache key AND both ASS writers (karaoke
    and bounce) so the cache stays correct across emphasis changes.

This file pins:
  - The weight tables sum to 1.0 (defence against accidental
    drift breaking output_score's [0, 100] clamp).
  - resolve_structure_bias_weights / resolve_structure_bias_label
    handle valid + unknown + None inputs correctly.
  - _compute_output_ranking_entry produces different output_score
    for the same seg under different structure_bias values.
  - _apply_subtitle_emphasis returns the expected scaled value.
  - The orchestrator wires both fields through the call sites.
  - result_json.ranking_metadata surfaces applied_structure_bias
    and effective_formula (Strategic-4 metadata extended).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. structure_bias weight tables.
# ---------------------------------------------------------------------------


def test_structure_bias_weights_sum_to_one():
    """Each weight set MUST sum to 1.0 — output_score is computed as a
    weighted sum and the [0, 100] clamp depends on this. A drift to
    1.05 silently inflates scores; a drift to 0.95 silently deflates.
    The defence-in-depth assertion is cheap."""
    from app.features.render.engine.pipeline.pipeline_ranking import STRUCTURE_BIAS_WEIGHTS

    for bias, weights in STRUCTURE_BIAS_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, (
            f"STRUCTURE_BIAS_WEIGHTS[{bias!r}] does not sum to 1.0 "
            f"(sum={total!r}). Adjust the weights so the formula stays "
            f"a normalised weighted average."
        )


def test_structure_bias_balanced_matches_pre_strategic_1c_formula():
    """The 'balanced' weight set must mirror the pre-Strategic-1c
    hardcoded coefficients at pipeline_ranking.py:204-211 byte-for-byte
    so legacy callers + stored payloads behave identically."""
    from app.features.render.engine.pipeline.pipeline_ranking import STRUCTURE_BIAS_WEIGHTS

    balanced = STRUCTURE_BIAS_WEIGHTS["balanced"]
    assert balanced == {
        "viral":          0.35,
        "hook":           0.20,
        "retention":      0.20,
        "speech_density": 0.10,
        "market":         0.10,
        "duration_fit":   0.05,
    }


def test_structure_bias_hook_emphasises_hook_score():
    """The 'hook' bias must give hook_score MORE weight than the
    balanced default. The new value (0.30) is documented in the
    weight table; this test catches a refactor that silently flips
    the bias direction."""
    from app.features.render.engine.pipeline.pipeline_ranking import STRUCTURE_BIAS_WEIGHTS

    assert STRUCTURE_BIAS_WEIGHTS["hook"]["hook"] > STRUCTURE_BIAS_WEIGHTS["balanced"]["hook"]


def test_structure_bias_story_emphasises_retention_score():
    """Symmetric to the hook bias: 'story' must give retention MORE
    weight than balanced (operator's intent: long-form storytelling
    that holds the audience)."""
    from app.features.render.engine.pipeline.pipeline_ranking import STRUCTURE_BIAS_WEIGHTS

    assert STRUCTURE_BIAS_WEIGHTS["story"]["retention"] > STRUCTURE_BIAS_WEIGHTS["balanced"]["retention"]


# ---------------------------------------------------------------------------
# 2. Resolution helpers.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected_key",
    [
        ("hook", "hook"),
        ("HOOK", "hook"),       # case-insensitive
        (" balanced ", "balanced"),  # whitespace stripped
        ("story", "story"),
    ],
)
def test_resolve_structure_bias_weights_known_values(value, expected_key):
    """Valid values (case-insensitive, whitespace-tolerant) return
    the matching weight set."""
    from app.features.render.engine.pipeline.pipeline_ranking import (
        resolve_structure_bias_weights,
        STRUCTURE_BIAS_WEIGHTS,
    )
    assert resolve_structure_bias_weights(value) == STRUCTURE_BIAS_WEIGHTS[expected_key]


@pytest.mark.parametrize(
    "value",
    [None, "", "rumble_strip", "unknown", "balance"],  # 'balance' missing 'd'
)
def test_resolve_structure_bias_weights_unknown_defaults_to_balanced(value):
    """Unknown / None / case-mismatched values MUST default to the
    'balanced' weight set so stored payloads with garbage values
    don't accidentally re-weight."""
    from app.features.render.engine.pipeline.pipeline_ranking import (
        resolve_structure_bias_weights,
        STRUCTURE_BIAS_WEIGHTS,
    )
    assert resolve_structure_bias_weights(value) == STRUCTURE_BIAS_WEIGHTS["balanced"]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("hook", "hook"),
        ("HOOK", "hook"),
        ("balanced", "balanced"),
        ("story", "story"),
        (None, "balanced"),
        ("", "balanced"),
        ("unknown", "balanced"),
    ],
)
def test_resolve_structure_bias_label(value, expected):
    """resolve_structure_bias_label normalises the input to the
    canonical key. Used for persisting the choice into
    result_json.ranking_metadata.applied_structure_bias."""
    from app.features.render.engine.pipeline.pipeline_ranking import resolve_structure_bias_label

    assert resolve_structure_bias_label(value) == expected


# ---------------------------------------------------------------------------
# 3. _compute_output_ranking_entry behaviour.
# ---------------------------------------------------------------------------


def _ranking_seg(viral=80.0, hook=70.0, retention=60.0):
    """Minimal seg shape — only the score fields the entry computer reads."""
    return {
        "viral_score":          viral,
        "hook_score":            hook,
        "retention_score":       retention,
        "speech_density_score": 50.0,
        "mv_viral_score":       50.0,
        "duration_fit_score":   50.0,
        "continuity_score":     50.0,
        "content_type_hint":    "vlog",
    }


def test_compute_entry_balanced_default_matches_pre_strategic_1c():
    """With structure_bias=None, the computed output_score MUST match
    the pre-Strategic-1c balanced-formula value. Pre-Strategic-1c
    coefficients: viral 0.35 + hook 0.20 + retention 0.20 + density
    0.10 + market 0.10 + duration_fit 0.05.

    For seg(viral=80, hook=70, retention=60) with density=50,
    market=50, duration_fit=50:
      80*0.35 + 70*0.20 + 60*0.20 + 50*0.10 + 50*0.10 + 50*0.05
      = 28 + 14 + 12 + 5 + 5 + 2.5 = 66.5
    """
    from app.features.render.engine.pipeline.pipeline_ranking import _compute_output_ranking_entry

    entry = _compute_output_ranking_entry(
        part_no=1,
        seg=_ranking_seg(),
        output_file="out.mp4",
        structure_bias=None,
    )
    assert entry["output_score"] == pytest.approx(66.5, abs=0.05)


def test_compute_entry_hook_bias_boosts_high_hook_clip():
    """A clip with HIGH hook_score MUST score HIGHER under 'hook'
    bias than under 'balanced' bias. The whole point of the bias."""
    from app.features.render.engine.pipeline.pipeline_ranking import _compute_output_ranking_entry

    # Clip with strong hook (90) and weaker retention (40).
    seg = _ranking_seg(viral=70, hook=90, retention=40)
    balanced_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="balanced")
    hook_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="hook")

    assert hook_entry["output_score"] > balanced_entry["output_score"], (
        f"Strategic-1c regression — 'hook' bias did not boost a "
        f"high-hook clip's score above the balanced default. "
        f"balanced={balanced_entry['output_score']!r}, "
        f"hook={hook_entry['output_score']!r}."
    )


def test_compute_entry_story_bias_boosts_high_retention_clip():
    """Symmetric: 'story' bias scores a high-retention clip HIGHER
    than the balanced default."""
    from app.features.render.engine.pipeline.pipeline_ranking import _compute_output_ranking_entry

    seg = _ranking_seg(viral=70, hook=40, retention=90)
    balanced_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="balanced")
    story_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="story")

    assert story_entry["output_score"] > balanced_entry["output_score"]


def test_compute_entry_unknown_bias_defaults_to_balanced():
    """An unknown structure_bias value MUST produce the same score
    as 'balanced' (defence — stored payloads with garbage values
    don't accidentally re-weight)."""
    from app.features.render.engine.pipeline.pipeline_ranking import _compute_output_ranking_entry

    seg = _ranking_seg()
    balanced_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="balanced")
    unknown_entry = _compute_output_ranking_entry(1, seg, "x", structure_bias="rumble_strip")

    assert unknown_entry["output_score"] == balanced_entry["output_score"]


# ---------------------------------------------------------------------------
# 4. subtitle_emphasis multiplier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "size, emphasis, expected",
    [
        (46, None, 46),                   # default: no change
        (46, "balanced", 46),             # explicit balanced: no change
        (46, "subtle", 39),               # 46 * 0.85 = 39.1 → 39
        (46, "aggressive", 55),           # 46 * 1.20 = 55.2 → 55
        (46, "AGGRESSIVE", 55),           # case-insensitive
        (46, "  subtle  ", 39),           # whitespace tolerant
        (46, "unknown", 46),              # unknown → unchanged
        (0, "aggressive", 0),             # zero in → zero out (no_op for unset font)
        (100, "subtle", 85),              # 100 * 0.85 = 85
    ],
)
def test_apply_subtitle_emphasis(size, emphasis, expected):
    """The multiplier is documented in _SUBTITLE_EMPHASIS_MULTIPLIERS.
    Pin the behaviour: subtle 0.85x, balanced 1.0x, aggressive 1.20x,
    rounded to int and clamped to [10, 200] when applicable."""
    from app.features.render.engine.stages.part_asset_planner import _apply_subtitle_emphasis

    assert _apply_subtitle_emphasis(size, emphasis) == expected


def test_apply_subtitle_emphasis_clamps_large_aggressive_value():
    """Aggressive 1.20× of a huge font size must clamp to the 200pt
    ceiling. Defence against overflow into the ASS renderer."""
    from app.features.render.engine.stages.part_asset_planner import _apply_subtitle_emphasis

    # 200 * 1.20 = 240 → clamped to 200.
    assert _apply_subtitle_emphasis(200, "aggressive") == 200


def test_apply_subtitle_emphasis_clamps_tiny_subtle_value():
    """Subtle 0.85× of a tiny font must clamp to the 10pt floor."""
    from app.features.render.engine.stages.part_asset_planner import _apply_subtitle_emphasis

    # 8 * 0.85 = 6.8 → clamped to 10.
    assert _apply_subtitle_emphasis(8, "subtle") == 10


# ---------------------------------------------------------------------------
# 5. Strategic-4 metadata gains the new fields.
# ---------------------------------------------------------------------------


def _build_minimal_ctx(*, rank_source: str = "render_plan", structure_bias=None):
    """Construct a minimal FinalizeContext for testing the result_json
    shape. Mirrors the helper in test_strategic_4_ranking_metadata."""
    from app.features.render.engine.pipeline.pipeline_finalize import FinalizeContext
    from app.models.render import RenderRequest

    payload = RenderRequest(
        channel_code="t-strategic-1c",
        source_mode="local",
        source_video_path="/nonexistent.mp4",
        output_dir="/nonexistent/out",
        structure_bias=structure_bias,
    )

    return FinalizeContext(
        job_id="job-s1c",
        effective_channel="t-strategic-1c",
        payload=payload,
        started_at=datetime.utcnow(),
        output_dir=Path("/nonexistent/out"),
        output_stem="t_s1c",
        outputs=[],
        failed_parts=[],
        total_parts=0,
        scored=[],
        recovery_notes=[],
        rank_entries=[],
        rank_entries_ordered=[],
        best_rank_entry=None,
        partial_warning="",
        preset_name="",
        preset_id="",
        preset_label="",
        mv_parts=[],
        voice_summary="not used",
        subtitle_translate_summary="not used",
        render_plan=None,
        rank_source=rank_source,
    )


def _capture_result_payload(ctx) -> dict:
    """Run finalize and return the captured result_json dict."""
    from app.features.render.engine.pipeline import pipeline_finalize

    captured: dict = {}

    def _fake_upsert_job(job_id, kind, channel, status, payload, result, **kwargs):
        captured["result"] = result

    with patch.object(pipeline_finalize, "upsert_job", side_effect=_fake_upsert_job), \
         patch.object(pipeline_finalize, "_emit_render_event"), \
         patch.object(pipeline_finalize, "_job_log"):
        try:
            pipeline_finalize.run_render_finalize(ctx)
        except Exception:
            pass

    return captured.get("result", {})


def test_ranking_metadata_exposes_applied_structure_bias_default():
    """When the operator doesn't set structure_bias, the metadata
    must surface 'balanced' as the applied label and the canonical
    balanced weights as effective_formula."""
    result = _capture_result_payload(_build_minimal_ctx(structure_bias=None))
    rm = result["ranking_metadata"]

    assert rm["applied_structure_bias"] == "balanced"
    assert rm["effective_formula"] == {
        "viral_score":        0.35,
        "hook_score":         0.20,
        "retention_score":    0.20,
        "speech_density":     0.10,
        "market_score":       0.10,
        "duration_fit":       0.05,
    }


def test_ranking_metadata_exposes_applied_structure_bias_hook():
    """When operator picks 'hook', the metadata surfaces it AND the
    actual weights used. Strategic-4 + Strategic-1c interplay."""
    result = _capture_result_payload(_build_minimal_ctx(structure_bias="hook"))
    rm = result["ranking_metadata"]

    assert rm["applied_structure_bias"] == "hook"
    # The hook weight set: viral=0.30, hook=0.30, retention=0.10,
    # density=0.10, market=0.15, duration_fit=0.05.
    assert rm["effective_formula"]["hook_score"] == 0.30
    assert rm["effective_formula"]["retention_score"] == 0.10


def test_ranking_metadata_preserves_canonical_formula_field():
    """Strategic-4 backward-compat: the original `formula` field MUST
    keep showing the BALANCED weights even when structure_bias is
    non-default. Consumers that look at `formula` shouldn't see
    different values just because the operator set a bias."""
    result = _capture_result_payload(_build_minimal_ctx(structure_bias="story"))
    rm = result["ranking_metadata"]

    # `formula` (Strategic-4 field) stays canonical balanced.
    assert rm["formula"]["hook_score"] == 0.20
    assert rm["formula"]["retention_score"] == 0.20
    # `effective_formula` (Strategic-1c field) shows the actual weights.
    assert rm["effective_formula"]["retention_score"] == 0.30  # story-biased


def test_ranking_metadata_lists_documented_structure_bias_values():
    """structure_bias_documented lets consumers iterate the allowed
    values without re-implementing the enumeration. Useful for FE
    select widgets + lints."""
    result = _capture_result_payload(_build_minimal_ctx())
    rm = result["ranking_metadata"]

    assert set(rm["structure_bias_documented"]) == {"hook", "balanced", "story"}


# ---------------------------------------------------------------------------
# 6. Orchestrator wiring — source-level guard for both fields.
# ---------------------------------------------------------------------------


def test_orchestrator_passes_structure_bias_to_ranking_entry():
    """A refactor that drops the kwarg silently reverts to balanced
    weights — operators still set the field but the formula doesn't
    change."""
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "pipeline" / "render_pipeline.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    assert re.search(
        r"_compute_output_ranking_entry\([\s\S]*?structure_bias\s*=\s*getattr\("
        r"\s*payload\s*,\s*[\"']structure_bias[\"']",
        source,
    ), (
        "Strategic-1c regression — render_pipeline.py no longer "
        "passes structure_bias=getattr(payload, 'structure_bias', None) "
        "to _compute_output_ranking_entry. Operators still set the "
        "field but the formula no longer responds."
    )


def test_part_asset_planner_applies_subtitle_emphasis_at_top():
    """The emphasis MUST be resolved ONCE near the start of
    prepare_part_assets so the cache key + both ASS writers see the
    same value. A refactor that scatters multiple
    _apply_subtitle_emphasis calls risks inconsistent values across
    the cache key vs the actual ASS write."""
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "stages" / "part_asset_planner.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    # _apply_subtitle_emphasis MUST appear exactly once in
    # prepare_part_assets (the single resolution at the top). Other
    # appearances are in the helper definition + comments.
    direct_calls = re.findall(r"_apply_subtitle_emphasis\(_raw_sub_font_size", source)
    assert len(direct_calls) == 1, (
        f"Strategic-1c regression — _apply_subtitle_emphasis is called "
        f"{len(direct_calls)} times in part_asset_planner.py. The "
        f"resolution must happen ONCE at the top of prepare_part_assets "
        f"so the ASS cache key matches the writer call."
    )

    # The effective value MUST be used by the cache key + both writers
    # (3 call sites in prepare_part_assets).
    effective_uses = re.findall(r"\b_effective_sub_font_size\b", source)
    assert len(effective_uses) >= 4, (
        f"Strategic-1c regression — _effective_sub_font_size used "
        f"{len(effective_uses)} time(s) in part_asset_planner.py. "
        f"Expected at least 4 (the local binding line + 3 consumer "
        f"call sites). A drop means one ASS writer site is still "
        f"reading the raw payload font_size."
    )
