# Audit 2026-06-02 — Track D Audit Pass D5: AI module SC#3 conformance

Twelfth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## Why this audit

Sacred Contract #3 says AI modules must return None on failure rather
than raising. A leak crashes the active render job. This audit
enumerates every public entry point under `backend/app/ai/**` and
classifies its exception-handling shape.

## Audit methodology

For each of the 26 in-scope `.py` files:

1. Enumerate every public (non-underscore) top-level `def` and class method.
2. Classify each as **SAFE** (broad `try/except Exception` at top, returns
   None/default on failure), **LEAKY** (a path can propagate an exception),
   **NARROW** (catches a too-narrow set of exceptions), or
   **N/A** (dataclasses, type stubs, ABC declarations).
3. Inspect all top-level imports of heavy SDKs (`torch`, `groq`, `openai`,
   `anthropic`, `google.genai`, `mediapipe`, `faiss`, etc.) and confirm
   each is guarded by `try/except ImportError` with an availability flag.
4. Flag every leak with a concrete failure mode and pipeline impact.

Read-only — no production code or test code was modified.

## Module inventory

| Module | LOC | Public entry points | SAFE | LEAKY |
|---|---|---|---|---|
| ai/__init__.py | 1 | — | — | — |
| ai/dependencies.py | 57 | 9 (`has_*`, `get_ai_dependency_status`) | 9 | 0 |
| ai/diagnostics.py | 94 | 1 (`get_ai_runtime_diagnostics`) | 1 | 0 |
| ai/tracing.py | 291 | 9 (`AITraceLogger.log_*`) | 9 | 0 |
| ai/analysis/__init__.py | 22 | — re-exports — | — | — |
| ai/analysis/contract.py | 27 | 1 abstract `analyze` | N/A | 0 |
| ai/analysis/hybrid_analyzer.py | 78 | 1 (`HybridAnalyzer.analyze`) | 1 | 0 |
| ai/analysis/local_analyzer.py | 108 | 1 (`LocalAnalyzer.analyze`) | 1 | 0 |
| ai/analysis/merger.py | 106 | 1 (`merge`) | 0 | 1 ⚠ |
| ai/analysis/signals.py | 62 | dataclasses only | N/A | — |
| ai/analysis/cloud/__init__.py | 4 | re-exports | — | — |
| ai/analysis/cloud/base.py | 51 | 1 (`CloudAnalyzerBase.analyze`) + 1 prop | 1 | 0 |
| ai/analysis/cloud/groq_provider.py | 87 | 1 prop (`provider_name`) | N/A | 0 |
| ai/analysis/cloud/openai_provider.py | 54 | 1 prop (`provider_name`) | N/A | 0 |
| ai/analysis/cloud/prompt_builder.py | 83 | 2 (`build_prompt`, `get_system_prompt`) | 0 | 1 ⚠ |
| ai/analysis/cloud/response_parser.py | 139 | 1 (`parse_response`) | 1 | 0 |
| ai/analysis/groq/__init__.py | 14 | re-exports | — | — |
| ai/analysis/groq/client.py | 180 | 1 (`select_segments`) | 1 | 0 |
| ai/analysis/groq/parser.py | 181 | 2 (`sanitize_clip_name`, `parse_segment_response`) | 2 | 0 |
| ai/analysis/groq/prompts.py | 84 | 1 (`build_segment_prompt`) | 0 | 1 ⚠ |
| ai/llm/__init__.py | 67 | 1 (`select_segments` dispatcher) | 0 | 1 ⚠⚠ |
| ai/llm/claude_provider.py | 149 | 1 (`select_segments`) | 1 | 0 |
| ai/llm/gemini_provider.py | 172 | 1 (`select_segments`) | 1 | 0 |
| ai/llm/openai_provider.py | 142 | 1 (`select_segments`) | 1 | 0 |
| ai/visibility/__init__.py | 1 | — | — | — |
| ai/visibility/ai_visibility_summary.py | 196 | 2 (`build_ai_visibility_summary`, `attach_ai_visibility_summaries`) | 0 | 2 ⚠ |

**Totals:** 26 files in scope, ~38 inspected public entry points,
**6 LEAKY entry points** (1 HIGH, 5 MEDIUM).

## HIGH risk findings — LEAKY entry points

### H1 — `ai/llm/__init__.py:select_segments` dispatcher is not wrapped

**Location:** `backend/app/ai/llm/__init__.py:27-67`

**Shape:** The dispatcher branches on `provider`, then does a lazy
`from app.ai.llm.<x>_provider import select_segments as _impl`, then
calls `_impl(...)` — **no top-level `try/except`**.

**Leak paths:**

1. The lazy `from app.ai.llm.gemini_provider import ...` line itself
   can raise `ImportError` if the provider module fails to import
   (e.g., a typo introduced in `gemini_provider.py`, a missing module
   path, a circular import). This propagates to the caller —
   `orchestration/groq_stage.run_groq_segment_selection` — which then
   crashes the render job.
2. While each provider's own `select_segments` is wrapped, the
   keyword-only call expansion at lines 58-67 happens **outside**
   the provider's try block. A TypeError on a missing keyword would
   propagate.

**Impact:** Active render job aborts mid-flight with no fallback.
Caller (`groq_stage.py`) expects `None` to mean "Groq selection
failed, hard-fail in groq_only_mode" — an uncaught exception
bypasses this code path.

**Fix:** Wrap the entire dispatcher body in
`try: ... except Exception as exc: logger.warning(...); return None`.

## MEDIUM risk findings — partial coverage

### M1 — `ai/visibility/ai_visibility_summary.build_ai_visibility_summary` is not wrapped

**Location:** `ai_visibility_summary.py:78-179`

**Shape:** No outer `try/except`. Defensive `isinstance` checks and
`_as_float` helpers cover most type errors, but residual leaks exist:

- `int(quality_penalty)` at line 158 can raise `OverflowError` on
  `float('inf')` or `ValueError` on `float('nan')` — these slip past
  `_as_float` (which only catches `TypeError, ValueError`, not
  overflow).
- `round(value, 3)` at line 104 is safe for finite floats but raises
  on `Decimal('NaN')` (unlikely but possible if upstream stores
  Decimal scores).
- `str(part.get("dominant_signal") or "")` etc. is safe.

**Caller:** `render_pipeline.py:907` — `attach_ai_visibility_summaries`
is called immediately before the best-clip selection. A leak here
would abort the entire render job after all parts have finished
rendering — maximum damage, maximum confusion.

**Impact:** Edge-case crash after successful render. Most likely
trigger: an upstream scoring bug stores `inf`/`nan` into
`quality_penalty` and the visibility-summary call propagates it
upward into the orchestrator.

**Fix:** Wrap function body in `try: ...; except Exception: return {}`.

### M2 — `ai/visibility/ai_visibility_summary.attach_ai_visibility_summaries` is not wrapped

**Location:** `ai_visibility_summary.py:182-196`

**Shape:** Iterates `entries`, `deepcopy`s each, calls
`build_ai_visibility_summary`. If `entries` is `None`, the
`entries or []` guard handles it. But `deepcopy(item)` could raise
on non-copyable contents (e.g., open file handles, generator
references — extremely unlikely for ranking entries which are pure
dicts of primitives, but not impossible).

The bigger risk is the inner call to M1 above — same leak.

**Impact:** Same as M1 — orchestrator crash after parts complete.

**Fix:** Wrap iteration body in `try/except`, skip the offending
entry and continue.

### M3 — `ai/analysis/merger.merge` is not wrapped

**Location:** `merger.py:26-43`

**Shape:** No outer `try/except`. Most operations are dataclass
construction with known-typed fields. But `cloud.warnings` is iterated
in `[f"cloud:{w}" for w in cloud.warnings]` — if a cloud parser stuffs
a non-iterable into `warnings` (defensive against future bugs in
`response_parser.py`), this raises `TypeError`.

`_merge_clips`, `_merge_emotion`, `_closest_cloud` are private helpers
called from inside merge — exceptions there propagate.

**Caller:** `hybrid_analyzer.HybridAnalyzer.analyze` line 60 — but
that caller does **not** wrap the `merge()` call in a try/except.
HybridAnalyzer's `_run_safe` only wraps the `analyzer.analyze()` call,
not the post-merge step. A merge exception escapes HybridAnalyzer.

**Impact:** Render job aborts when Hybrid analysis is in use (i.e.
when both Local + Cloud analyzers are enabled).

**Fix:** Either wrap `merge()` body in try/except returning the
`local` arg as fallback, or wrap the call inside
`HybridAnalyzer.analyze`.

### M4 — `ai/analysis/cloud/prompt_builder.build_prompt` is not wrapped

**Location:** `prompt_builder.py:55-59`

**Shape:** `float(context.get("duration") or 0.0)` raises `ValueError`
if `duration` is a non-numeric string. `_format_chunks` raises if a
chunk is not a dict (`chunk.get` attribute access).

**Caller:** `cloud/base.CloudAnalyzerBase.analyze` — which IS wrapped
in try/except (line 30-44), so a leak here is currently absorbed.
**However**, the function is also re-exported and may be reused
elsewhere; today's safety relies on a single safe caller. Document
it as "must be called from a guarded context".

**Impact:** Limited today — base.py absorbs it. Becomes a leak if any
future caller invokes `build_prompt` directly.

**Fix:** Either wrap internally returning a degenerate prompt string,
or add a comment that this function assumes a guarded caller.

### M5 — `ai/analysis/groq/prompts.build_segment_prompt` is not wrapped

**Location:** `prompts.py:58-84`

**Shape:** `int(min_sec)` and `int(max_sec)` raise on non-numeric
inputs. `srt_content[:cap]` raises `TypeError` if `srt_content` is
None (the caller's `_run` checks `not srt_content` first, so today
this is safe).

**Caller:** All four `*_provider.py:_run` functions check non-None
srt_content first and pass numeric `min_sec`/`max_sec` from upstream
payload schema. Each `select_segments` is itself wrapped — so leaks
here are absorbed today.

**Impact:** Same as M4 — relies on caller-side guards. If reused
elsewhere, becomes a real leak.

**Fix:** Add a `try/except` returning a tuple of empty strings, OR
keep the doc that this is "wrapped-caller-only".

## LOW risk / informational

- **`AITraceLogger` (tracing.py)** — Excellent compliance. Every
  `log_*` method has nested defensive try/except blocks; the core
  `_write` swallows all I/O errors. Pattern to emulate.
- **`LocalAnalyzer.analyze` (local_analyzer.py:49)** — Wrapped at
  top level and again per-clip inside `_score_clips`. Safe.
- **`HybridAnalyzer._run_safe`** — Correctly catches `Exception`,
  but only around the `analyzer.analyze()` call. Sibling `merge()`
  call is not guarded (see M3).
- **`CloudAnalyzerBase.analyze`** — Single broad try/except, returns
  None on any failure. Safe.
- **All four `select_segments` provider entry points
  (groq/client.py, llm/claude_provider.py, llm/gemini_provider.py,
  llm/openai_provider.py)** — Identical pattern: top-level wrapper
  delegates to `_run`, catches all exceptions, returns None. Safe.
- **`parse_response` (cloud/response_parser.py:34)** and
  **`parse_segment_response` (groq/parser.py:39)** — Both wrap the
  full body in try/except returning None. Per-item parse errors
  caught locally. Safe.
- **`get_ai_runtime_diagnostics` (diagnostics.py:18)** — Wraps
  `_collect()` and returns a degenerate-but-valid dict on failure.
  Memory probe also wrapped separately. Excellent compliance.
- **All `has_*` detectors (dependencies.py)** — `importlib.util.find_spec`
  is documented as non-raising; functions are pure boolean returns.
  Safe.

## Optional-dependency import safety

All heavy / optional SDK imports under `backend/app/ai/**` are
guarded by `try/except ImportError`:

| Module | Lazy-imported deps | Pattern |
|---|---|---|
| `analysis/__init__.py` | groq sub-package | try/except ImportError → `_GROQ_AVAILABLE` flag |
| `analysis/local_analyzer.py` | `app.ai.analyzers.*` | try/except + stub functions on miss |
| `analysis/cloud/groq_provider.py` | `groq`, `openai` | both guarded with `_GROQ_SDK_AVAILABLE` / `_OPENAI_COMPAT_AVAILABLE` |
| `analysis/cloud/openai_provider.py` | `openai` | guarded with `_OPENAI_AVAILABLE` |
| `analysis/groq/client.py` | `groq`, `openai` | guarded |
| `llm/claude_provider.py` | `anthropic` | guarded with `_ANTHROPIC_SDK` |
| `llm/gemini_provider.py` | `google.genai` | guarded with `_GENAI_SDK` |
| `llm/openai_provider.py` | `openai` | guarded with `_OPENAI_SDK` |
| `diagnostics.py` | `app.ai.rag.sqlite_store` | imported lazily inside `_memory_diagnostics` try/except |

**No unconditional `import torch / groq / openai / anthropic / google.genai`
found anywhere under `backend/app/ai/**`.** All checks pass —
FastAPI startup is safe even when zero AI extras are installed.

The only `raise` statement under the entire tree is
`NotImplementedError` in `CloudAnalyzerBase._call_api` (private default,
overridden by every concrete subclass — never reachable at runtime).

## Priority-ranked action items

| Priority | Action | Effort | Why |
|---|---|---|---|
| **HIGH** | Wrap `ai/llm/__init__.select_segments` body in try/except → None | 5 lines | H1 — sole un-guarded multi-provider entry; any provider import bug crashes a live render |
| **MEDIUM** | Wrap `ai/visibility/ai_visibility_summary.build_ai_visibility_summary` in try/except → `{}` | 5 lines | M1 — called at end of render pipeline; leak aborts an otherwise-successful job |
| **MEDIUM** | Wrap `attach_ai_visibility_summaries` per-entry in try/except, skip-on-fail | 8 lines | M2 — same call path as M1 |
| **MEDIUM** | Wrap `ai/analysis/merger.merge` body in try/except → local arg | 5 lines | M3 — hybrid analyzer doesn't guard this sibling call |
| **LOW** | Add comment on `build_prompt` / `build_segment_prompt` documenting "wrapped-caller required" | comment-only | M4, M5 — guard discipline currently holds but is fragile to future call sites |

All five actions are surgical, additive, and behavior-preserving on
the happy path. Each can land independently.

## Pytest

Audit is read-only. Baseline unchanged: 2149 passed, 1 skipped, 0 failed.

## References

- Sacred Contract #3 — CLAUDE.md, "AI Modules Return None on Failure"
- Audit ledger root — `docs/review/AUDIT_2026-06-02.md`
- Prior follow-up (closest topical) — `docs/review/AUDIT_2026-06-02_followup_4.md` (Sprint 6.D closure)
- Caller of leak H1 — `backend/app/orchestration/groq_stage.py:24`
- Caller of leak M1/M2 — `backend/app/orchestration/render_pipeline.py:907`
- Caller of leak M3 — `backend/app/ai/analysis/hybrid_analyzer.py:60`

## Status

**D5 audit: COMPLETE.** No code changes — pure findings document.
One HIGH-risk and four MEDIUM-risk leaks identified. All recommended
fixes are surgical (≤8 lines each) and can be scheduled as a single
follow-up sprint (suggested label: "Track D Audit Pass D5 remediation").
