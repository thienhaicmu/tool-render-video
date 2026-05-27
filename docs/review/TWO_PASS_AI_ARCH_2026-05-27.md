# Two-Pass AI Architecture — Architectural Review 2026-05-27

## Summary

This document records the architectural decisions made during the Two-Pass AI Architecture implementation (Phases 43–46, 3a–3c), completed 2026-05-27.

Prior state is described in the conversation context of this session. This file captures what changed, why, and the key invariants going forward.

---

## Problem Statement

Before this work, the AI pipeline had three structural gaps:

**Gap 1 — AI Director selections were advisory only (Phase 44)**
`_ai_edit_plan.selected_segments` was computed but never used to actually replace the heuristic `scored[]` list. The AI selected clips, but the heuristic always won. Fixed by `_map_ai_segments_to_scored()` overlap matching (30% threshold) when `ai_content_driven_selection=True`.

**Gap 2 — Whisper ran after clip selection (Phase 45)**
Transcript was unavailable when clips were being scored and selected. The AI Director had no content understanding at selection time for the default path. Fixed by Phase 45 early transcription block with feature flag `ai_early_transcription`.

**Gap 3 — Each AI consumer re-ran the same analyzers independently**
`ai_director._build_pacing_plan()` called `analyze_beats()` and `analyze_pacing_emotion()` independently. `clip_selector` had no access to hook positions. `viral_scorer` had no narrative structure signal. Three separate analyzer runs for one render job.

---

## Solution: ContentAnalyzer + ContentAnalysisResult

### New files

| File | Role |
|---|---|
| `backend/app/orchestration/content_analysis.py` | `ContentAnalysisResult` dataclass — Layer 4.5 boundary |
| `backend/app/ai/content/__init__.py` | Package marker |
| `backend/app/ai/content/content_analyzer.py` | `ContentAnalyzer` — stateless single-pass analysis |

### ContentAnalysisResult fields

```python
available: bool
chunks: list                  # normalized transcript chunks
narrative_arc: list           # [{start, end, phase, confidence}] — 4 windows
hook_positions: list          # [{time, score, hook_type, text}] — top 5
dominant_emotion: str
emotion_score: float
emotion_arc: list             # [{start, end, emotion, intensity}] — 6 windows
speaker_segments: list        # [{start, end, speech_density, is_question}]
beat_available: bool
bpm: Optional[float]
beat_count: int               # required by beat_execution.py gate (_MIN_BEAT_COUNT=4)
energy_level: Optional[float]
pacing_style: str
suggested_cut_style: str
silence_penalty: float
source_duration: float
analysis_ms: int
warnings: list
```

### Where ContentAnalysisResult is produced

`render_pipeline.py` Phase 46 — runs after Phase 45 (early transcription) when `full_srt_available=True`. Result stored in `_content_analysis` local variable, passed into `_ai_context["content_analysis"]`.

### Where ContentAnalysisResult is consumed (Phase 3a–3c)

| Phase | Consumer | Field(s) used |
|---|---|---|
| 3b | `viral_scorer.score_segments()` | `narrative_arc` → `narrative_phase` per clip |
| 3b | `viral_scorer.score_segments()` | `hook_positions` → `hook_proximity_score` per clip |
| 3c-i | `clip_selector.select_ai_segments()` | `hook_positions` → up to +5 score boost |
| 3c-ii | `ai_director._build_plan()` Phase 4 | `pacing_style`, `bpm`, `beat_count`, `energy_level`, `dominant_emotion`, `emotion_score`, `suggested_cut_style` |
| 3c-iii | `ai_director._build_plan()` transcript | `chunks` — skip SRT re-read |

---

## Fallback Contract

Every consumer checks `content_analysis.available` before using ContentAnalysisResult. When `available=False` (no transcript, analyzer exception, or feature flags off):

- `viral_scorer` sets `narrative_phase="unknown"`, `hook_proximity_score=0.0`
- `clip_selector` skips boost entirely
- `ai_director` calls `_resolve_transcript_chunks()` and `_build_pacing_plan()` as before

No existing behavior changes without opt-in feature flags.

---

## Feature Flags (all default False — Contract 2 compliant)

| Flag | Location | Effect |
|---|---|---|
| `ai_content_driven_selection` | `RenderRequest` in `schemas.py` | AI Director selections override heuristic `scored[]` |
| `ai_early_transcription` | `RenderRequest` in `schemas.py` | Whisper runs before scene detection |

ContentAnalyzer (Phase 46) runs independently of both flags — it runs whenever `full_srt_available=True`. The flags only control the two upstream phases that produce the SRT earlier.

---

## Preserved Invariants

- `_resolve_transcript_chunks()` in `ai_director.py` — kept as fallback, not removed
- `_build_pacing_plan()` in `ai_director.py` — kept as fallback, not removed
- `beat_count` added to `ContentAnalysisResult` specifically to preserve `beat_execution.py` gate (would have silently broken if `beat_count=0` was the default with no fallback)
- All new `RenderRequest` fields default to `False` (Contract 2)
- `scored[]` backward compat: `narrative_phase` and `hook_proximity_score` are additive new fields, no existing field renamed or removed
- Full pytest suite: 7549 passed, 2 skipped throughout — no regression

---

## Layer Model (updated)

```
Layer 4   — scene detection, segment generation
Layer 4.5 — ContentAnalyzer (single-pass content understanding)
Layer 5   — segment scoring (viral_scorer, AI Director clip selection)
Layer 6+  — subtitle, voice, motion crop, FFmpeg, validation
```

Layer 4.5 is the correct insertion point: after transcript is available, before any scoring or selection that benefits from content understanding.

---

## Files Changed (this session)

```
backend/app/models/schemas.py                        # +ai_content_driven_selection, +ai_early_transcription
backend/app/orchestration/render_pipeline.py         # Phase 43 feedback, 44 AI override, 45 early transcription, 46 ContentAnalyzer
backend/app/orchestration/content_analysis.py        # NEW — ContentAnalysisResult dataclass
backend/app/ai/content/__init__.py                   # NEW — package
backend/app/ai/content/content_analyzer.py           # NEW — ContentAnalyzer service
backend/app/services/viral_scorer.py                 # +narrative_phase, +hook_proximity_score enrichment
backend/app/ai/director/clip_selector.py             # +content_analysis param, +_apply_hook_proximity_boost()
backend/app/ai/director/ai_director.py               # 3c-i/ii/iii: pass content_analysis, fast paths
docs/ARCHITECTURE.md                                 # Two-Pass AI section added
docs/PROJECT_FLOW_VI.md                              # Flow and AI Director sections updated
docs/review/TWO_PASS_AI_ARCH_2026-05-27.md           # this file
```
