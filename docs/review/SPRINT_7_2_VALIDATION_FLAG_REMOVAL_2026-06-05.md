# Sprint 7.2 — `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` removal

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-2-validation-flag-removal`
**Baseline:** Pytest 2423 passed / 1 skipped / 0 failed @ `0c31323` (main, post Sprint 7.7 prep + Issue 2 close)
**Final pytest:** 2414 passed (-9 net) / 1 skipped / 0 failed
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.2 row + `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"Deprecation timeline"

## Purpose

Sprint 6 P0 HIGH (2026-06-05) added `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` as a 30-day opt-in escape hatch for users who relied on writing `base_clip.mp4` as an A/B forensics artifact when `FEATURE_BASE_CLIP_FIRST=1` but `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`. The settling period was scheduled to end 2026-07-05.

The user has elected to ship the removal early (same-day as Sprint 6 P0 HIGH itself) because:
1. Sole operator — no other consumers to surface during settling.
2. Zero usage observed.
3. Sprint 7.x execution velocity preference.

Risk assessment: the only behavior change for users who explicitly set `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1` is that the validation artifact stops being written. The render output itself is unchanged (the flag never affected `render_part_smart`'s final output, only whether the throwaway `base_clip.mp4` was written alongside). For the user's setup (no such opt-in active), this commit is a zero-behavior-change cleanup.

## What was deleted

### 5 module-level env reads (the drift-prevention mirror pattern)

| File | Lines deleted |
|---|---|
| `backend/app/orchestration/render_pipeline.py` | 116-125 (Sprint 6 P0 HIGH comment block + 3-line env read) |
| `backend/app/orchestration/stages/part_cut.py` | 87-89 (mirror env read) |
| `backend/app/orchestration/stages/part_renderer.py` | 28-31 (mirror env read) |
| `backend/app/orchestration/stages/part_render_setup.py` | 93-96 (mirror env read) |
| `backend/app/orchestration/stages/part_render_encode.py` | 110-113 (mirror env read) |

Each site replaced with a single-line breadcrumb comment citing this audit doc.

### 1 predicate-function kwarg

`backend/app/orchestration/stages/part_cut.py:97` — dropped `feature_base_clip_validation_artifact: bool` from `_should_skip_raw_part_write` signature. Body at `:125-127` simplified from:

```python
base_clip_will_render = feature_base_clip_first and (
    feature_overlay_after_base_clip or feature_base_clip_validation_artifact
)
```

to:

```python
base_clip_will_render = feature_base_clip_first and feature_overlay_after_base_clip
```

Call site at `:316` updated accordingly (dropped the kwarg).

### 1 gate-condition simplification

`backend/app/orchestration/stages/part_render_encode.py:171-174` — removed the `_base_clip_consumer_active` intermediate variable. The gate is now a plain `if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:`. Comment block at `:158-170` rewritten to cite Sprint 7.2 simplification + reference this audit doc.

### 2 test files updated

- `backend/tests/test_part_render_encode_base_clip_gate.py` rewritten:
  - Module docstring updated to reflect post-7.2 gate
  - `_gate(first, overlay)` helper signature dropped `validation` param
  - `TestGateTruthTable`: 6 cases → 4 cases (removed validation-specific rows)
  - `TestPipelineBlockGate`: 4 cases → 3 cases (removed validation-active case)
  - `TestValidationArtifactFlagDefault` DELETED entirely (2 cases)
  - `TestModuleLevelFlagReadsCoherent` (4 hasattr tests) RENAMED to `TestValidationArtifactFlagRemoved` (5 `not hasattr` absence pins — includes new pin on `part_cut.py` since Sprint 6 O-4 added it as a 5th site)
  - Source-pin test renamed from `_uses_consumer_check` to `_uses_simple_and` + inverted to assert flag string NOT in source
- `backend/tests/test_raw_part_skip_predicate.py` rewritten:
  - `_predicate(s, f1, f2, fv)` → `_predicate(s, f1, f2)` (dropped `fv`)
  - `TestSubtitleGateDominates`: 6 cases → 4 cases (removed 2 validation-specific rows)
  - `TestBaseClipConsumerGate`: 3 cases → 1 case (removed 2 validation-specific rows)
  - `TestPredicateFires`: 4 cases → 3 cases (renamed/consolidated; added `test_subtitle_off_first_on_no_overlay` to cover the FIRST=1 alone case that used to need explicit `VALIDATION=0` to fall through)
  - `TestKeywordOnlySignature`: positional-args call updated to 3 args (was 4)
  - `TestModuleLevelFlagReadsCoherent`: dropped the validation-hasattr test, added an inverted `not hasattr` absence pin
  - `TestSourcePin`: added `test_predicate_does_not_reference_validation_artifact` source-absence pin

Net test delta: -9 cases (matches the pytest baseline shift 2423 → 2414).

## Sacred Contracts walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases | No | unchanged |
| #2 RenderRequest additive | Spirit engaged (controlled flag removal) | Mitigated: the flag was a 30-day opt-in by design; zero usage observed; documented as planned in `SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"Deprecation timeline". Operators who had set the flag now see the same render output (the flag never affected the final mp4 — only the throwaway base_clip.mp4 artifact). |
| #3 AI returns None | No | unchanged |
| #4 Job stage frozen | No | unchanged |
| #5 Part stage frozen | No | `CUTTING` upsert still unconditional in `run_cut_stage` |
| #6 `_emit_render_event` signature | No | signature unchanged. The `subtitle_style_applied` event's recently-added `ass_cache_hit` (Sprint 7.3) is unaffected. |
| #7 `data/app.db` | No | unchanged |
| #8 `qa_pipeline` | No | qa reads final_part only, never base_clip.mp4 |
| Performance Protections (NVENC) | Improved | One fewer base_clip render in the FIRST=1 + VALIDATION=1 configuration (which no longer exists). NVENC budget unchanged for default configs. |

## Behavior diff: pre vs post Sprint 7.2

| Config | Pre-Sprint-7.2 | Post-Sprint-7.2 |
|---|---|---|
| All flags OFF (default) | Skip base_clip | Skip base_clip (unchanged) |
| FIRST=1, OVERLAY=0, VALIDATION=0 | Skip base_clip (Sprint 6 P0 HIGH win) | Skip base_clip (unchanged) |
| FIRST=1, OVERLAY=0, **VALIDATION=1** | Write base_clip as throwaway A/B artifact | **Skip base_clip — VALIDATION flag no longer exists** |
| FIRST=1, OVERLAY=1, VALIDATION=0 | Write base_clip, composite consumer reads it | Write base_clip (unchanged) |
| FIRST=1, OVERLAY=1, VALIDATION=1 | Write base_clip, composite consumer reads it | Write base_clip (unchanged — VALIDATION irrelevant when OVERLAY active) |

Only one row changed behavior — the third one. For an operator who explicitly set `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1`, the throwaway artifact stops being written. The final rendered output (`render_part_smart` produces it) is unchanged.

## What this sprint does NOT do

- Does NOT change `render_base_clip` itself. Untouched.
- Does NOT change `composite_overlays_on_base_clip`. Untouched.
- Does NOT change `render_part_smart`. Untouched.
- Does NOT touch `raw_part` write site. (Sprint 7.4 will do that.)
- Does NOT change any FFmpeg argv.
- Does NOT alter API contracts.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.2 row — scoped this work
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"Deprecation timeline" — the original 30-day settling commitment
- `docs/review/SPRINT_7_EXECUTION_PLAN_2026-06-05.md` Phase 1 — execution runbook entry
- `backend/app/orchestration/render_pipeline.py:115-124` — Sprint 7.2 removal breadcrumb
- `backend/app/orchestration/stages/part_render_encode.py:158-167` — simplified gate
- `backend/app/orchestration/stages/part_cut.py:87-89, 92-128` — predicate sans validation kwarg
- `backend/tests/test_part_render_encode_base_clip_gate.py` — post-Sprint-7.2 truth table
- `backend/tests/test_raw_part_skip_predicate.py` — post-Sprint-7.2 predicate truth table
