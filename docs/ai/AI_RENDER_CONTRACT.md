# AI_RENDER_CONTRACT.md

**Status**: Active — enforced governance document.
**Scope**: AI involvement in the render pipeline.
**Date**: 2026-05-23 (Phase 5.1)
**Branch**: `restructure/output-timeline-architecture`

---

## 1. Purpose

This document defines the contract between the AI subsystem and the render
pipeline. It exists to prevent scope creep, ensure AI output is always
validated before affecting a render, and guarantee the system works offline
once the knowledge base is built.

Any AI code that violates these rules is a bug, not a feature.

---

## 2. AI Is Local-First — No External LLM at Render Runtime

- The render runtime **must not** call any external LLM API (OpenAI, Anthropic,
  Ollama remote, etc.) during a render job.
- All AI decisions must be derivable from local knowledge files and local
  heuristic scoring.
- Cloud AI **may** be used offline to generate or curate knowledge items
  (e.g. to populate `knowledge/processed/*.jsonl`), but the render job
  itself must work with zero network connectivity once the knowledge index exists.
- If no index exists and no knowledge files exist, the system degrades
  gracefully — renders proceed with safe defaults, a warning is logged, and
  no error is surfaced to the user.

---

## 3. RAG Is Filter-Based Knowledge Retrieval — Not Personal User Memory

The terms "RAG" and "memory" are overloaded in this codebase. The contract is:

| System | Location | Purpose |
|---|---|---|
| `memory_store` | `app/ai/rag/memory_store.py` | RAG infrastructure — stores per-job render experience for semantic retrieval. Not active in production render path yet (H3). |
| `knowledge/` | `backend/knowledge/` | Platform and video-quality knowledge — filter-based retrieval (platform, niche, style, duration). **This is the desired usage.** |

RAG in the render context means:
- **Retrieve** knowledge items that match the user's render filters.
- **Augment** the render plan with matched rules (pacing, subtitle, hook, visual).
- **Generate** a deterministic render plan from matched rules.

It does not mean:
- Streaming LLM text generation during a render.
- Semantic "chat" or "ask the AI" interactions.
- Personal memory of individual users across sessions.

---

## 4. AI Must Not Control Render Infrastructure

AI output is advisory only. AI **must not** directly control:

- FFmpeg command construction or filter graph generation
- Filesystem paths (output directory, temp directory, channel directory)
- Database reads or writes
- WebSocket payloads or job state updates
- Route registration or HTTP response shapes
- Security boundaries (filename sanitisation, path traversal checks)

All AI output must pass through the render plan validation layer before
influencing any of the above.

---

## 5. AI Output Must Be Structured and Validated Before Render

The AI subsystem produces structured output objects:

```
CreativeBrief  → validated → ScenePlan  → validated → VisualDirection
```

Validation rules:
- All required fields must be present with correct types.
- All numeric values must be within safe render ranges (e.g. playback speed
  clamped to [0.5, 1.5]; subtitle font scale clamped to [0.5, 2.0]).
- Unknown fields are ignored (forward compatibility).
- Validation errors are logged and the fallback path is taken.

---

## 6. Invalid AI Output Must Fall Back to Safe Defaults

When AI output fails validation or is unavailable:
- The render proceeds using safe hardcoded defaults.
- A structured warning is logged (not an error — renders must complete).
- The output is not degraded; only AI augmentation is skipped.

Fallback must never:
- Block or cancel a render job.
- Raise an unhandled exception that propagates to the route layer.
- Silently use corrupted or partially-validated AI output.

---

## 7. Knowledge Sources

The knowledge base covers real-world video production patterns:

| File | Content |
|---|---|
| `platform_rules.jsonl` | Encoding format, aspect ratio, codec requirements per platform |
| `hook_patterns.jsonl` | Opening hook strategies for retention |
| `subtitle_rules.jsonl` | Subtitle readability, word count, positioning |
| `pacing_rules.jsonl` | Cut frequency, clip duration, playback speed |
| `visual_rules.jsonl` | First-frame quality, brightness, blur avoidance |
| `cta_patterns.jsonl` | Call-to-action placement and timing |
| `failure_patterns.jsonl` | Known render failure modes and QA check mappings |

Knowledge items are curated by humans (or offline cloud AI). They are
static at render time — no knowledge is written during a render job.

---

## 8. User Filters Drive Retrieval

The knowledge retriever matches user-provided render filters against knowledge items:

| Filter | Matched Field |
|---|---|
| `platform` | `platform[]` |
| `niche` | `niche[]` |
| `style` | `style[]` |
| `duration` | `duration_range[min, max]` |
| `aspect_ratio` | `render_usage.aspect_ratio` |
| `subtitle_style` | `render_usage.subtitle_emphasis` |
| `output_count` | Not directly filtered — affects how many scene plans are built |
| `target_goal` | `tags[]` |

Retrieval is deterministic: same filters always produce the same knowledge set.
No stochastic LLM sampling occurs during retrieval.

---

## 9. Cloud AI May Only Populate Knowledge — Never Runs at Render Time

Acceptable uses of cloud AI:
- Generating knowledge items for `processed/*.jsonl` offline.
- Curating or scoring existing knowledge items offline.
- Generating example render plans for developer review.

Unacceptable uses of cloud AI:
- Any API call during a render job (`POST /api/render/process`).
- Any API call triggered by user interaction in the editor.
- Any API call triggered by the QA pipeline.

The test suite must be runnable with no network connectivity. Any test that
requires an external API call is a contract violation.

---

## 10. Local Runtime Must Work Offline

Once the knowledge index (`knowledge/index/faiss.index`) is built:

- Server restarts must not require network access.
- Render jobs must complete without any outbound HTTP requests from the AI layer.
- The FAISS index is rebuilt from `knowledge/processed/*.jsonl` on startup if
  the index file is missing — still no network access required.
- If both the index and the knowledge files are missing, a warning is logged
  and renders proceed with safe defaults.

---

## Future Render Flow (Target Architecture)

```
User render filters (platform, niche, style, duration, aspect_ratio,
                     subtitle_style, output_count, target_goal)
        │
        ▼
Knowledge retrieval
  Filter-match against knowledge/processed/*.jsonl
  Rank by weight field
  Top-N rules selected
        │
        ▼
CreativeBrief
  {hook_pattern, subtitle_rules, pacing_rules, visual_rules, cta_pattern}
  Validated — all fields checked, safe ranges enforced
        │
        ▼
ScenePlan
  {segments, cut_points, durations}
  Validated — durations in range, segment count bounded
        │
        ▼
VisualDirection
  {subtitle_style, font_scale, emphasis_keywords, first_frame_check}
  Validated — style ID in known presets, scale in [0.5, 2.0]
        │
        ▼
Validation / fallback layer
  Any invalid field → replaced with safe default
  Warning logged
        │
        ▼
Deterministic render pipeline
  render_pipeline.py → FFmpeg commands → encoded output
        │
        ▼
QA pipeline (qa_pipeline.py)
  _validate_render_output — file existence, size, duration, audio stream
  _assess_output_quality  — first-frame dark/blur, subtitle/hook presence
        │
        ▼
Output
  Rendered video parts → output_dir
  QA report → job metadata
```

---

## Phase 5.2 Status

| Component | Status |
|---|---|
| Local knowledge loader | ACTIVE — `app/ai/rag/knowledge_loader.py` reads all `knowledge/processed/*.jsonl` |
| Knowledge schema | DEFINED — `app/ai/rag/knowledge_schema.py` — `KnowledgeItem` dataclass with validation |
| Filter-based retrieval | ACTIVE — `KnowledgeIndex.query()` applies platform/niche/style/duration/aspect_ratio/subtitle_style/target_goal filters |
| FAISS load/save/rebuild | ACTIVE — `KnowledgeIndex.save()/load()/rebuild()` with metadata persistence; FALLBACK MODE if FAISS/sentence-transformers unavailable |
| Startup warmup | ACTIVE — `warmup_knowledge_index()` called in daemon background thread at startup |
| Retrieved knowledge injected into AI edit context | ACTIVE — `retrieved_knowledge` and `knowledge_filters` added to `_ai_context` in `render_pipeline.py` |
| AI edit plan knowledge hints | ACTIVE — `pacing_hint`, `subtitle_emphasis_hint`, `hook_hint` extracted in `ai_director.py`; attached as advisory `knowledge_injection` metadata |
| Minimal trace logger | ACTIVE — `app/ai/tracing.py` — `AITraceLogger` writes JSONL to `data/logs/{job_id}_ai_trace.jsonl` |
| No cloud AI at runtime | CONFIRMED — zero external API calls during render |
| Render works without knowledge/index | CONFIRMED — missing knowledge files, missing FAISS index, or retrieval failure all degrade gracefully; renders proceed with safe defaults |

---

## Phase 5.3 Status

| Component | Status |
|---|---|
| Contract models | IMPLEMENTED — `app/ai/contracts.py`: `CreativeBrief`, `RenderExecutionHints`, `AIValidationResult` dataclasses with `to_dict()` |
| Validation layer | IMPLEMENTED — `app/ai/validators.py`: `validate_execution_hints()` clamps speed [0.5,1.5], cut intervals [1.0,12.0], enforces allowed subtitle/visual enums, strict bool check; records fixups |
| Knowledge→hints mapper | IMPLEMENTED — `app/ai/render_mapper.py`: `map_knowledge_to_execution_hints()` sorts by weight, maps pacing/subtitle/hook from `render_usage`, always calls validator |
| AI director integration | IMPLEMENTED — `ai_director.py` calls mapper after all Phase 53–57 blocks; stores `execution_hints`, `validation_fixups`, `validation_warnings` in `plan.knowledge_injection` |
| Pacing hint application | ADVISORY ONLY — `cut_interval_min/cut_interval_max` logged; no compatible runtime parameter for override; render behavior unchanged |
| Subtitle emphasis hint | ADVISORY ONLY — `subtitle_emphasis_style` logged; per-part style resolved from `payload.subtitle_style` and DNA/platform bias; render behavior unchanged |
| Hook overlay hint | APPLIED — `hook_overlay_enabled=False` gates `_hook_overlay_enabled`; True/None keeps existing behavior; only AI-controlled change to render behavior |
| Trace logger additions | IMPLEMENTED — `log_execution_hints()`, `log_validation_fixup()`, `log_decision_rejected()` added to `AITraceLogger` |
| AI still cannot control FFmpeg | CONFIRMED — zero FFmpeg command changes; zero filter graph changes |
| Deterministic + offline-safe | CONFIRMED — mapper output is deterministic; zero external API calls |
| Render safe on AI failure | CONFIRMED — mapper exception caught in ai_director; render continues |

---

## Phase 5.4 Status

| Component | Status |
|---|---|
| Pacing config model | IMPLEMENTED — `app/ai/pacing.py`: `AIPacingConfig` dataclass, `build_ai_pacing_config()` |
| Pacing hint application | APPLIED — `cut_interval_min/max` from knowledge hints now sets `_seg_min_sec/_seg_max_sec` before `build_segments_from_scenes()` |
| User explicit override | ENFORCED — if `payload.min_part_sec` or `max_part_sec` differ from schema defaults (15/60), user values win; AI rejected with `user_duration_override` |
| Segment function coverage | ALL THREE — `build_segments_from_scenes()`, `refine_segment_boundaries()`, `refine_cuts_for_naturalness()` now use `_seg_min_sec/_seg_max_sec` |
| Early retrieval | IMPLEMENTED — knowledge retrieved before segment building; results reused by Phase 5.2/5.3 block (no double-query) |
| Trace logger | EXTENDED — `log_pacing_applied()` added to `AITraceLogger`; writes `ai.pacing_applied` JSONL event |
| Subtitle hints | ADVISORY ONLY — unchanged from Phase 5.3 |
| Hook overlay gate | ACTIVE — unchanged from Phase 5.3 |
| FFmpeg changes | NONE — zero changes to FFmpeg commands or filter graphs |
| Render safe on AI failure | CONFIRMED — all pacing failures degrade to payload defaults; never raises |
| AI disabled behavior | CONFIRMED — if `ai_director_enabled=False`, early pacing block skipped; `_seg_min_sec/_seg_max_sec` = payload values |

---

## Phase 5.5 Status

| Component | Status |
|---|---|
| Subtitle emphasis config model | IMPLEMENTED — `app/ai/subtitle_hints.py`: `AISubtitleEmphasisConfig` dataclass, `build_ai_subtitle_emphasis_config()` |
| Subtitle emphasis hint application | APPLIED — `subtitle_emphasis_style` from knowledge hints now passed as `emphasis_level_override` to `subtitle_emphasis_pass()` in per-part subtitle loop |
| Emphasis style validation | ENFORCED — only "subtle"/"medium"/"strong"/"word_only" allowed; unknown styles rejected with `invalid_emphasis_style` |
| No new style IDs | CONFIRMED — `emphasis_level_override` only changes text transform behavior; `_effective_subtitle_style` (preset ID for ASS generation) is never changed |
| Subtitle timing safety | CONFIRMED — `subtitle_emphasis_pass()` modifies only `b['text']`, never `b['start']` or `b['end']`; SRT timestamps preserved |
| User subtitle_style preservation | CONFIRMED — `_effective_subtitle_style` resolution hierarchy (variant > creator > platform > DNA > content-type default) unchanged; AI only affects emphasis level inside the pass |
| Trace logger | EXTENDED — `log_subtitle_emphasis_applied()` added to `AITraceLogger`; writes `ai.subtitle_emphasis_applied` JSONL event |
| AI disabled behavior | CONFIRMED — if `ai_director_enabled=False`, Phase 5.5 block skipped; emphasis derived from preset_id as before |
| Missing knowledge fallback | CONFIRMED — no knowledge/hints → `applied=False` → `emphasis_level_override=None` → existing behavior |
| Invalid hint fallback | CONFIRMED — invalid style → `rejected_reason="invalid_emphasis_style"` → `emphasis_level_override=None` → existing behavior |
| Pacing hints | ACTIVE — unchanged from Phase 5.4 |
| Hook overlay gate | ACTIVE — unchanged from Phase 5.3 |
| FFmpeg changes | NONE — zero changes to FFmpeg commands or filter graphs |
| API changes | NONE — no new API endpoints, no schema changes, no websocket payload changes |
| Render safe on AI failure | CONFIRMED — all subtitle emphasis failures degrade to original behavior; never raises |

---

## Phase 5.6 Status

| Component | Status |
|---|---|
| Visual intensity config model | IMPLEMENTED — `app/ai/visual_hints.py`: `AIVisualIntensityConfig` dataclass, `build_ai_visual_intensity_config(execution_hints, payload)` |
| Visual injection point | FOUND (Phase 5.7) — `visual_intensity_hint: str | None = None` added to `render_part()`, `render_part_smart()`, `render_base_clip()`; renderer calls `resolve_effect_preset_with_intensity()` which maps hint to known presets only |
| Visual intensity hint application | ACTIVE (Phase 5.7) — `visual_intensity` hint validated; `applied=True` when valid; `render_overrides={"visual_intensity_hint": <value>}`; render_pipeline extracts value and passes to renderer; renderer OWNS mapping (low→story_clean_01, medium→slay_soft_01, high→slay_pop_01); AI never picks preset name or FFmpeg string |
| User visual override detection | ENFORCED — if `payload.effect_preset != "slay_soft_01"` (schema default), hint rejected with `user_visual_override`; `effect_preset` never mutated |
| Trace logger | EXTENDED — `log_visual_intensity_applied()` added to `AITraceLogger`; writes `ai.visual_intensity_applied` JSONL event; `log_decision_rejected()` called for every rejection including `no_safe_visual_injection_point` |
| AI disabled behavior | CONFIRMED — if `ai_director_enabled=False`, Phase 5.6 block skipped; `ai_disabled` rejection logged |
| Missing knowledge fallback | CONFIRMED — no knowledge/hints → `applied=False` → `render_overrides={}` → existing behavior |
| Invalid hint fallback | CONFIRMED — invalid intensity → `rejected_reason="invalid_visual_intensity"` → `render_overrides={}` → existing behavior |
| Subtitle hints | ACTIVE — unchanged from Phase 5.5 |
| Pacing hints | ACTIVE — unchanged from Phase 5.4 |
| Hook overlay gate | ACTIVE — unchanged from Phase 5.3 |
| FFmpeg changes | NONE — zero changes to FFmpeg commands or filter graphs |
| API changes | NONE — no new API endpoints, no schema changes, no websocket payload changes |
| Render safe on AI failure | CONFIRMED — all visual intensity failures degrade to existing behavior; never raises |

---

## Changelog

| Date | Change |
|---|---|
| 2026-05-23 | Initial document — Phase 5.1 AI knowledge foundation |
| 2026-05-23 | Phase 5.2 — local knowledge retrieval activated; knowledge schema/loader/index/warmup/tracing implemented |
| 2026-05-23 | Phase 5.3 — AI contract models, validation layer, knowledge→hints mapper, limited render influence (hook overlay gate), trace logger extensions |
| 2026-05-23 | Phase 5.4 — AI pacing hints now applied to segment selection; `AIPacingConfig` model; early retrieval before segment building; user explicit limits override AI; no FFmpeg changes |
| 2026-05-23 | Phase 5.5 — AI subtitle emphasis hints now applied to subtitle text transforms; `AISubtitleEmphasisConfig` model; `emphasis_level_override` parameter added to `subtitle_emphasis_pass()`; no new style IDs; no timing changes; no FFmpeg changes |
| 2026-05-23 | Phase 5.7 — Safe visual intensity injection point found and implemented; `visual_intensity_hint: str | None = None` added to `render_part()`, `render_part_smart()`, `render_base_clip()`; `resolve_effect_preset_with_intensity()` added to `ffmpeg_helpers.py`; renderer OWNS mapping table (low→story_clean_01, medium→slay_soft_01, high→slay_pop_01); `applied=True` now possible; `render_overrides={"visual_intensity_hint": <value>}`; AI passes only low/medium/high — never a preset name or FFmpeg string; user explicit `effect_preset` always wins; `payload.effect_preset` never mutated |
| 2026-05-23 | Phase 5.6 — AI visual intensity hint infrastructure built; `AIVisualIntensityConfig` model; `log_visual_intensity_applied()` trace logger added; no safe injection point found — hints logged as advisory only; no FFmpeg changes; no render behavior changes |
| 2026-05-23 | Phase 5.8 — Quality intelligence added: `app/quality/` module with `QualityIssue`, `QualityReport`, `assess_rendered_part_quality()`; `_assess_render_quality_intelligence()` wired in `qa_pipeline.py` and `render_pipeline.py`; all checks are non-fatal; warnings never affect ok/error result; no FFmpeg changes; no API changes; AI trace JSONL read for correlation |

---

## Phase 5.8 Summary (2026-05-23)

**Quality Intelligence Added — Offline, Deterministic, Non-Blocking**

Post-render quality assessment now runs automatically after `_assess_output_quality()` succeeds in `render_pipeline.py`. The assessment:

- Is **NEVER fatal** — all exceptions caught internally; warnings never convert to errors
- Uses **only local probes** (ffprobe cached metadata, SRT parsing, file checks)
- Writes a **sidecar JSON report**: `<output_dir>/quality/<job_id>_part_<N>.json`
- Correlates **AI trace events** from `data/logs/{job_id}_ai_trace.jsonl`
- Does **NOT** auto-regenerate video or change render behavior

Assessment categories:
1. File integrity (missing/zero-byte → CRITICAL, early exit)
2. Video probe (ffprobe failure → ERROR)
3. Audio stream presence (missing → WARNING)
4. Duration vs manifest (mismatch > tolerance → ERROR)
5. First frame quality (dark/blur → WARNING, confidence ≤ 0.7)
6. Subtitle density (too fast / flash / line too long → WARNING; >30% flash → ERROR)
7. Hook risk (first subtitle > 5s → WARNING; first block > 15 words → WARNING)
8. Pacing risk (< 3s or > 300s → WARNING)
9. AI trace correlation (reads events from JSONL, stores in ai_trace_refs)


---

## Phase 5.9 Addition (2026-05-23)

**Quality Report API — Read-Only Exposure**

Two new GET endpoints expose the Phase 5.8 quality sidecar JSON via the API:

- `GET /api/jobs/{job_id}/parts/{part_no}/quality` — single-part report
- `GET /api/jobs/{job_id}/quality` — aggregated job-level summary

**Contract constraints for Phase 5.9**:
- API is **READ-ONLY** — no render behavior change of any kind
- **No FFmpeg calls** in any quality report route
- **No auto-regeneration** of videos or quality reports
- **No raw filesystem paths** accepted from or exposed to the client
- **No AI hints** modified or triggered
- **No DB schema changes**
- Invalid `job_id` (non-alphanumeric) → 400; missing job/part → 404; missing report → 404
