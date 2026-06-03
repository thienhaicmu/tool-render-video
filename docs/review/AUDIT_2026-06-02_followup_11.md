# Audit 2026-06-02 — Track D P3 Action Items: Contracts #2 + #7 conformance

Eleventh append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

Two of three P3 items from the audit ledger
(`docs/review/AUDIT_2026-06-02_followup_7.md`):

- **Contract #2** — `RenderRequest` new-field default audit.
- **Contract #7** — `app.db` sole job-state authority (import-graph test).

The third P3 item (Sacred Contract #3 audit of `backend/app/ai/**`,
flagged as a D5 candidate) is deferred — it requires a discovery
pass like followup_7 was, not a test addition.

## What was added

Two test files, one bundled commit:

| File | Tests | Contract |
|---|---|---|
| `backend/tests/test_contract_render_request_defaults.py` | 4 | #2 |
| `backend/tests/test_contract_db_sole_authority.py` | 3 | #7 |

Total: 7 new tests, 0 production code changes.

## Test breakdown

### Contract #2 — `test_contract_render_request_defaults.py`

Per CLAUDE.md Sacred Contract #2: every new bool field on
`RenderRequest` must default to `False` (or the most conservative
disabled state). New fields defaulting to `True` would silently
activate features on stored job replay.

Approach: introspect `RenderRequest.model_fields` (Pydantic v2) for
every `bool`-annotated field. Assert default is `False` unless the
field name appears in `GRANDFATHERED_TRUE_DEFAULTS` — a 6-entry
allowlist of long-standing baseline-behavior flags (subtitles on,
motion crop on, loudnorm on, etc.). Adding a new bool that defaults
to `True` requires a conscious decision to extend the allowlist with
a justification comment.

The 6 grandfathered entries:
- `cleanup_temp_files`
- `auto_detect_scene`
- `add_subtitle`
- `motion_aware_crop`
- `loudnorm_enabled`
- `reup_overlay_enable`

Four tests:

1. `test_all_bool_fields_default_to_false_or_grandfathered` — the
   primary guard. Iterates every bool field; collects violations;
   fails with field names + remediation guidance.
2. `test_grandfathered_list_only_contains_actual_fields` — sanity:
   allowlist entries reference real RenderRequest fields. Catches
   stale entries after refactors.
3. `test_grandfathered_fields_actually_default_to_true` — sanity:
   every grandfathered field IS still bool=True. Catches dead
   allowlist entries.
4. `test_known_safe_features_default_to_false` — spot-check the 11
   sensitive feature flags explicitly cited in CLAUDE.md / Sprint 3
   3E commentary (ai_director_enabled, ai_auto_cut, voice_enabled,
   etc.) as fields that MUST stay False.

### Contract #7 — `test_contract_db_sole_authority.py`

Per CLAUDE.md Sacred Contract #7: only `app/db/**` modules may call
`sqlite3.connect()` directly. Direct connections elsewhere bypass
WAL mode, row factories, and thread-local connection state — corrupting
the render pipeline's consistency guarantees.

Approach: walk `backend/app/**/*.py` with the Python AST, find every
`sqlite3.connect(...)` call site (matched as `Attribute(value=Name('sqlite3'),
attr='connect')`). Assert every hit's relative path is in
`SANCTIONED_RELATIVE_PATHS`.

Sanctioned paths (4 entries):

- `db/connection.py` — the sole-authority connection module.
- `db/__init__.py` — re-export shim (currently has no call sites
  but listed for forward-compat).
- `services/db_backup.py` — Sprint 6.A online-backup module
  (`sqlite3.Connection.backup(target)` API on app.db; documented
  exception per its module docstring).
- `services/cookie_extractor.py` — reads BROWSER cookie databases
  (Chrome/Firefox), NOT app.db. Legitimate cross-purpose sqlite3
  use.

Three tests:

1. `test_no_unsanctioned_sqlite3_connect_calls` — the primary guard.
   AST-walks the tree, lists violations with file paths + line
   numbers + remediation guidance.
2. `test_sanctioned_paths_all_exist` — sanity: every allowlist
   entry is a real file. Catches typos and stale entries.
3. `test_db_connection_module_actually_uses_sqlite3_connect` —
   positive control: `db/connection.py` SHOULD have at least one
   `sqlite3.connect()` call. If it doesn't, the connection model
   changed and the test needs to be re-audited.

## Why static analysis works here

Both Contracts are amenable to introspection-only tests because the
underlying invariants are declarative:

- Contract #2: "every bool field defaults to False" is a Pydantic
  schema property visible via `model_fields`.
- Contract #7: "no module outside `app/db/` calls `sqlite3.connect()`"
  is an AST property visible via tree walk.

Neither test needs to invoke any production code path. Both fail
loudly with actionable diagnostics if a future change violates the
invariant.

## Sacred Contracts honored

Both tests **assert** Sacred Contracts — they don't modify them. The
tests are pure introspection / static analysis. No production code
modified.

## Pytest

Before this batch: 2142 passed, 1 skipped (after followup_10).
After this batch: **2149 passed, 1 skipped**, 0 failed.

Net +7 tests, 0 regressions. Fastest section of the suite (~0.8 sec
combined).

## Risk

**LOW.** Test-only additions, static analysis only.

## Remaining work from followup_7

### Contract #3 audit (D5 candidate) — DEFERRED

Sacred Contract #3 says: "All modules under `backend/app/ai/**` MUST
catch all exceptions internally and return `None` on failure. Never
allow an exception to propagate upward."

A static-analysis test analogous to Contract #7 is feasible:
walk `backend/app/ai/**`, identify public entry points (top-level
def / class methods), check whether each is wrapped in a top-level
try/except that returns None.

However, the analysis is more involved than #7 because:
- "public entry point" is not statically obvious (some helpers are
  internal; some classes export inner methods).
- "returns None on error" is not the only safe pattern — returning
  a default value (e.g., empty list) is also safe.
- Async functions and generators behave differently.

A proper D5 audit pass — like followup_7's D2 — should enumerate
the public entry points first, document each one's failure mode,
then add targeted tests where coverage is missing. That is a
half-day discovery effort, not a single test addition.

### Code-shape recommendations — DEFERRED (HIGH risk)

- Refactor `except: pass` blocks to `except: log + emit_warning`
  pattern.
- Add `_run_or_warn(block_name, fn)` helper in `render_events.py`.

These touch CRITICAL-tier files (`stages/part_*.py`,
`orchestration/pipeline_*.py`) and require Planner analysis + explicit
user approval per CLAUDE.md §"Render Edit Protocol".

## References

- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- D2 audit findings: `docs/review/AUDIT_2026-06-02_followup_7.md`.
- P0 closure: `docs/review/AUDIT_2026-06-02_followup_8.md`.
- P1 closure: `docs/review/AUDIT_2026-06-02_followup_9.md`.
- P2 closure: `docs/review/AUDIT_2026-06-02_followup_10.md`.

## Status

**Track D P3 (Contracts #2 + #7): CLOSED.** Both Sacred Contracts
now have direct static-analysis conformance tests. The audit's
P3 backlog is reduced to one open item (D5 / Contract #3 audit)
and the gated code-shape recommendations.

Track D summary across the 5 closures (followup_8 through _11):

| Closure | Tests added | Net coverage gain |
|---|---|---|
| P0 — T1 + T2 | 6 | Cover frame + combined score call-site guards |
| P1 — T3 + #1/#6/#8 | 22 | Market line-break + 3 Sacred Contract conformance |
| P2 — 9 module smoke tests | 34 | 9 of 20 uncovered Sprint 6.D modules direct-imported |
| P3 — #2 + #7 conformance | 7 | RenderRequest defaults + sqlite3 import graph |
| **Total** | **69** | Pytest 2080+1 → 2149+1 |

Zero regressions across all 5 closures.
