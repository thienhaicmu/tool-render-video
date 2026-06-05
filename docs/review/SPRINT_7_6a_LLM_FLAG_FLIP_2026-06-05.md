# Sprint 7.6a — Flip `LLM_EMIT_RENDER_PLAN=1` default ON

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-6a-llm-flag-flip`
**Baseline:** Pytest 2422 passed / 1 skipped / 0 failed @ `7967c90` (main, post Sprint 7.3)
**Final pytest:** 2423 passed (+1 new) / 1 skipped / 0 failed
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` §"Sprint 7.6 — pre-gate decision" — *"User explicitly approves the LLM_EMIT_RENDER_PLAN=1 default flip. This is a separate small sprint preceding Sprint 7.6 itself."*

## Purpose

Sprint 7.6 retires the legacy `select_segments` path + `LLMSegment` dataclass + `_to_scored_dict` consumer. Its gate is **≥ 1 release cycle of `LLM_EMIT_RENDER_PLAN=1` running clean in production**. This sprint ships the default-flip that starts that release-cycle clock.

The flag's behavior contract was wired in Sprint 4.D (`render_pipeline.py:457-552`) with a defensive dual-mode: AI emission failure leaves `_render_plan = None` and the legacy resolvers continue. That dual-mode is the foundation that makes flipping the default safe — render output is unchanged on the bad-AI-day branch.

## Code changes (single commit)

### 1. `backend/app/orchestration/render_pipeline.py:134`

```diff
- _FEATURE_LLM_EMIT_RENDER_PLAN: bool = os.getenv("LLM_EMIT_RENDER_PLAN", "0") == "1"
+ _FEATURE_LLM_EMIT_RENDER_PLAN: bool = os.getenv("LLM_EMIT_RENDER_PLAN", "1") == "1"
```

Plus comment block at lines 116-133 updated to explain the flip + the dual-mode safety net + the 3-second rollback.

### 2. `backend/app/orchestration/pipeline_ranking.py:310` (mirror)

```diff
- if _os.getenv("LLM_EMIT_RENDER_PLAN", "0") != "1":
+ if _os.getenv("LLM_EMIT_RENDER_PLAN", "1") != "1":
```

Per-call read (NOT module-load) so tests can monkeypatch without reload gymnastics. Strict `!= "1"` compare preserved — anything other than `"1"` opts out, including the explicit `"0"` rollback.

### 3. Test inversions + new escape-hatch pin

| File | Test | Before | After |
|---|---|---|---|
| `tests/test_render_pipeline_llm_emit_flag.py:37-43` | `test_flag_defaults_off_when_env_unset` → rename `test_flag_defaults_on_when_env_unset` | unset → False | unset → True |
| `tests/test_render_pipeline_llm_emit_flag.py` (NEW) | `test_flag_off_when_env_set_to_0_explicitly` | n/a | `"0"` → False (Sprint 7.6a escape-hatch pin) |
| `tests/test_pipeline_ranking_render_plan_consume.py:84-87` | `test_flag_unset_returns_fallback` → rename `test_flag_unset_returns_consume_path` | unset → fallback | unset → mapping with `"render_plan"` source |

Existing tests that explicitly set the env to `"1"`, `"0"`, `"true"`, etc. continue to pass unchanged (strict `== "1"` contract preserved).

### 4. Non-ledger docs updated in same commit

- `docs/RENDERPLAN.md:243` — Sacred Contract #2 walk updated to reflect "default ON since Sprint 7.6a" + the dual-mode mitigation + 3-second rollback escape hatch.
- `docs/RENDER_PIPELINE.md:219-235` — "Two emission paths" section: `LLM_EMIT_RENDER_PLAN=1` now flagged as default, `=0` flagged as opt-out.

`docs/review/**` audit ledger NOT touched (append-only per CLAUDE.md). This audit doc is the new ledger entry.

## Behavior diff: OFF (current) vs ON (proposed)

| Aspect | OFF (pre-Sprint-7.6a) | ON (Sprint 7.6a default) |
|---|---|---|
| `select_segments` (legacy) | Runs | **Still runs** (NOT deleted by this sprint) |
| `select_render_plan` (AI emission) | Skipped | Attempts; falls back on None/exception |
| `ctx.render_plan` | None | `RenderPlan` instance on success; None on failure |
| `subtitle_policy` consume | Legacy 5-tier | Per-field merge with plan; empty fields → legacy |
| `camera_strategy` consume | `payload.reframe_mode` | Plan override; empty → legacy |
| `ClipPlan.rank` consume | Score-descending | Plan sequential 1..N when valid; None → fallback |
| `render.plan.ai_emitted` event | Never | Fires on AI success |
| `render.plan.ai_fallback` event | Never | Fires on AI None/exception (with reason tag) |
| `render.plan.persisted` event | Never | Fires after `jobs_repo.update_render_plan` succeeds |
| `jobs.render_plan_json` column | NULL | Populated on success; NULL on AI failure |
| Operator override | n/a | `LLM_EMIT_RENDER_PLAN=0` reverts to OFF behaviour |

**Bidirectional-safe fallback (the load-bearing safety net):**
- Outer try/except at `render_pipeline.py:457-552` wraps the entire AI-emission block. Catches every exception class.
- On exception: emits `render.plan.ai_fallback` with `reason="exception"` + traceback context, sets `_render_plan = None`. Render continues identical-to-OFF.
- On `None` return from `select_render_plan`: emits `render.plan.ai_fallback` with `reason="select_render_plan_returned_none"`, sets `_render_plan = None`. Render continues identical-to-OFF.
- AI provider modules (`backend/app/ai/llm/*`) honour Sacred Contract #3 internally — they return None on any internal failure rather than raising.

Net: AI emission **cannot crash a render**. Worst case = legacy `scored` list (already built upstream in `llm_stage.run_llm_segment_selection`) drives the per-stage legacy resolvers. Identical-to-OFF output.

## Sacred Contracts walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases (`output_rank_score`, `is_best_output`, `is_best_clip`) | No | `_compute_output_ranking_entry` writes the three keys unconditionally at `pipeline_ranking.py:225-247`, BEFORE any consume-vs-fallback branch. Pinned by existing tests. |
| #2 RenderRequest additive (spirit: conservative defaults) | **Engaged** | The flag is NOT a `RenderRequest` field — it's a module-load env var read. But the SPIRIT ("don't activate features on replay/upgrade without consent") is engaged: stored jobs replayed after the flip use AI emission too. **Mitigations:** dual-mode fallback (above), legacy path NOT deleted (Sprint 7.6 follows), explicit `LLM_EMIT_RENDER_PLAN=0` opt-out, single-commit revert. |
| #3 AI modules return None on failure | Honored | AI providers + outer try/except both honour. |
| #4 Job stage names frozen | No | Unchanged. |
| #5 Part stage names frozen | No | Unchanged. |
| #6 `_emit_render_event` signature | No | Signature unchanged. Existing events (`render.plan.ai_emitted`, `render.plan.ai_fallback`, `render.plan.persisted`) wired in Sprint 4.D conform to the frozen shape. |
| #7 `data/app.db` sole authority | No | `render_plan_json` column was added by migration 0001 (Sprint 2.1); writes happen via the existing `jobs_repo.update_render_plan` helper. No new schema. |
| #8 `qa_pipeline` never bypassed | No | qa reads `final_part` only. Unchanged. |

## Rollback path (3-second escape hatch)

### Operator-side (fastest)

```bash
# POSIX
export LLM_EMIT_RENDER_PLAN=0

# PowerShell
$env:LLM_EMIT_RENDER_PLAN = "0"

# Restart backend
```

The strict `== "1"` compare means any value other than `"1"` (including `"0"`, `"true"`, `"yes"`, empty string) leaves the flag OFF. The explicit `"0"` is the documented contract; anything else stays OFF defensively.

### Git-side (single SHA revert)

```bash
git revert <sprint-7-6a-commit-sha>
git push origin main
```

Restores the `"0"` default. No state migration needed — the env-var read is module-load.

### Silent backstop (no operator action needed)

Even without env override or revert, the dual-mode try/except at `render_pipeline.py:457-552` already catches every AI-emission failure and continues with `_render_plan = None` → identical-to-OFF behaviour at the resolver layer. The flip only changes what is *attempted* — the *output* of a failed attempt is byte-identical to the pre-flip baseline.

## Sprint 7.6 deletion timeline

| Date | Milestone |
|---|---|
| 2026-06-05 | Sprint 7.6a commit ships (this sprint) |
| 2026-06-05 + N days | Production telemetry collected on `render.plan.ai_emitted` vs `render.plan.ai_fallback` event ratio. Healthy ratio = AI emission landing correctly. |
| After ≥ 1 production release with flag default ON | Sprint 7.6 ready to scope: delete `LLMSegment`, `_to_scored_dict`, legacy `select_segments` paths in 4 providers + dispatcher |

The 1-release waiting period exists to surface AI-emission edge cases on real workloads before the legacy escape hatch is removed.

## Pytest

```
Baseline (before this sprint): 2422 passed / 1 skipped / 0 failed
Expected after flip:           2423 passed / 1 skipped / 0 failed
Actual after flip:             2423 passed (+1 new) / 1 skipped / 0 failed ✅
```

The +1 net is the new `test_flag_off_when_env_set_to_0_explicitly` Sacred Contract #2 escape-hatch pin. The two inverted tests (renamed `_defaults_on_` and `_unset_returns_consume_path`) preserve their case count.

## What this sprint does NOT do

- Does NOT delete `LLMSegment`, `_to_scored_dict`, `select_segments`, `_dict_to_segment`, or `parse_segment_response`. Those are Sprint 7.6 scope.
- Does NOT change provider modules (`ai/llm/claude_provider.py`, `gemini_provider.py`, `openai_provider.py`, dispatcher `__init__.py`). Sprint 7.6 scope.
- Does NOT change `llm_stage.run_llm_segment_selection` — the legacy `select_segments` call still happens upstream of the flag check. Sprint 7.6 will retire it.
- Does NOT touch CLAUDE.md (the flag is referenced only as a cross-ref, not a default-value statement).
- Does NOT touch `docs/review/**` audit ledger (append-only per CLAUDE.md).

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.6 row + pre-gate decision — scoped this work
- `docs/review/SPRINT_4_2026-06-04.md` — the Sprint 4 closure that wired the dual-mode and chose default OFF
- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §3 — LLMSegment defer context (Sprint 7.6 prerequisite)
- `docs/review/MIGRATION_COMPLETE_2026-06-04.md:109,138` — historical default-OFF references (NOT updated — append-only)
- `backend/app/orchestration/render_pipeline.py:134` — the env read (this commit's primary change)
- `backend/app/orchestration/render_pipeline.py:457-552` — the dual-mode try/except (the safety net)
- `backend/app/orchestration/pipeline_ranking.py:310` — the mirror env read
- `backend/app/ai/llm/__init__.py` — `select_render_plan` dispatcher (called when flag is ON)
- `docs/RENDERPLAN.md` + `docs/RENDER_PIPELINE.md` — non-ledger docs updated in this commit
- `backend/tests/test_render_pipeline_llm_emit_flag.py` — test invert + new escape-hatch pin
- `backend/tests/test_pipeline_ranking_render_plan_consume.py` — consume-path test invert
- `CLAUDE.md` Sacred Contracts §2 (additive spirit), §3 (AI returns None), §6 (event signature)

## Cross-references to subsequent sprints

After Sprint 7.6a ships and ≥ 1 release cycle elapses with clean production telemetry:
- **Sprint 7.6** can ship: delete `LLMSegment`, `_to_scored_dict`, legacy `select_segments` in 4 providers + dispatcher.
- **Sprint 7.5** (groq_* deletion) is independent — its gate is migration 0002 having run on every production DB. Can ship in parallel.

If telemetry shows excessive `render.plan.ai_fallback` events (e.g. > 20% of renders falling back), Sprint 7.6a is **paused** with a follow-up audit doc and Sprint 7.6 stays gated until the AI emission stabilises.
