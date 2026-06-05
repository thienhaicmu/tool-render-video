# Sprint 7.6 FULL — RenderPlan-derived `scored` (Plan)

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-6-full-renderplan-derived-scored` (off `feature/render-engine-upgrade`)
**Baseline expected:** 2439 passed / 1 skipped / 0 failed (verify before edit)
**Tier:** HIGH-CRITICAL (touches `render_pipeline.py`)
**Status:** APPROVED 2026-06-05 (architect plan via Agent Team Protocol)

---

## Purpose

When AI emission succeeds (`_render_plan is not None`), derive the `scored` list from `RenderPlan.clips` instead of using the legacy `select_segments → _to_scored_dict` output that `run_llm_pre_render` already produced. When AI emission fails or is flag-disabled, keep `scored` exactly as `run_llm_pre_render` returned it (legacy path) — byte-identical to Sprint 7.6a behaviour.

The legacy path stays alive. `LLMSegment` + `select_segments` + `_to_scored_dict` are **not** deleted. They remain the fallback authority. AI emission becomes the source of truth on the happy path only.

---

## Architectural finding (load-bearing context)

The Sprint 7.6 LITE finding (`SPRINT_7_6_LITE_GROQSEGMENT_ALIAS_2026-06-05.md`) discovered that `_render_plan` block at `render_pipeline.py:474-595` does NOT replace `scored`. It only persists the plan, emits events, and lets `_resolve_rank_from_plan` consume `RenderPlan.clips[i].rank` for ranking in the per-part loop. The full call chain on the AI-emit happy path TODAY:

1. `llm_pipeline.run_llm_pre_render` builds `scored` via `select_segments → _to_scored_dict` (legacy).
2. `render_pipeline.py:474-595` ALSO calls `select_render_plan` (which calls the LLM A SECOND TIME) and persists the plan. `scored` is not touched.
3. Downstream pipeline reads `scored` (from step 1) for timing + everything except rank.
4. `_resolve_rank_from_plan` consumes `_render_plan.clips[i].rank` for ranking only.

The "AI is called twice on the happy path" is pre-existing inefficiency — flagged as **out of scope** below (Sprint 7.6b). Sprint 7.6 FULL introduces the data-flow seam (`scored` derived from `_render_plan`) that a future sprint can use to eliminate the second call. This sprint does not eliminate it.

---

## Files touched

| File | Action | What |
|---|---|---|
| `backend/app/orchestration/render_pipeline.py` | modify | New module-scope helper `_scored_from_render_plan` (~80 LOC). Insertion block after L595 that REPLACES `scored` when `_render_plan is not None` (~20 LOC + event emit). |
| `backend/app/domain/render_plan.py` | modify (additive) | Add `subtitle_style: str = ""` field to `ClipPlan`. |
| `backend/app/ai/llm/parser.py` | modify (additive) | Add `subtitle_style` to `_segment_to_clip_dict` mapping. |
| `backend/tests/test_render_pipeline_scored_from_render_plan.py` | new | ~10 tests pinning derivation + parity + Sacred Contract. |
| `backend/tests/test_render_pipeline_render_plan_wiring.py` | modify | +2 pins (helper importable + source-level conditional). |

**LOC estimate:** ~120 prod + ~265 test = ~385 total.

---

## Detailed change specs

### A. New helper `_scored_from_render_plan` in `render_pipeline.py`

Insert at module scope, near the other private helpers:

```python
def _scored_from_render_plan(render_plan, fallback_scored: list) -> list:
    """Derive scored-shaped list from RenderPlan.clips.

    Sprint 7.6 FULL — when AI emission produced a RenderPlan
    (LLM_EMIT_RENDER_PLAN=1 happy path), this builds the scored list
    directly from RenderPlan.clips instead of relying on the legacy
    LLMSegment → _to_scored_dict chain.

    The shape MUST match _to_scored_dict's output (llm_stage.py:263)
    key-for-key. Any divergence breaks downstream consumers that
    string-match field names.

    fallback_scored is used when render_plan is None / clips empty.
    The function NEVER raises — Sacred Contract #3 spirit. Any
    unexpected error returns fallback_scored unchanged so the render
    keeps moving.
    """
    try:
        if render_plan is None or not getattr(render_plan, "clips", None):
            return fallback_scored
        derived: list[dict] = []
        for clip in render_plan.clips:
            _base = float(getattr(clip, "score", 0.0) or 0.0) * 100.0
            _viral = (float(getattr(clip, "viral_score", 0.0) or 0.0) * 100.0) or _base
            _hook  = (float(getattr(clip, "hook_score", 0.0) or 0.0) * 100.0) or _base
            _ret   = (float(getattr(clip, "retention_score", 0.0) or 0.0) * 100.0) or _base
            _start = float(getattr(clip, "start", 0.0) or 0.0)
            _end = float(getattr(clip, "end", 0.0) or 0.0)
            _cover = float(getattr(clip, "cover_offset_ratio", 0.0) or 0.0)
            derived.append({
                "start":    _start,
                "end":      _end,
                "duration": _end - _start,
                "viral_score":     _viral,
                "hook_score":      _hook,
                "motion_score":    50.0,
                "diversity_score": 50.0,
                "retention_score": _ret,
                "audio_energy":    50.0,
                "clip_name": str(getattr(clip, "clip_name", "") or ""),
                "ai_title":  str(getattr(clip, "title", "") or ""),
                "ai_reason": str(getattr(clip, "reason", "") or ""),
                "source":    "render_plan",
                "ai_subtitle_style":  str(getattr(clip, "subtitle_style", "") or ""),
                "content_type_hint":  str(getattr(clip, "content_type", "") or ""),
                "hook_type":          str(getattr(clip, "hook_type", "") or ""),
                "cover_hint_ratio":   _cover if _cover > 0 else None,
                "speech_density":     float(getattr(clip, "speech_density", 0.0) or 0.0),
                "duration_fit_score": float(getattr(clip, "duration_fit", 0.0) or 0.0) * 100.0,
            })
        return derived
    except Exception:
        return fallback_scored
```

### B. Insertion point in `run_render_pipeline`

After the existing `_render_plan = ...` block (currently at L474-595), BEFORE the `existing_parts = ...` line. Diff sketch:

```python
        except Exception as _plan_exc:
            logger.warning("render_plan wire-up failed (non-fatal): %s", _plan_exc)
            _render_plan = None

        # Sprint 7.6 FULL — derive scored from RenderPlan when AI emit succeeded.
        if _render_plan is not None:
            _scored_before = scored
            scored = _scored_from_render_plan(_render_plan, fallback_scored=scored)
            if scored is not _scored_before:
                total_parts = len(scored)
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.plan.scored_derived",
                    level="INFO",
                    message=f"scored derived from RenderPlan: {len(scored)} clips",
                    step="render.llm_pipeline",
                    context={
                        "clips_count": len(scored),
                        "source": "render_plan",
                        "fallback_count": len(_scored_before),
                    },
                )

        existing_parts = {int(x["part_no"]): x for x in list_job_parts(job_id)}
```

**Critical:** `total_parts` is reassigned because `select_render_plan` is bounded by `output_count` but may produce a different valid-clip count than `select_segments`.

### C. Additive `ClipPlan.subtitle_style` field

In `backend/app/domain/render_plan.py`:

```python
content_type: str = ""
subtitle_style: str = ""    # Sprint 7.6 FULL — viral|clean|story|gaming|"" = inherit
viral_score: float = 0.0
```

Sacred Contract #2 compliant: additive, defaults to `""` (most conservative = inherit).

### D. Update `_segment_to_clip_dict` in `parser.py`

```python
"content_type": seg.get("content_type", ""),
"subtitle_style": seg.get("subtitle_style", ""),
"viral_score": seg.get("viral_score", 0.0),
```

---

## `scored` field shape inventory (parity contract)

Every key `_to_scored_dict` produces must be derivable. All keys are derivable from `ClipPlan` either directly, by scaling (×100 for 0-1 → 0-100), or via documented constant defaults (50.0 for motion/diversity/audio_energy — same as legacy neutral defaults). Only schema addition: `ClipPlan.subtitle_style` (to source `ai_subtitle_style`).

Intentional divergence: `source: "llm" → "render_plan"` (telemetry discriminator). Grep audit confirmed zero string-match consumers.

---

## Sacred Contracts walk

| # | Engages? | Disposition |
|---|---|---|
| #1 result_json aliases | YES (verify) | Derivation runs BEFORE rank-mirror loop. Aliases set unchanged. Pinned by test. |
| #2 RenderRequest additive | No new RenderRequest field. `ClipPlan.subtitle_style` defaults `""`. |
| #3 AI never raises | Spirit | Helper has bare try/except, returns fallback on any error. |
| #4 Job stage frozen | No |
| #5 Part stage frozen | No |
| #6 `_emit_render_event` shape | No | New `render.plan.scored_derived` event uses existing signature. |
| #7 `data/app.db` sole | No |
| #8 qa_pipeline never bypassed | No |

---

## Test plan

**New file `backend/tests/test_render_pipeline_scored_from_render_plan.py`:**

1. `test_helper_returns_fallback_when_render_plan_is_none`
2. `test_helper_returns_fallback_when_clips_empty`
3. `test_helper_returns_fallback_on_attribute_error`
4. `test_helper_field_shape_matches_to_scored_dict` (DUAL-PATH PARITY — critical)
5. `test_helper_preserves_zero_score_neutral_fallback`
6. `test_helper_cover_hint_ratio_zero_becomes_none`
7. `test_helper_source_field_is_render_plan`
8. `test_helper_subtitle_style_round_trips_from_clip`
9. `test_clipplan_subtitle_style_defaults_to_empty_string`
10. `test_helper_total_parts_reflects_len_scored`

**Modify `tests/test_render_pipeline_render_plan_wiring.py`:**

11. `test_scored_from_render_plan_is_importable`
12. `test_legacy_scored_path_unchanged_when_render_plan_none` (source-grep pin)

**Existing tests MUST still pass** — full pytest baseline (2439 passed) preserved.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Field-shape divergence breaks downstream consumer silently | Dual-path parity test pins every key |
| `total_parts` mismatch crashes per-part loop | Reassign `total_parts = len(scored)` in insertion block |
| `select_render_plan` and `select_segments` produce different clip counts | Trust AI plan; operator rollback via `LLM_EMIT_RENDER_PLAN=0` |
| Sacred Contract #1 keys missing in result_json | Derivation runs BEFORE ranking; ranking unchanged |
| Cover_offset_ratio None vs 0.0 boundary | Test mirrors `_to_scored_dict` line 291 |

---

## Rollback

1. **Operator-level (instant):** `LLM_EMIT_RENDER_PLAN=0` in env. Helper returns fallback unchanged.
2. **Code-level partial:** delete insertion block. Helper becomes unused but harmless. `ClipPlan.subtitle_style` additive, harmless.
3. **Code-level full:** `git revert` the sprint's commits.

**No new flag** added — existing `LLM_EMIT_RENDER_PLAN` is sufficient. Adding a redundant `SCORED_FROM_RENDER_PLAN` flag is over-engineering.

---

## What this sprint does NOT do

1. Does NOT delete `LLMSegment`, `select_segments`, `_to_scored_dict`, or `parse_segment_response`.
2. **Does NOT eliminate the double-LLM call** on the AI happy path. Deferred to **Sprint 7.6b**.
3. Does NOT migrate downstream stages to read `RenderPlan.clips` directly.
4. Does NOT touch `_resolve_rank_from_plan`.
5. Does NOT add new env flags.
6. Does NOT modify `qa_pipeline.py`, `_emit_render_event`, stage names, or any other Sacred Contract surface.
7. Does NOT touch `motion_crop.py`, `part_renderer.py`, or any other CRITICAL file beyond `render_pipeline.py`.

---

## Cross-references

- `docs/review/SPRINT_7_6_LITE_GROQSEGMENT_ALIAS_2026-06-05.md` — architecture finding
- `docs/review/SPRINT_PLAN_2026-06-05.md` — Sprint 7.6 row
- `docs/RENDERPLAN.md` — RenderPlan dataclass contract
- `backend/app/orchestration/render_pipeline.py:474-595` — _render_plan block
- `backend/app/orchestration/llm_stage.py:263` — `_to_scored_dict` (parity reference)
- `backend/app/orchestration/llm_pipeline.py:88-130` — mandatory LLM path
