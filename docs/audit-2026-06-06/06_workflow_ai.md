# 06 — AI Workflow

Deep trace of every AI-touching path on branch `feature/ai-workflow-upgrade`. Source code only.

> Phase 1 located the AI code at [backend/app/features/render/ai/](../../backend/app/features/render/ai/) (not `backend/app/ai/`, which is a ghost dir).

---

## 1. Provider selection & dispatch

[backend/app/features/render/ai/llm/__init__.py](../../backend/app/features/render/ai/llm/__init__.py) is the dispatcher. Two entry points:

| Entry | Purpose | Sprint |
|---|---|---|
| `select_segments(provider, srt, …)` | LLM Call 1 — returns segment list (`LLMSegment` dataclass) | legacy / being retired |
| `select_render_plan(provider, srt, …)` | LLM Call 2 — returns full `RenderPlan` | Sprint 4.C / default since 7.6a |

Provider order ([llm/__init__.py:49-61](../../backend/app/features/render/ai/llm/__init__.py)):
1. Explicit `provider` argument (from `RenderRequest.ai_provider` / payload.ai_provider).
2. Fallback `DEFAULT_PROVIDER = "gemini"` ([line 28](../../backend/app/features/render/ai/llm/__init__.py)).
3. Invalid name → warning + fallback to gemini.

Defaults baked into providers (verified by reading the code, **not docs**):

| Provider | Default model | File |
|---|---|---|
| Claude | `claude-haiku-4-5-20251001` | `llm/providers/claude.py:29` |
| OpenAI | `gpt-4o-mini` | `llm/providers/openai.py:23` |
| Gemini | `gemini-2.5-pro` | `llm/providers/gemini.py:26` |

API-key resolution per provider ([llm_stage.py:107-142](../../backend/app/features/render/engine/pipeline/llm_stage.py)):
1. payload-specific field (e.g., `payload.gemini_api_key`)
2. generic `payload.ai_cloud_api_key`
3. env var (`GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY`)
4. Hard-fail if none.

**FINDING-AI01 (MED):** There is **no sequential provider fallback**. If the user picks Claude and the key is missing, the call fails — system does not silently try Gemini. This is the right default (respect user choice) but the error surfaced to the FE is just a generic failure. Phase 7 should propose explicit error code `AI_KEY_MISSING_PROVIDER=claude` for the UI.

**FINDING-AI02 (LOW):** Model string mismatch between FE and BE:
- FE `AiSummaryCard.tsx` displays `gemini-2.0-flash`, `gpt-4o`, `claude-sonnet-4-6`.
- BE defaults to `gemini-2.5-pro`, `gpt-4o-mini`, `claude-haiku-4-5-20251001`.
The FE strings appear to be labels for the *user's selection in the UI*, not what the backend actually used. Cosmetic, but auditable. Recommend backend echo back `actual_model` in `result_json` and FE display that.

---

## 2. Prompts

Two prompt families in [backend/app/features/render/ai/llm/prompts.py](../../backend/app/features/render/ai/llm/prompts.py):

| Template | Purpose | File:line | Output schema |
|---|---|---|---|
| `_SYSTEM` + `_USER_TEMPLATE` (`build_segment_prompt`) | Segment selection | 46-207 | `{ "segments": [{ start, end, score, clip_name, title, reason, … }] }` |
| `_SYSTEM_RP` + `_USER_TEMPLATE_RP` (`build_render_plan_prompt`) | RenderPlan emission | 214-422 | Native `RenderPlan` JSON (`clips[]`, `subtitle_policy`, `camera_strategy`, `audio_plan`, `overlays`) |

Inputs both templates interpolate: `{language}`, `{srt_content}`, `{output_count}`, `{min_sec}`, `{max_sec}`, `{example_end}`, `{editorial_section}`.

**Format-safety (FINDING-AI03, LOW):** Every literal `{` in JSON examples is doubled to `{{` and `}}` ([prompts.py:221-225, 390-396](../../backend/app/features/render/ai/llm/prompts.py)). This is the documented mitigation for an earlier `str.format` bug. Regression-guarded by `tests/test_creator_context_dataclass.py`. Healthy.

`editorial_section` is built by `_build_editorial_hint` in [llm_stage.py:62-104](../../backend/app/features/render/engine/pipeline/llm_stage.py) — combines `hook_strength` (aggressive|balanced|soft), `video_type` (auto|viral|storytelling|educational|emotional|high_retention), and the optional `CreatorContext` from `creator_prefs`.

---

## 3. Structured output / parsing

[backend/app/features/render/ai/llm/parser.py](../../backend/app/features/render/ai/llm/parser.py) has two parsers — both built for *resilience*, not strictness.

### `parse_segment_response` (lines 66-138)

- Extracts JSON tolerating markdown fences and missing braces (`_extract_json_array`).
- Accepts: direct array, object keyed by `segments|clips|items|results|data`, unwrapped.
- **Two-pass duration validation:** strict `[min_sec, max_sec]` first; if zero pass, retry with `[1.0, 86400]` lenient.
- Defaults applied per optional field (hook_type, viral_score, …).
- Returns `Optional[list[LLMSegment]]` — `None` only after both passes fail.

### `parse_render_plan_response` (lines 238-338)

- Accepts native, `{render_plan: {...}}`, or legacy `{segments: [...]}` shapes.
- Validates clips via `_filter_and_score_clip_dicts` (lines 405-457) — same duration bounds.
- `RenderPlan.from_json` (domain layer) does defensive sub-plan recovery — malformed `subtitle_policy` etc. fall back to defaults.
- Returns `Optional[RenderPlan]`.

**Malformed JSON behaviour:** never raises. Logs warning. Returns `None`. ✓ Honors Sacred Contract #3.

**FINDING-AI04 (MED):** Lenient duration fallback (`[1.0, 86400]`) can let segments through that ignore the user's `min_sec/max_sec`. Mitigated by a *third* bounds check at [llm_pipeline.py:337-347](../../backend/app/features/render/engine/pipeline/llm_pipeline.py). But: the FE has no way to know "we accepted clips outside your constraint because nothing else passed". Minor UX issue.

---

## 4. Orchestration / call chains

### 4.1 `run_llm_pre_render` (llm_pipeline.py:68-448)

Phase by phase, all from a single file read:

| Phase | Lines | What |
|---|---|---|
| Pre-flight validation | 88-134 | check `llm_enabled` (warn if False), provider+key resolution, audio-stream check; **HARD-FAIL** if any missing |
| Transcription | 152-296 | reuse SRT if `resume_from_last`; else `transcribe_with_adapter` (default model `base`, env `LLM_WHISPER_MODEL`); cache 72 h TTL; heartbeat thread updates progress every 5 s |
| Segment selection | 317-334 | `run_llm_segment_selection` (`llm_stage.py:145`) — applies `llm_min_quality` (default 0.6) with lenient fallback when *every* segment scores below threshold |
| Bounds + clip_exclude + clip_lock | 337-417 | global [0, video_dur+0.5] check; filter exclude ranges; promote lock ranges; **HARD-FAIL** if exclude empties result |
| Return | 434-448 | `LLMPreRenderResult` shaped like legacy pre_render output (backward compat) |

### 4.2 `run_llm_segment_selection` (llm_stage.py:145-260)

Wraps `_run()` with try/except → returns `None` on any error (Sacred Contract #3 honored).

### 4.3 `build_creator_context` (context/builder.py:78-82)

- DB read of `creator_prefs.prefs_json.creator_context`.
- Returns `None` if empty.
- Enrich step currently a no-op (Sprint 4 placeholder).
- Outer try/except — silently swallows errors. Caller appends nothing to prompt.

### 4.4 AI Visibility summary (visibility/ai_visibility_summary.py)

Called by `attach_ai_visibility_summaries` ([line 182](../../backend/app/features/render/ai/visibility/ai_visibility_summary.py)) inside `render_pipeline.py`. Builds the FE-facing dict at `GET /api/jobs/{id}/ai-summary`:

- `badges` — boolean badges per signal (hook ≥ 80, retention ≥ 70, …)
- `reasons` — weighted ranking contributions
- `warnings` — quality penalties / missing scores
- `signals` — numeric scores (output, hook, market, …)
- `is_best`, `confidence_tier` — FE metadata

---

## 5. Retries / fallback

**No retry loops** in the AI path. Only:

- **Parser lenient retry** (parse_segment_response, lines 106-115) — defensive duration fallback, not a real retry.
- **Provider invalid-name fallback** (dispatcher line 49-61) — falls back to default; does *not* try alternate providers on actual failure.

No exponential backoff, no per-provider timeout, no jitter.

**FINDING-AI05 (MED):** Network errors against Claude/OpenAI/Gemini have no retry. A single transient `503` from a provider kills the LLM call → kills `run_llm_pre_render` → kills the job. Phase 11 roadmap should add small `Retry-After`-aware backoff (e.g., 2 attempts with 2s/4s) inside each provider.

---

## 6. Caching

| Layer | What | Where |
|---|---|---|
| Whisper transcription | full SRT cached 72 h, keyed `(source_path, mtime, size, model, lang)` | `pipeline_cache.py:52-81` |
| Scene detection | PySceneDetect output cached 72 h | `pipeline_cache.py:22-49` |
| Motion path | per-segment crop path cached 72 h | `engine/motion/cache.py` |
| ASS content | content-addressable cache (SHA-256 of inputs) | `pipeline_cache.py:102-150` (Sprint 7.3) |
| **LLM response** | **None** | — |

**FINDING-AI06 (MED):** Re-rendering the same video re-pays Whisper but skips it via cache. The LLM call is *not* cached. If a user retries the same render, the same LLM call is paid again. Phase 11 should consider a request-cache keyed on `(provider, model, srt_hash, prompt_hash, params_hash)`.

---

## 7. Validation

- Per-segment duration bounds (parser).
- Bounds against `video_duration + 0.5 s`.
- `clip_exclude` filtering, `clip_lock` promotion.
- `llm_min_quality` threshold with lenient fallback.
- `_filter_and_score_clip_dicts` re-applies duration bounds in RenderPlan path.
- `RenderPlan.from_json` recovery for malformed sub-plans.

No plausibility / hallucination checks beyond these (e.g., no "does this segment exist in the transcript timeframe"). Phase 4 should consider adding one.

---

## 8. Sacred Contract #3 verification

Rule: every public function under `backend/app/features/render/ai/**` must catch all exceptions and return `None`. Verified 11 entry points:

| Function | File:line | Verdict |
|---|---|---|
| `Claude.select_segments` | `llm/providers/claude.py:42-66` | ✓ try/except, returns None |
| `Claude.select_render_plan` | `llm/providers/claude.py:137-169` | ✓ |
| `OpenAI.select_segments` | `llm/providers/openai.py:36-60` | ✓ |
| `OpenAI.select_render_plan` | `llm/providers/openai.py:131-163` | ✓ |
| `Gemini.select_segments` | `llm/providers/gemini.py:46-75` | ✓ |
| `Gemini.select_render_plan` | `llm/providers/gemini.py:148-183` | ✓ |
| `run_llm_segment_selection` | `pipeline/llm_stage.py:145-163` (caller) | ✓ |
| `build_creator_context` | `ai/context/builder.py:78-82` | ✓ |
| `HybridAnalyzer.analyze` | `ai/analysis/hybrid.py:50-65` | ✓ (returns always; catches at 74-78) |
| `LocalAnalyzer.analyze` | `ai/analysis/local.py:49-64` | ✓ |
| `CloudAnalyzerBase.analyze` | `ai/analysis/cloud/base.py:29-44` | ✓ |

All 11 honor the contract at their public boundary. ✓ PASS.

---

## 9. Mandatory-LLM gate (Phase F1)

In [llm_pipeline.py:68-448](../../backend/app/features/render/engine/pipeline/llm_pipeline.py), seven hard-fail sites raise `LLMPipelineError`:

| Site | Reason |
|---|---|
| 88-91 | source has no audio stream |
| 124-128 | no API key (after all 3 sources checked) |
| 290-291 | Whisper transcription failure |
| 299-301 | SRT empty after transcription |
| 326-334 | LLM returned no segments / empty list |
| 344-347 | segments out of bounds |
| 382-384 | `clip_exclude` removed all segments |

`LLMPipelineError` propagates to `run_render_pipeline`'s outer `try` → job marked `failed`.

**No legacy fallback path exists** (the Sprint 2.2 builder shim was deleted in Sprint 4.H, commit `dbd758a`).

**FINDING-AI07 (HIGH — repeat of S07 / B05):** This contradicts the *spirit* of Sacred Contract #3 ("never bring down the render via the AI path"). Modules return None correctly; the pipeline *itself* raises. Either:

- (a) make Phase F1 truly mandatory and document the dependency clearly to the user (FE error code, settings hint), or
- (b) restore a legacy heuristic fallback for offline mode.

Pick one explicitly. Right now it's ambiguous.

---

## 10. `LLM_EMIT_RENDER_PLAN` flag

- Env var `LLM_EMIT_RENDER_PLAN`. Read at `render_pipeline.py:161`.
- Default: **`"1"` (ON)** since Sprint 7.6a (flipped 2026-06-05).
- Gates:
  - line 533 — issuance of `select_render_plan` LLM call.
  - line 1086 — output rank resolution: when ON, uses `RenderPlan.clips[i].rank` permutation if valid; when OFF, score-descending sort.
- Disable path: `LLM_EMIT_RENDER_PLAN=0` reverts to legacy single-call segment selection + score sort.

---

## 11. Surprises & dead surface

**FINDING-AI08 (LOW):** Legacy `select_segments` + `LLMSegment` + `_to_scored_dict` retained for one+ release cycle of `LLM_EMIT_RENDER_PLAN=1`. Planned cleanup, not surprise.

**FINDING-AI09 (LOW):** `context/builder.py::CreatorContextBuilder` has an `enrich(...)` step that is currently a no-op placeholder (Sprint 4). Not dead code (called) but contributes nothing.

**FINDING-AI10 (LOW):** `tracing.py`, `diagnostics.py`, `dependencies.py` at `ai/` top-level — these are utility modules. The first two surface AI provider status via diagnostic endpoint; `dependencies.py` lazy-imports optional deps (`torch`, `groq`, `openai`, `google-genai`). Healthy pattern, but Phase 5 should confirm `groq` is actually still used (CLAUDE.md hints groq imports were stripped Sprint 7.5; `dependencies.py` may still mention it).

---

## Summary table

| Layer | Status | Notes |
|---|---|---|
| Provider dispatch | ✓ | gemini default; explicit user choice respected |
| Prompts | ✓ | format-safety verified, tested |
| Parsing | ✓ | resilient, double-pass duration, returns None |
| Orchestration | mixed | hard-fail by design but documented poorly |
| Retries | ✗ | none — single network glitch kills the job |
| Caching | partial | transcription/scene/motion/ASS cached; LLM not |
| Validation | ✓ | three-layer duration enforcement |
| Sacred Contract #3 (modules) | ✓ | 11/11 entry points return None |
| Mandatory LLM gate | ⚠ | raises at pipeline level — surfaces poorly in FE |
| `LLM_EMIT_RENDER_PLAN` | ✓ | ON by default, env-overridable |

End of 06_workflow_ai.md.
