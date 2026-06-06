# 22 — AI Pipeline Reference

Rebuilt from code on 2026-06-06. Deep trace in [06_workflow_ai.md](06_workflow_ai.md).

## Modules

All AI code under [backend/app/features/render/ai/](../../backend/app/features/render/ai/) (ghost dir `backend/app/ai/` does not exist).

| Subdir | Purpose |
|---|---|
| `analysis/` | hybrid + local + cloud content analyzers |
| `llm/providers/{claude,openai,gemini}.py` | LLM clients (lazy-imported SDKs) |
| `llm/parser.py` (458 LOC) | resilient JSON extraction + duration-bounded validation |
| `llm/prompts.py` (423 LOC) | prompt templates (segment + RenderPlan) |
| `llm/__init__.py` | provider dispatch |
| `context/builder.py` | creator context fetch from DB |
| `visibility/ai_visibility_summary.py` | FE-facing AI decision summary |
| `dependencies.py`, `diagnostics.py`, `tracing.py` | optional-import gates + runtime status |

## Providers

| Provider | SDK | Default model | File |
|---|---|---|---|
| Anthropic Claude | `anthropic` (opt-in) | `claude-haiku-4-5-20251001` | `llm/providers/claude.py:29` |
| OpenAI | `openai` (opt-in) | `gpt-4o-mini` | `llm/providers/openai.py:23` |
| Google Gemini | `google-genai` (opt-in) | `gemini-2.5-pro` | `llm/providers/gemini.py:26` |

Dispatcher [llm/__init__.py:28](../../backend/app/features/render/ai/llm/__init__.py): `DEFAULT_PROVIDER = "gemini"`.

Sacred Contract #3 verified for all 11 public entry points (Phase 2 §8).

## Two LLM calls

1. **`select_segments`** — legacy, returns `LLMSegment` list. Being retired post Sprint 7.6.
2. **`select_render_plan`** — Sprint 4.C, returns full `RenderPlan` dataclass. Now default (`LLM_EMIT_RENDER_PLAN=1` since Sprint 7.6a).

## Pipeline (run_llm_pre_render)

[features/render/engine/pipeline/llm_pipeline.py:68-448](../../backend/app/features/render/engine/pipeline/llm_pipeline.py).

| Phase | Lines | Behaviour |
|---|---|---|
| Pre-flight | 88-134 | check `llm_enabled`, provider+key, audio stream; **HARD-FAIL** if any missing |
| Transcription | 152-296 | Whisper (default `base` model, env `LLM_WHISPER_MODEL`); cache 72 h; heartbeat every 5 s |
| Segment selection | 317-334 | call dispatcher; apply `llm_min_quality` filter with lenient fallback |
| Bounds + exclude + lock | 337-417 | global [0, video_dur+0.5]; clip_exclude filter; clip_lock promotion |
| Return | 434-448 | `LLMPreRenderResult` |

**Mandatory-LLM gate:** raises `LLMPipelineError` on any of 7 failure conditions. No retry, no fallback. The whole render job dies on a single transient cloud error (Phase 2 / Phase 4 BR02).

## RenderPlan emission

[render_pipeline.py:533-652](../../backend/app/features/render/engine/pipeline/render_pipeline.py). Gated by `LLM_EMIT_RENDER_PLAN=1` (default ON).

- Generates structured plan: `clips[]`, `subtitle_policy`, `camera_strategy`, `audio_plan`, `overlays`.
- Persisted via `update_render_plan(job_id, plan_json)` ([db/jobs_repo.py:61](../../backend/app/db/jobs_repo.py)).
- On parser failure: `_render_plan = None`, legacy `scored[]` path engages silently. FE does not learn (Phase 2 S05).

## Caching

| Surface | Cache? |
|---|---|
| Whisper transcription | ✓ 72 h |
| LLM response | ✗ none (Phase 4 AI06) |
| Scene detection | ✓ 72 h |
| Motion path | ✓ 72 h |
| ASS content | ✓ content-addressable |

## Validation pipeline

1. Parser duration bounds: strict `[min_sec, max_sec]` → lenient `[1.0, 86400]` fallback.
2. Pipeline-level bounds: `[0, video_dur + 0.5]`.
3. `clip_exclude` removal, `clip_lock` promotion.
4. `llm_min_quality` threshold.
5. `_filter_and_score_clip_dicts` re-applies bounds in RenderPlan path.
6. `RenderPlan.from_json` defensive recovery for malformed sub-plans.

## Failure modes

| Failure | Behaviour | Severity |
|---|---|---|
| No API key | HARD-FAIL, job dies | HIGH (Phase 2 AI07) |
| Provider 503 | HARD-FAIL, job dies (no retry) | HIGH (Phase 2 AI05) |
| Provider returns malformed JSON | parser returns None → pipeline raises | HIGH |
| No segments in [min_sec, max_sec] | parser falls back to lenient bounds; pipeline checks again at video_dur+0.5; raises if still empty | HIGH |
| clip_exclude removes everything | HARD-FAIL | MED |
| Whisper transcription fails | HARD-FAIL | HIGH |

## AI Visibility surface

[features/render/ai/visibility/ai_visibility_summary.py](../../backend/app/features/render/ai/visibility/ai_visibility_summary.py) builds the dict served at `GET /api/jobs/{id}/ai-summary`:

- `badges[]`, `reasons[]`, `warnings[]`, `signals{}`, `is_best`, `confidence_tier`, `hybrid_analysis{}`.

Frontend consumer: `frontend/src/api/jobs.ts:147-164` (`JobAiSummary` interface).

End of 22_ai_pipeline.md.
