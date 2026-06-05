# Sprint 7.5 — Delete `groq_*` alias fields + `_coerce_groq_to_llm` validator

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-5-groq-deletion`
**Baseline:** Pytest 2414 passed / 1 skipped / 0 failed @ `f15ef4b` (main, post Sprint 7.2)
**Final pytest:** 2415 passed (+1 net) / 1 skipped / 0 failed
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.5 row + `docs/review/MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` §"What this migration does NOT do"

## Pre-flight verification (live DB)

User's `data/app.db` queried at the start of Sprint 7.5:

```
groq_analysis_enabled    = 0 rows  [OK]
groq_model               = 0 rows  [OK]
groq_content_language    = 0 rows  [OK]
groq_min_quality_score   = 0 rows  [OK]
groq_selection_strategy  = 0 rows  [OK]

Preserved keys (Migration 0002 design):
groq_only_mode           = 7 rows
groq_api_key             = 1 row
```

Migration 0002 ran on the production DB at first startup post Sprint 5.4 ship (verified via `schema_versions` query during PR #6 smoke test). All 5 mapped `groq_*` keys are gone from stored `payload_json`. Sprint 7.5's pre-condition is fully met for this operator.

## Purpose

Migration 0002 (Sprint 5.4) translated the 5 legacy `groq_*` keys to canonical `llm_*` keys in every stored job's `payload_json`. The `_coerce_groq_to_llm` validator existed as a runtime safety net during the rollout window — it duplicated the migration's translation rule so jobs still carrying legacy keys deserialised correctly on read.

Sprint 7.5 ships when:
- The migration has run on every production DB (verified above for this operator)
- Sprint 5.3's `model_config = ConfigDict(extra="ignore")` is in place to silently drop any legacy keys that somehow slip through

Both conditions are met. The 5 alias fields + the validator become provably dead code.

## What was deleted

### 1. 5 field declarations in `backend/app/models/schemas.py:371-376`

```diff
- groq_analysis_enabled: bool = False
- groq_model: Optional[str] = None
- groq_content_language: Optional[str] = None
- groq_min_quality_score: float = 0.6
- groq_selection_strategy: str = "top_n"
  groq_only_mode: bool = False                   # PRESERVED — no llm_ equivalent
```

`groq_only_mode` stays — it was never part of the 5-pair mapping (no llm_only_mode equivalent exists). Sprint 7.5 audit doc + Migration 0002 design both committed to preserving it.

`groq_api_key` at `schemas.py:386` ALSO stays — it remains valid per-provider API key input alongside `gemini_api_key`, `openai_api_key`, `claude_api_key`. The `ai_provider="groq"` selection is still a live code path.

### 2. `_coerce_groq_to_llm` validator at `schemas.py:465-482`

Entire `@model_validator(mode="after")` decorated function deleted. Replaced with a single breadcrumb comment citing this audit doc + Sprint 5.3's `extra="ignore"` pin as the silent-drop safety net for any payload that still carries legacy keys.

### 3. Updated inline comments referencing the deleted fields

`schemas.py:361-365` (the `llm_*` field declarations) — the "None = inherit from groq_*" comments updated to "None = use server default" (which is what the pipeline does when the canonical fields are None).

## What was preserved

- `groq_only_mode` field at `schemas.py:376`
- `groq_api_key` field at `schemas.py:386`
- `ai_provider="groq"` code paths in `ai/llm/__init__.py` + provider modules
- Migration 0002 (`db/migration_steps/0002_jobs_rewrite_groq_to_llm.py`) — historical; never edited
- 14 of the 15 migration tests in `test_migration_0002_groq_to_llm.py`

## What was modified

### `test_migration_0002_groq_to_llm.py` Section 7

`test_replay_parity_with_validator` (which compared validator-derived `llm_*` values against migration-derived `llm_*` values) was deleted — the validator no longer exists, so there's nothing to parity-check against.

Replaced with two new tests:

1. **`test_post_migration_payloads_deserialize_to_llm_fields`** — pin the post-Sprint-7.5 contract: after Migration 0002 ran, every payload carries `llm_*` keys; `RenderRequest(**post_migration_payload)` succeeds without raising and produces the canonical `llm_*` fields.

2. **`test_legacy_groq_payload_drops_silently_post_sprint_7_5`** — the explicit safety pin: a payload that still carries legacy `groq_*` keys (somehow not migrated) must deserialise without raising thanks to `extra="ignore"`. The `llm_*` fields default to None (pipeline reads as "use server default"). The preserved `groq_only_mode` + `groq_api_key` still work as input.

Net pytest delta: -1 deleted + 2 added = +1 (2414 → 2415).

## Behaviour walk

| Stored payload shape | Pre-Sprint-7.5 result | Post-Sprint-7.5 result |
|---|---|---|
| Has `llm_*` keys only (post Migration 0002) | RenderRequest loads, llm_* fields set | RenderRequest loads, llm_* fields set (unchanged) |
| Has `groq_*` keys only (somehow not migrated) | Validator copies groq → llm; llm fields set | extra="ignore" drops groq keys silently; llm fields default to None (pipeline uses server defaults) |
| Has both groq_* and llm_* (llm wins) | Validator: llm wins (None-guarded copy) | extra="ignore" drops groq; llm values from payload preserved |
| Has groq_only_mode | Field set, available to pipeline | Field set, available to pipeline (unchanged) |
| Has groq_api_key (provider="groq") | Field set, available to provider dispatch | Field set, available to provider dispatch (unchanged) |

The legacy-payload row is the only behaviour change. The new behaviour (silent drop → server defaults) is identical to a fresh job with no LLM config. For production this is invisible — Migration 0002 already eliminated the row population.

## Sacred Contracts walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases | No | unchanged |
| #2 RenderRequest additive (spirit) | **Engaged but provably safe** | Field deletion is non-additive. Mitigations: (a) Migration 0002 rewrote every stored payload before this commit; (b) `extra="ignore"` silently drops any legacy keys that surface; (c) the new behaviour (None defaults) is identical to a fresh job — render still completes via existing legacy fallback. Live DB verified zero `groq_*` keys for the 5 mapped fields. |
| #3 AI returns None | No | unchanged |
| #4 / #5 stage names | No | unchanged |
| #6 `_emit_render_event` shape | No | unchanged |
| #7 `data/app.db` sole authority | No | not touched (Migration 0002 ran in a prior sprint; this commit is read-only against the DB) |
| #8 `qa_pipeline` never bypassed | No | unchanged |

## What this sprint does NOT do

- Does NOT touch Migration 0002 (`db/migration_steps/0002_jobs_rewrite_groq_to_llm.py`). Append-only historical migration code.
- Does NOT delete `groq_only_mode` or `groq_api_key` schema fields.
- Does NOT delete the `"groq"` provider option from `ai_provider`.
- Does NOT touch `ai/llm/*` provider modules.
- Does NOT regenerate the frontend openapi types (operator runs `npm run gen:types` separately).

## Frontend follow-up (operator runs separately)

`frontend/src/types/openapi-generated.ts` lines 1768-1789 reference the 5 deleted fields. Auto-cleans on next `npm run gen:types`. No hand-written component references the 5 fields (grep confirmed during Sprint 5.3 dead-code audit).

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.5 row — scoped this work
- `docs/review/MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` — migration that made this safe
- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §1 — the audit that identified this as the future-target
- `docs/review/SPRINT_7_EXECUTION_PLAN_2026-06-05.md` Phase 2 — execution runbook entry
- `backend/app/models/schemas.py:357-373` (post-deletion) — the canonical `llm_*` fields + preserved `groq_only_mode`
- `backend/tests/test_migration_0002_groq_to_llm.py` Section 7 — the two new post-Sprint-7.5 pins
