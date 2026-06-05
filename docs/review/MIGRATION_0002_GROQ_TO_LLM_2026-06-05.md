# Migration 0002 — `jobs.payload_json` `groq_*` → `llm_*` Rewrite

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Commit:** `4f5dd80`
**Migration file:** `backend/app/db/migration_steps/0002_jobs_rewrite_groq_to_llm.py`
**Test file:** `backend/tests/test_migration_0002_groq_to_llm.py`

## Why this migration ships

The Pydantic validator `_coerce_groq_to_llm` at `backend/app/models/schemas.py:466-482` runs on every `RenderRequest` deserialization to translate legacy `groq_*` field aliases into the canonical `llm_*` shape. Stored job records in `data/app.db` that predate the global groq→llm rename (commits `2df66ad`, `f6b51d4`, `e350824`) rely on this validator at replay/retry time.

Sprint 5.3 audit (`docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md`) found that deleting the validator + alias fields without first migrating stored payloads would silently downgrade replayed jobs from "LLM-enhanced" to "heuristic fallback" — a Sacred Contract #2 violation. The audit explicitly listed a one-shot DB migration as the precondition for any future deletion.

This migration ships that precondition. Once it has run on every user's DB, the validator is provably dead and can be retired in a follow-up sprint.

## Mapping

Five `(groq_*, llm_*)` pairs — bit-identical to `_coerce_groq_to_llm`:

| groq_* key | llm_* key | Coercion rule |
|---|---|---|
| `groq_analysis_enabled`   | `llm_enabled`     | Copy when `llm_*` is missing or None |
| `groq_model`              | `llm_model`       | same |
| `groq_content_language`   | `llm_language`    | same |
| `groq_min_quality_score`  | `llm_min_quality` | same |
| `groq_selection_strategy` | `llm_mode`        | same |

Two `groq_*` keys deliberately preserved:

| Key | Why preserved |
|---|---|
| `groq_only_mode`  | No canonical `llm_*` equivalent. Validator never touched it. |
| `groq_api_key`    | `groq` is still a valid LLM provider (`schemas.py:386`) — the per-provider key is live input, not a legacy alias. |

After the coercion, the five mapped `groq_*` keys are removed from `payload_json`. The two preserved keys stay.

## Idempotency + safety

| Concern | Mechanism |
|---|---|
| Never re-run | `schema_versions` runner sentinel — `migrations.py:158-160` skips already-applied versions. |
| Within-row re-run safety | The body only writes when a `groq_*` key is present. After the first pass deletes those keys, a second pass on the same row is a no-op. |
| NULL `payload_json` | Skip at DEBUG level. |
| Empty string `payload_json` | Skip. |
| Malformed JSON | Skip at DEBUG level. The next `RenderRequest(**payload)` deserialize handles it via `extra="ignore"` or raises a domain ValidationError — neither path runs through this migration. |
| Non-dict payload (e.g. list) | Skip. |
| In-flight jobs | Migration runs in `init_db()` at `main.py:223`, before `recover_pending_render_jobs()` at `main.py:242` and before any worker thread is spawned. The migration window is guaranteed pre-worker. |
| Half-migrated state | Runner wraps the whole pass in `BEGIN`/`commit()`/`rollback()` (`migrations.py:162-176`). Crash mid-loop → atomic rollback. Next startup retries from scratch. |
| Recovery on failure | `init_db()` catches `MigrationError` at `connection.py:368-369`, logs WARNING, app still starts. DB left in pre-migration state. User can downgrade and retry. |

Sacred Contract #7 honoured: this is additive in column terms (no DROP / RENAME / ALTER). Only mutates `payload_json` content.

## Test coverage (`backend/tests/test_migration_0002_groq_to_llm.py`)

14 cases:

1. `test_migration_version_and_name` — VERSION=2, NAME="jobs_rewrite_groq_to_llm"
2. `test_each_groq_pair_is_translated` — 5 fixtures, one per mapping pair
3. `test_existing_llm_value_wins_over_groq` — llm_enabled=False vs groq_analysis_enabled=True
4. `test_explicit_none_llm_value_is_overwritten` — llm_enabled=None is treated as absent
5. `test_null_payload_is_skipped`
6. `test_empty_string_payload_is_skipped`
7. `test_malformed_json_payload_is_skipped`
8. `test_non_dict_payload_is_skipped` — list payload
9. `test_payload_with_no_groq_keys_is_untouched` — payload bypass
10. `test_groq_only_mode_and_api_key_preserved`
11. `test_second_pass_is_noop` — within-row idempotency
12. `test_runner_discovers_and_records_version` — `run_pending_migrations` integration
13. `test_migration_skipped_when_no_jobs_table` — defensive
14. `test_replay_parity_with_validator` — load-bearing behavioural pin: `RenderRequest.model_dump()` `llm_*` fields are identical pre vs post-migration across 8 fixture variants

## Replay-parity test note

The full `model_dump()` of a `RenderRequest` deserialized pre- vs post-migration differs on the `groq_*` fields themselves: pre-migration carries the user's stored `groq_analysis_enabled=True`; post-migration sees them at their default values (because the keys are gone from payload_json). The render pipeline reads `llm_*` fields exclusively — no production code reads `groq_*` outside the validator — so the post-migration render is bit-identical at the pipeline level.

The replay-parity test asserts that the `llm_*` field subset matches exactly across all 8 fixture variants. Any future addition to `_coerce_groq_to_llm` MUST extend both the mapping table in the migration body and this test's fixture set.

## What this migration does NOT do

- It does NOT delete the `groq_*` schema fields (they stay in `RenderRequest` for now).
- It does NOT delete the `_coerce_groq_to_llm` validator (still runs harmlessly — every row it touches has already had `groq_*` keys removed).
- It does NOT alter the FE `openapi-generated.ts` types (those auto-clean on next regen after the backend field deletion in a future sprint).

Per the Sprint 5.3 audit, the field + validator deletion is gated on:
- Migration 0002 has been live for at least one release cycle (so all user DBs have had a chance to apply it).
- The frontend openapi-generated.ts is regenerated post-deletion.

That cleanup sprint is OUT of scope for Sprint 5.4.

## Cross-references

- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` — Sprint 5.3 audit that scoped this migration
- `docs/review/DB_CONNECTION_AUDIT_2026-06-05.md` — Sprint 5.4 sibling audit (Sub-A)
- `backend/app/models/schemas.py:466-482` — validator the migration replicates bit-identical
- `backend/app/db/migrations.py` — runner + idempotency guarantee
- `backend/app/db/migration_steps/0001_jobs_add_render_plan_json.py` — sibling migration (Sprint 2.1)
- `CLAUDE.md` Sacred Contract #2 + #7 — DB additive-only rule
