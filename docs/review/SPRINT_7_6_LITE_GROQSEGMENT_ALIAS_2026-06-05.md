# Sprint 7.6 LITE — `GroqSegment` backward-compat alias deletion

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-6-lite-groqsegment-alias-deletion`
**Baseline:** Pytest 2415 passed / 1 skipped / 0 failed @ `6cf04dc` (main, post Sprint 7.5)
**Final pytest:** 2415 passed / 1 skipped / 0 failed (zero behavior change)
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.6 row (re-scoped from FULL to LITE per architecture finding below)

## Sprint 7.6 architecture finding — load-bearing for future planning

The original Sprint 7.6 scope (`SPRINT_PLAN_2026-06-05.md` + `SPRINT_7_EXECUTION_PLAN_2026-06-05.md` Phase 3) called for deleting `LLMSegment` dataclass + `select_segments` paths in 4 providers + `_to_scored_dict` consumer. During the surgical-edit audit on 2026-06-05, the Planner-equivalent inspection surfaced a critical architectural detail:

**`LLMSegment` + `select_segments` + `_to_scored_dict` are NOT a fallback path. They are the LOAD-BEARING production code path that builds the `scored` list consumed by the entire downstream pipeline.**

### Call chain audit

1. `backend/app/orchestration/render_pipeline.py::run_render_pipeline` calls `run_llm_pre_render` FIRST.
2. `backend/app/orchestration/llm_pipeline.py:317` — `scored = run_llm_segment_selection(...)` produces the `scored: list` field that lives on `LLMPreRenderResult`.
3. `backend/app/orchestration/llm_stage.py::run_llm_segment_selection` calls the dispatcher's `select_segments` and runs `_to_scored_dict` over each returned `LLMSegment` to produce the `scored` list.
4. The downstream pipeline (segment selection, ranking, per-part loop, every `stages/part_*.py` consumer) reads from `scored`. There is no alternative source.

Sprint 4.D's `select_render_plan` AI emission (Sprint 7.6a flag flip enabled it by default) is **additive**: it runs SECOND, after `run_llm_pre_render`, and produces `ctx.render_plan` for **stage decisions** (subtitle_policy / camera_strategy / rank). It does NOT produce `scored`.

**Consequence:** Deleting `LLMSegment` + `select_segments` + `_to_scored_dict` as a unit would leave the pipeline with no `scored` source — render breaks entirely. The original Sprint 7.6 scope was based on a misreading of the dual-mode wiring.

### Real Sprint 7.6 (FULL) options

Three architectural options exist; each warrants its own Planner cycle:

| Option | Approach | Effort |
|---|---|---|
| **FULL-A** | Build `scored` from `RenderPlan.clips` when available; keep legacy `select_segments` as TRUE fallback for AI-failure | 8-10 commits, large refactor of `llm_pipeline.py` data flow |
| **FULL-B** | RenderPlan-native pipeline: delete `scored` entirely; downstream stages read `RenderPlan.clips` directly | Even larger; touches every downstream consumer |
| **FULL-C** | Status quo + delete only provably-dead alias (`GroqSegment`) | 1 small commit (THIS sprint) |

User picked Option C — Sprint 7.6 LITE.

## What this sprint deletes

### `GroqSegment = LLMSegment` alias at `backend/app/ai/llm/parser.py:55`

Caller audit (grep across `d:/tool-render-video`):

```
backend/app/ai/llm/parser.py     — defines the alias (this commit deletes)
docs/review/SPRINT_PLAN_2026-06-05.md     — text mention, not code reference
docs/review/SPRINT_7_EXECUTION_PLAN_2026-06-05.md     — text mention
docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md     — text mention
docs/review/GROQ_WORKFLOW_ARCH_2026-05-30.md     — text mention
```

**Zero code references** in production OR tests. The alias was a backward-compat hedge in case downstream code imported `GroqSegment` — verified at audit time that NO module does.

The deletion is a one-line removal (plus a breadcrumb comment).

## What this sprint preserves

- `LLMSegment` dataclass — load-bearing
- `select_segments` in 4 providers — load-bearing
- `_to_scored_dict` in `llm_stage.py:263` — load-bearing
- `parse_segment_response` + `_dict_to_segment` in `parser.py` — load-bearing (called by all 4 providers' `select_segments` impl)
- All `LLMSegment` imports in 3 test files — load-bearing (test the providers)

## Sacred Contracts walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1-#8 | No | unchanged |
| Performance Protections | No | unchanged |

Pure dead-code deletion, zero behavior surface.

## Pytest

```
Baseline:  2415 passed / 1 skipped / 0 failed
Post-edit: 2415 passed / 1 skipped / 0 failed (unchanged)
```

Zero test changes — the deleted alias had zero consumers.

## What this sprint does NOT do

- Does NOT delete `LLMSegment`, `select_segments`, `_to_scored_dict`, `parse_segment_response`, or `_dict_to_segment`.
- Does NOT touch the 4 provider modules.
- Does NOT touch `llm_stage.py` or `llm_pipeline.py`.
- Does NOT touch the anti-import pin tests at `test_render_pipeline_llm_emit_flag.py:124` or `test_render_pipeline_render_plan_wiring.py:139`.
- Does NOT close out the broader Sprint 7.6 scope — that requires a fresh Planner cycle citing this audit.

## Re-scoped Sprint 7.6 FULL — preconditions for any future re-opening

1. Production telemetry on `render.plan.ai_emitted` vs `render.plan.ai_fallback` ratio across multiple release cycles (already a Sprint 7.6 gate per the original execution plan).
2. Architectural decision: FULL-A vs FULL-B (must be made by user + Planner, not by inline deletion).
3. Render-engine integration test on the RenderPlan-derived `scored` path (currently absent — must be authored before any code change).
4. Manual visual review on 3-5 sample renders covering the new derivation path.
5. Documented fallback semantics: what happens when `select_render_plan` returns None AND `scored` derivation has nothing to fall back to?

Until those preconditions are met, the deletion of `LLMSegment` / `select_segments` / `_to_scored_dict` stays explicitly out of scope.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.6 row — original (mis-scoped) intent
- `docs/review/SPRINT_7_EXECUTION_PLAN_2026-06-05.md` Phase 3 — original execution-plan entry
- `docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md` — the flag flip that the original Sprint 7.6 was supposed to follow
- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §3 — the audit that listed LLMSegment for "Sprint 5 cleanup"
- `docs/review/SPRINT_4_2026-06-04.md:31` — the original "defer LLMSegment cleanup" note that this audit retroactively justifies
- `backend/app/ai/llm/parser.py:54-57` (post-deletion) — the breadcrumb comment that replaced the alias
- `backend/app/orchestration/llm_pipeline.py:317-320` — the load-bearing `scored = run_llm_segment_selection(...)` call site
- `backend/app/orchestration/llm_stage.py:258-260` — the `_to_scored_dict` consumer

## Honest verdict for the audit ledger

The session-level Sprint 7.6 scope was based on the Sprint 7.6a default-flip "trust dual-mode safety net" framing. That framing presumed AI emission was an additive layer ON TOP of legacy. The reality is the opposite: legacy is the load-bearing source of `scored`, AI emission is the additive layer on top of legacy. Deleting legacy leaves nothing to be additive against.

This is the most important finding from the 2026-06-05 session for future Sprint 7.6 planning. Future agents should index from this audit doc, NOT from the SPRINT_PLAN row.
