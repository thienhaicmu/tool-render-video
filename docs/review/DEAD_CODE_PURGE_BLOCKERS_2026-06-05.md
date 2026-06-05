# Dead Code Purge Blockers — Sprint 5.3 Audit

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline:** Pytest 2332 passed / 1 skipped / 0 failed @ `ee9ad65` (Sprint 5.2 close, tag `sprint-5-2-done-2026-06-05`)

## Purpose

Record the Sprint 5.3 dead-code audit so future agents do not re-attempt unsafe deletions, and so the precise blocker for each candidate is documented for follow-up sprints.

Sprint 5.3 was scoped per `SPRINT_PLAN_2026-06-04.md:249-251` to delete `LLMSegment`, `groq_*` schema aliases, `_coerce_groq_to_llm`, `motion_crop/legacy.py`, and frontend deprecated fields. On audit, **none of these symbols are genuinely dead.** Each has at least one live consumer or a stored-record replay constraint that requires a precondition migration before deletion is safe.

The only safe touch landed in `abaa8e0` (Sprint 5.3 commit 1): explicit `model_config = ConfigDict(extra="ignore")` on `RenderRequest` — pins the Sacred Contract #2 replay tolerance at the class header. Behavior unchanged (Pydantic v2 already defaulted to `ignore`); the value is now readable in the schema and protected against an implicit upgrade flip.

## Candidate inventory

### 1. `groq_*` field aliases on `RenderRequest`

**Location:** `backend/app/models/schemas.py:364-379` (post Sprint 5.3 commit 1; line numbers shift by +7).

```
groq_analysis_enabled       (bool, default False)
groq_model                  (Optional[str])
groq_content_language       (Optional[str])
groq_min_quality_score      (float, default 0.6)
groq_selection_strategy     (str, default "top_n")
groq_only_mode              (bool, default False)
groq_api_key                (Optional[str])
```

**Verdict:** DEFER — block until DB migration ships.

**Why:**

- Pydantic deserialization is safe because `RenderRequest.model_config = ConfigDict(extra="ignore")` was pinned in Sprint 5.3 commit 1. Stored jobs that carry `groq_*=<value>` keys do not raise ValidationError on replay.
- Behavior is unsafe. The `_coerce_groq_to_llm` validator (`schemas.py:458-475`) translates `groq_analysis_enabled=True && llm_enabled is None` → `llm_enabled=True` (and similar for the other four pairs). Stored jobs from before the global groq→llm rename (commits `2df66ad`, `f6b51d4`, `e350824`) rely on this validator at replay time.
- Deleting the fields and the validator together would silently degrade replayed jobs from "LLM-enhanced" to "heuristic fallback" — no exception, no log signal at replay time. This violates the spirit of Sacred Contract #2 ("Jobs replayed from history activate features they were never configured to use" — same harm class in reverse).

**Precondition for safe delete:** Sprint 5.4 one-shot startup DB migration in `backend/app/db/migration_steps/` that rewrites stored payload_json: `groq_analysis_enabled=true` → `llm_enabled=true`, `groq_model=X` → `llm_provider_model=X` (and similar mappings). After the migration runs once on every existing DB, the validator becomes provably dead and can be removed in a follow-up sprint along with the alias fields.

**Frontend impact:** Only `frontend/src/types/openapi-generated.ts:1768-1789` references these fields (auto-generated from FastAPI schema). Zero hand-written component reads them. When the backend fields are removed and the openapi spec is regenerated, the frontend types auto-clean.

### 2. `_coerce_groq_to_llm` model_validator

**Location:** `backend/app/models/schemas.py:458-475`.

**Verdict:** DEFER — tied 1:1 to the alias fields above.

**Why:** Sole responsibility is the alias coercion at deserialize time. If the alias fields stay, the validator must stay. Once the Sprint 5.4 DB migration ships and the alias fields are removed in a future sprint, the validator is trivially deletable in the same commit.

### 3. `LLMSegment` dataclass

**Location:** `backend/app/ai/llm/parser.py:35` (definition) + alias `GroqSegment = LLMSegment` at `parser.py:55`.

**Live consumers (production):**

- `backend/app/ai/llm/claude_provider.py:22,51,78` — return type of `select_segments`
- `backend/app/ai/llm/gemini_provider.py:15,56,88` — same
- `backend/app/ai/llm/openai_provider.py:16,45,72` — same
- `backend/app/ai/llm/__init__.py:21,43` — dispatcher return type
- `backend/app/ai/llm/parser.py` — `_dict_to_segment` at :213 + `parse_segment_response` at :71
- `backend/app/orchestration/llm_stage.py:263` — consumed by `_to_scored_dict` at line 258 inside the live legacy path

**Pin tests (anti-import sentinels):**

- `backend/tests/test_render_pipeline_llm_emit_flag.py:124`
- `backend/tests/test_render_pipeline_render_plan_wiring.py:139`

Both pin that `render_pipeline.py` does NOT import LLMSegment. They are not consumers — they document an explicit non-coupling.

**Verdict:** DEFER — not dead.

**Why:** The Sprint 4 closure (`docs/review/SPRINT_4_2026-06-04.md:31`) explicitly deferred LLMSegment retirement: "Legacy `select_segments` path còn dùng. Sprint 5 cleanup." That deferral predates Sprint 5.3 and is still load-bearing. The legacy `select_segments` path runs whenever `LLM_EMIT_RENDER_PLAN != "1"` (the default — strict env-var comparison), which means every provider invocation today returns `list[LLMSegment]` to be scored by `llm_stage._to_scored_dict`.

**Precondition for safe delete:** Flip `LLM_EMIT_RENDER_PLAN` default ON (currently OFF), then delete the legacy `select_segments` paths in all three providers + the `_to_scored_dict` consumer + the dispatcher branch. That is its own multi-commit migration. Scope it as Sprint 5.5 or later — explicitly outside Sprint 5.3.

### 4. `backend/app/services/motion_crop/legacy.py`

**Verdict:** DEFER — not dead. The "legacy" name in the SPRINT_PLAN recap was a misclassification.

**Live callers:**

- `backend/app/services/motion_crop/__init__.py:89-93` (re-export tuple)
- `backend/app/services/motion_crop/__init__.py:349` (call inside `build_motion_path` dispatcher when `cfg.reframe_mode != "subject"`)
- `backend/app/services/motion_crop/__init__.py:443` (call inside `render_motion_aware_crop` early-exit fallback)
- `backend/app/services/motion_crop/__init__.py:467` (early-exit fallback at the no-subject branch)
- `backend/app/services/motion_crop/path.py:64,387` (called as `_build_motion_path_legacy` when `build_subject_path` finds no subject)

The module owns three functions: `detect_motion_center`, `_build_motion_path_legacy`, `_detect_scene_ranges_in_clip`. All three are in the hot render path under various fallback conditions. CRITICAL tier per CLAUDE.md (motion_crop package).

**Follow-up recommendation (separate sprint):** Rename `legacy.py` to `motion_pixel_diff.py` so future audits don't reach the same false-conclusion that misnamed it as dead. This is a pure file rename + import update — schedule as a Sprint 5 sub-task or roll into 5.4.

### 5. Frontend deprecated fields (`groq_*` in `openapi-generated.ts`)

**Location:** `frontend/src/types/openapi-generated.ts:1768-1789` (7 fields).

**Verdict:** GO via auto-regen — no standalone hand-edit needed.

**Why:** The file is generated by openapi-typescript from the FastAPI schema. Grep across `frontend/src/**` excluding `openapi-generated.ts` returns zero hits — no production component reads any `groq_*` field. When the backend `groq_*` fields are eventually removed (after Sprint 5.4 migration) and `npm run gen:types` regenerates, these vanish automatically.

## Quoted invariants

`backend/app/models/schemas.py:111-117` after Sprint 5.3 commit 1:

```python
class RenderRequest(BaseModel):
    # Sprint 5.3: pin extra="ignore" explicitly. Stored job records in
    # data/app.db may carry deprecated/renamed keys (e.g. groq_* aliases
    # pending DB migration in Sprint 5.4). Silent-drop is the contract
    # the replay path relies on. Pydantic v2 already defaults to ignore,
    # but pinning makes Sacred Contract #2 readable at the class header.
    model_config = ConfigDict(extra="ignore")
```

`backend/app/models/schemas.py:43` and `:61` (sibling schemas with explicit pin already):

```python
class PrepareSourceRequest(BaseModel):
    ...
    model_config = ConfigDict(extra="ignore")

class QuickProcessRequest(BaseModel):
    ...
    model_config = ConfigDict(extra="ignore")
```

## Follow-up sprint dependencies

| Target deletion | Precondition | Sprint |
|---|---|---|
| `groq_*` alias fields + `_coerce_groq_to_llm` | One-shot DB migration: stored payload_json `groq_*` → `llm_*` rewrite | 5.4 (plan) + later sprint (delete) |
| `LLMSegment` + legacy `select_segments` path + `_to_scored_dict` | Flip `LLM_EMIT_RENDER_PLAN` default ON, ship for at least one release | 5.5 or later |
| `motion_crop/legacy.py` rename → `motion_pixel_diff.py` | None (pure rename) | 5.4 sub-task or 5.5 |
| Frontend `groq_*` types | Backend field deletion → openapi regen | Automatic after the backend sprint |

## What changed in Sprint 5.3

1. `abaa8e0` — `schemas.py` `RenderRequest` pinned to `ConfigDict(extra="ignore")`. 7-line additive change. Pytest 2332/1/0 preserved.
2. This document — `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` — audit findings + per-symbol blockers. Append-only audit ledger per CLAUDE.md.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-04.md:249-251` — original Sprint 5 retire targets
- `docs/review/MIGRATION_COMPLETE_2026-06-04.md:180` — migration outstanding items
- `docs/review/SPRINT_4_2026-06-04.md:31` — original LLMSegment deferral
- `CLAUDE.md` Sacred Contract #2 — RenderRequest additive-only + replay safety
- `CLAUDE.md` Blast Radius Order — `schemas.py` HIGH, `motion_crop/**` CRITICAL, `ai/llm/parser.py` HIGH
