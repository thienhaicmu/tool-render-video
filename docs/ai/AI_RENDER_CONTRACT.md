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

## Changelog

| Date | Change |
|---|---|
| 2026-05-23 | Initial document — Phase 5.1 AI knowledge foundation |
| 2026-05-23 | Phase 5.2 — local knowledge retrieval activated; knowledge schema/loader/index/warmup/tracing implemented |
