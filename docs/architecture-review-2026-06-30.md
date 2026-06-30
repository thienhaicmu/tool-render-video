# Architecture Review — Closure Record (2026-06-30)

> One-session response to a CTO-board architecture review of the Story
> Intelligence pipeline + Recap/Clip rendering surface. Seven batches
> shipped; substrate + first consumer in place; remaining consumer
> wiring (CRITICAL tier) deferred to follow-up sprints.
>
> **Final HEAD:** `13cfb6d` · **Range:** `eebcfe0..13cfb6d` · **7 commits**
> · **+197 tests** · **0 regression** · **0 Sacred Contract violations**

When this doc and code conflict: **trust code.** This is a snapshot of
the session's outcome, not a living spec.

---

## Commits at a glance

| Batch | SHA | Theme | New tests |
|-------|-----|-------|-----------|
| A | [`eebcfe0`](#) | Naming + typing + observability — `PROMPT_VERSION` cache keying, `RenderFormat` Literal, WS pass events, Prometheus chars counters | 25 |
| B | [`8ce29cb`](#) | `StoryBeat ↔ RecapScene` deterministic reconciler (`StoryBeat.bound_scene_index`) | 19 |
| C | [`650e05d`](#) | **Comprehension stage hoisted** out of `select_recap_plan` — Recap-only wire-in (Q1=a, Q2=a, Q3=a) | 27 |
| D-1 | [`0c8caa0`](#) | Edge-TTS content-addressable cache (the #2 perf gap flagged in the review) | 31 |
| D-3 | [`a3b555c`](#) | `LLM_MAX_SRT_CHARS` parity knob + Anthropic prompt-cache extension to clips + rewrite paths | 30 |
| D-2-thin | [`0caf895`](#) | **SceneMap substrate** — `scene_detector.detect_scenes()` revived from dead code | 48 |
| D-2-snap | [`13cfb6d`](#) | **Pass-3 snap-to-shot reconciler** — `RecapPlan.snap_scenes_to_shots()` consumes D-2-thin SceneMap | 17 |
| D-2-motion Phase 1 | [`7301db0`](#) | **Audit + scaffolding** — architecture audit doc, `SceneMap.slice()` helper, mock-based motion dispatch tests, A/B benchmark script + 3 synthetic fixtures. NO motion/crop.py touch. | 31 |
| D-2-motion Phase 2 | [`2f5c05b`](#) | **A/B benchmark verdict** — ran benchmark on 3 synthetic fixtures using `backend/.venv` (cv2 4.11.0 + scenedetect 0.6.4 already installed). Verdict: ✅ CONDITIONAL GO with Policy A fallback. Phase 3 unblocked. | — (verdict doc only) |
| Batch B test fix | [`4cde1de`](#) | Pre-edit pytest baseline housekeeping — `test_storymodel_v1_strings_upgrade_to_entities` had stale `schema_version == 2` assertion from before Batch B's bump to v3. Made Phase 3 delta check meaningful. | — |
| **D-2-motion Phase 3** | [`20c8249`](#) | **Actual `motion/crop.py` swap** — `scene_map` kwarg threaded through `render_motion_aware_crop` ← `render_part_smart` ← `part_render_encode.py`. Policy A: SceneMap when `MOTION_USE_SCENE_MAP=1` + non-empty, pixel-diff fallback otherwise. Shipped default OFF (Sacred Contract #2 conservative). | 0 new (zero regression on 2147 baseline) |
| **D-2-motion default flip** | [`50cefcd`](#) | **`MOTION_USE_SCENE_MAP` default 0 → 1** — operator authorisation; deviates from Phase 2 verdict's 2-3-validation-renders recommendation. One-character change in `motion/crop.py`. Pixel-diff fallback (Policy A) bounds risk to subtle visual drift on cinematic content. Instant rollback via env var. | 0 new (zero regression on 2147 baseline) |
| **C.1 Phase 1** | (this commit) | **Clip-path Comprehension substrate** — `use_story_intelligence: bool = False` on RenderRequest + audit doc + 16 contract tests pinning the Phase 2/3 wire-up surface. NO `render_pipeline.py` touch. NO provider touch. Default False → bit-identical production. | +16 (2147 → 2163 baseline) |

---

## Architecture-review backlog — status

### ✅ Done in this session

| Item | Where |
|------|-------|
| Prompt versioning + cache invalidation by construction | A |
| `RenderFormat` typed `Literal` at API boundary | A |
| WS observability between Story Intelligence passes | A |
| Coarse-grained LLM cost telemetry (chars/4 ≈ tokens) | A |
| StoryBeat ↔ RecapScene back-reference for re-edit UI | B |
| "Did pass-3 cover every plot turn?" diagnostic (`coverage_pct`) | B |
| Comprehension stage substrate ready for Clip consumer | C |
| `jobs.story_model_json` persisted for re-edit | C |
| Edge-TTS cache (re-render skips network) | D-1 |
| Provider transcript cap parity (single env knob) | D-3a |
| Anthropic prompt-cache on clips + rewrite paths | D-3b |
| SceneMap substrate (`jobs.scene_map_json`, stage, domain) | D-2-thin |
| `scene_detector.py` dead-code revival | D-2-thin |
| **Pass-3 picks snap to nearest shot boundary** (Recap quality win) | **D-2-snap** |
| **D-2-motion Phase 1** (audit + scaffolding + helper) | **D-2-motion Phase 1** |
| **D-2-motion Phase 2** (A/B benchmark verdict — CONDITIONAL GO) | **D-2-motion Phase 2** |
| **D-2-motion Phase 3** (motion/crop.py swap — substrate live) | **D-2-motion Phase 3** |
| **D-2-motion default flip** (`MOTION_USE_SCENE_MAP` 0 → 1 — operator authorisation, deviates from verdict recommendation) | **D-2-motion default flip** |
| **C.1 Phase 1** (Clip-path Comprehension substrate — schema field + audit + contract tests) | **C.1 Phase 1** |

### ⏳ Deferred (consumer-wiring follow-ups)

| Item | Priority | Risk | Effort | Notes |
|------|----------|------|--------|-------|
| **D-2-motion production-validate** — run 2-3 real-content renders; flip back to `0` if visual quality regresses on dissolves / lighting-change-in-shot content | Operator side | LOW | ~30min | The verdict's recommended Phase 2 fallback step. If renders look bad: `export MOTION_USE_SCENE_MAP=0` |
| **C.1 Phase 2** — `render_pipeline.py` reads the flag + calls `run_comprehension(...)` when True | #1 strategic | **CRITICAL** | ~2h | Substrate ready (this commit); see [audit §2.2](audit-c-1-2026-06-30.md) for the exact insertion-point sketch. |
| **C.1 Phase 3** — 3 provider `select_render_plan` sigs + `_story_block` prompt injection + `PROMPT_VERSION = 2` bump | #1 strategic | HIGH × 3 | ~2h | Final closure of architecture review's #1 strategic gap. |

**Recommended next-sprint order:** Production-validate D-2-motion (~30min) → C.1 (own sprint, CRITICAL).

---

## New operator knobs (env vars)

All defaults preserve historical behaviour — **Sacred Contract #2 spirit**.

### Caching

| Env var | Default | Effect |
|---------|---------|--------|
| `STORY_INTELLIGENCE_HOIST_ENABLED` | `1` | `0` → Comprehension stage no-op; `select_recap_plan` runs legacy internal pass-1 (Batch A behaviour bit-identical). |
| `SCENE_MAP_ENABLED` | `1` | `0` → `scene_map_stage.run_scene_map()` no-op; recap proceeds without a SceneMap. |
| `RECAP_SNAP_TO_SHOTS_ENABLED` | `1` | `0` → `RecapPlan.snap_scenes_to_shots()` is not called; scenes keep their AI-emitted timestamps. |
| `RECAP_SNAP_TOLERANCE_SEC` | `0.5` | In-tolerance window for the snap reconciler. Matches scene_detector's `_TV2_MERGE_GAP_SEC` by design. |
| `TTS_CACHE_ENABLED` | `1` | `0` → Edge-TTS hits the network on every call (legacy). |
| `MOTION_USE_SCENE_MAP` | `1` | D-2-motion Phase 3 wire. Default flipped to `1` on 2026-06-30 (deviates from Phase 2 verdict's "2-3 production validation renders first" recommendation — operator authorisation; Policy A pixel-diff fallback bounds risk to subtle visual drift on cinematic dissolves / lighting-change-in-shot content). `0` → instant rollback to pixel-diff (legacy, bit-identical). |

### Claude prompt-cache gates (all default `1` = ON)

| Env var | Wraps |
|---------|-------|
| `CLAUDE_RECAP_CACHE` | Recap pass + Story pass (existing — gate unchanged) |
| `CLAUDE_CLIPS_CACHE` | `_call_claude_once` (clips path) — **new** |
| `CLAUDE_REWRITE_CACHE` | `_call_claude_rewrite_once` (per-part rewrite) — **new** |

### Transcript cap parity

```
LLM_MAX_SRT_CHARS          # NEW global parity knob
CLAUDE_MAX_SRT_CHARS       # per-provider override (existed)
GEMINI_MAX_SRT_CHARS       # per-provider override (existed)
OPENAI_MAX_SRT_CHARS       # per-provider override (existed)
```

Resolution priority: per-provider > global > hardcoded default (Claude 50K /
Gemini 60K / OpenAI 30K). Defensive parsing — malformed values fall
through, never raise.

---

## New schema versions (cache-invalidation-by-construction)

| Constant | Value | Bump triggers |
|----------|-------|---------------|
| `PROMPT_VERSION` (`ai/llm/prompts.py`) | `1` | Any prompt template wording change. Folded into LLM disk-cache SHA-256 key + Comprehension cache key. |
| `STORY_SCHEMA_VERSION` (`domain/recap_plan.py`) | `3` | StoryModel wire-shape change. v1/v2 blobs still load defensively. |
| `EDITORIAL_SCHEMA_VERSION` (`domain/recap_plan.py`) | `1` | EditorialBlueprint wire-shape change. |
| `RecapPlan.SCHEMA_VERSION` | `4` | RecapPlan envelope change. |
| `SCENE_MAP_SCHEMA_VERSION` (`domain/scene_map.py`) | `1` | SceneMap wire-shape change. |
| `TTS_HUMANIZER_VERSION` (`engine/audio/tts_cache.py`) | `1` | `humanize_narration_text` or `ssml_humanize_for_edge` behaviour change. Folded into TTS cache key. |

---

## New WebSocket events (Sacred Contract #6 — ADDITIVE only)

Top-level `{job, parts, summary}` shape unchanged. New event names:

| Event | Emitted by | Payload `context` |
|-------|-----------|-------------------|
| `recap.pass1.done` | `recap_pipeline` (Batch A) + `comprehension_stage` (Batch C, alias) | `{pass: "story", ok, story_model}` |
| `recap.pass2.done` | `recap_pipeline` (Batch A) | `{pass: "editorial", ok, editorial}` |
| `comprehension.start` | `comprehension_stage` (Batch C) | `{cache_key_prefix, provider}` |
| `comprehension.done` | `comprehension_stage` (Batch C) | `{ok, source: "cache"\|"llm"\|"failed", story_model}` |
| `scene_map.start` | `scene_map_stage` (Batch D-2-thin) | `{video_path}` |
| `scene_map.done` | `scene_map_stage` (Batch D-2-thin) | `{ok, source: "cache"\|"detect"\|"failed"\|"missing-dep", shot_count, total_duration_sec, scene_map}` |

`recap.pass1.done` is preserved as a forever alias even when Comprehension
stage owns the canonical emission (Q3=a) — zero churn for any FE consumer
already wired to it.

---

## New domain modules

| File | Purpose |
|------|---------|
| `backend/app/domain/scene_map.py` | `SceneMap` + `Shot` dataclasses; `find_shot_containing`, `nearest_boundary`, `scene_map_from_detector_result`. |

## New pipeline stages

| File | Purpose |
|------|---------|
| `backend/app/features/render/engine/pipeline/comprehension_stage.py` | Wraps `select_story_model` into a persisted, cached, observable stage. |
| `backend/app/features/render/engine/pipeline/scene_map_stage.py` | Wraps `scene_detector.detect_scenes` into a persisted, cached, observable stage. |

## New cache modules

| File | Purpose |
|------|---------|
| `backend/app/features/render/engine/audio/tts_cache.py` | Edge-TTS content-addressable disk cache (7d TTL, atomic write). |

## New DB columns (additive — Sacred Contract #7)

| Migration | Column |
|-----------|--------|
| `0013_jobs_add_story_model_json.py` | `jobs.story_model_json TEXT NULL` |
| `0014_jobs_add_scene_map_json.py` | `jobs.scene_map_json TEXT NULL` |

---

## Sacred Contract impact summary

Every batch in this session honoured all 8 Sacred Contracts. Notes:

- **#1** (`output_rank_score`, `is_best_output`, `is_best_clip`) — untouched in every batch.
- **#2** (RenderRequest additive defaults) — `RenderFormat` Literal added with default `"clips"` + `mode="before"` validator preserves legacy payload casing.
- **#3** (AI → None, never raise) — every new public surface wrapped in defensive try/except. Stage failures fall back to legacy paths; missing optional deps (`scenedetect`) auto-degrade.
- **#4 / #5** (stage / part names) — frozen, untouched.
- **#6** (WS shape) — only ADDITIVE new event names; top-level structure unchanged. Legacy `recap.pass1.done` alias preserved alongside `comprehension.done`.
- **#7** (DB sole authority) — migrations 0013 and 0014 are additive ALTER TABLE with PRAGMA-guard idempotency.
- **#8** (qa_pipeline gate) — untouched.

---

## Latent issues documented (NOT fixed in this session)

| Issue | Where flagged | Risk |
|-------|---------------|------|
| Piper + XTTS per-engine cache keys omit `voice_id` AND `rate` — same text + different voice = wrong audio | `tts_cache.py` docstring (D-1) | Latent — Edge cache fixed it by construction; offline engines retain the bug. Follow-up D-1.1. |
| Pre-existing test failures: `test_llm_metrics::test_*` fail on `_run_render_plan() got an unexpected keyword argument 'reaction_intensity'` | Pre-existing, not this session | Kwarg drift between dispatcher and `_run_render_plan` helper. ~30min fix. |
| Pre-existing test failures: 8× `test_recap_plan` fail on `ModuleNotFoundError: No module named 'whisper'` | Pre-existing, not this session | Test venv missing optional `whisper` SDK. Env issue, not bug. |

---

## Regression history per batch

| Batch | Baseline passed | Post-batch passed | Delta |
|-------|----------------|-------------------|-------|
| (start) | 1412 | — | — |
| A | 1412 | 1437 | +25 |
| B | 1437 | 1456 | +19 |
| C | 1456 | 1479 | +23 in wider sweep + 4 hidden by `*recap_plan*` glob collision (4 verified standalone) |
| D-1 | 1479 | 1510 | +31 |
| D-3 | 1510 | 1540 | +30 |
| D-2-thin | 1540 | 1588 | +48 |
| D-2-snap | 1588 | 1605 | +17 |

Pre-existing failures (159 failed + 99 collection errors) — **unchanged across all 6 batches**. Causes documented above.

---

## Recommended sprint plan after this session

### Sprint 1 (~1 week)

1. **D-2-motion** (CRITICAL, ~3-5 days) — `motion/crop.py` consumes persisted SceneMap. Own sprint, full pytest baseline, Render Edit Protocol.

### Sprint 2+ (~1 week)

2. **C.1** (CRITICAL, ~1.5-2 days) — Clip pipeline calls Comprehension stage; `select_render_plan` accepts `story_model` kwarg; clips prompt injects StoryModel block; `PROMPT_VERSION = 2` bump.

### Skip / nice-to-have

- Piper/XTTS cache key gap (D-1.1) — fix when convenient
- `reaction_intensity` kwarg drift in `test_llm_metrics` — fix when convenient
- D-3a follow-up: aligning the per-provider default values — only if operator hits a real parity issue

---

## File index — what's new

```
backend/app/domain/
  scene_map.py                                        NEW (D-2-thin)

backend/app/features/render/engine/pipeline/
  comprehension_stage.py                              NEW (C)
  scene_map_stage.py                                  NEW (D-2-thin)

backend/app/features/render/engine/audio/
  tts_cache.py                                        NEW (D-1)

backend/app/db/migration_steps/
  0013_jobs_add_story_model_json.py                   NEW (C)
  0014_jobs_add_scene_map_json.py                     NEW (D-2-thin)

backend/tests/
  test_comprehension_stage.py                         NEW (C)
  test_select_recap_plan_external_story.py            NEW (C)
  test_migration_0013_story_model_json.py             NEW (C)
  test_jobs_repo_story_model.py                       NEW (C)
  test_story_beat_binding.py                          NEW (B)
  test_render_format_enum.py                          NEW (A)
  test_recap_pass_events.py                           NEW (A)
  test_tts_cache.py                                   NEW (D-1)
  test_tts_cache_integration.py                       NEW (D-1)
  test_transcript_cap_resolution.py                   NEW (D-3a)
  test_claude_cache_control_extension.py              NEW (D-3b)
  test_scene_map_domain.py                            NEW (D-2-thin)
  test_scene_map_stage.py                             NEW (D-2-thin)
  test_migration_0014_scene_map_json.py               NEW (D-2-thin)
  test_jobs_repo_scene_map.py                         NEW (D-2-thin)
  test_recap_scene_snapping.py                        NEW (D-2-snap)
```

Total: 5 new app modules + 2 new migrations + 16 new test files + ~12 modified files.

---

## Reading this doc later

- For **operator** questions ("how do I disable X?") → see "Operator knobs".
- For **schema** questions ("what's the wire shape now?") → see "Schema versions" + cross-link to `domain/scene_map.py` / `domain/recap_plan.py` source.
- For **follow-up planning** → see "Deferred" + "Recommended sprint plan".
- For **why a Sacred Contract is honoured** → see commit body of the relevant SHA (`git show <sha>`).
- For **what NOT to do** → see "Latent issues documented" + "Skip / nice-to-have".
