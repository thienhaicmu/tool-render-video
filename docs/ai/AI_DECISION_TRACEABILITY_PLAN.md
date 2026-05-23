# AI_DECISION_TRACEABILITY_PLAN.md

**Status**: IMPLEMENTED — Phase 5.2. `AITraceLogger` is live in `app/ai/tracing.py`.
**Scope**: Future structured logging for AI render decisions.
**Date**: 2026-05-23 (Phase 5.1)
**Branch**: `restructure/output-timeline-architecture`

---

## Purpose

When a rendered output is bad (wrong pacing, wrong subtitle style, wrong
hook, no CTA, muted audio, etc.), the developer must be able to answer:

> "Why did the AI choose this scene / style / subtitle / pacing / hook?"

Without traceability logging, the answer is "unknown" — the AI is a black
box. This plan defines what must be logged at each AI decision point so
post-mortem analysis is possible.

---

## Logged Data Points

Each render job that uses AI augmentation must write a structured traceability
record to `data/logs/{job_id}_ai_trace.jsonl`. One JSON line per decision event.

### 1. Input Filters

Logged at the start of knowledge retrieval.

```json
{
  "event": "ai.input_filters",
  "job_id": "...",
  "timestamp": "...",
  "filters": {
    "platform": "tiktok",
    "niche": "education",
    "style": "viral",
    "duration": 45,
    "aspect_ratio": "9:16",
    "subtitle_style": "bounce",
    "output_count": 3,
    "target_goal": "retention"
  }
}
```

### 2. Retrieved Knowledge IDs and Scores

Logged after filter-matching, before rule selection.

```json
{
  "event": "ai.knowledge_retrieved",
  "job_id": "...",
  "timestamp": "...",
  "candidates": [
    {"id": "tiktok_hook_001", "type": "hook_pattern", "weight": 0.9, "match_reason": ["platform:tiktok", "niche:education"]},
    {"id": "pacing_medium_fast_001", "type": "pacing_rule", "weight": 0.8, "match_reason": ["platform:tiktok", "style:viral"]}
  ],
  "total_candidates": 12,
  "top_k": 5
}
```

### 3. Selected Rules and Why

Logged when rules are promoted from candidates to the CreativeBrief.

```json
{
  "event": "ai.rules_selected",
  "job_id": "...",
  "timestamp": "...",
  "selected": [
    {"id": "tiktok_hook_001", "type": "hook_pattern", "reason": "highest weight for platform+niche"},
    {"id": "pacing_medium_fast_001", "type": "pacing_rule", "reason": "highest weight for platform+style"}
  ]
}
```

### 4. Heuristic AI Decisions Made

Logged for each parameter the AI chose heuristically (not directly from a knowledge rule).

```json
{
  "event": "ai.heuristic_decision",
  "job_id": "...",
  "timestamp": "...",
  "parameter": "playback_speed",
  "chosen_value": 1.1,
  "reason": "pacing_rule suggests medium_fast; mapped to 1.1x by heuristic table",
  "source_rule_id": "pacing_medium_fast_001"
}
```

### 5. Rejected Decisions and Why

Logged when a candidate rule or heuristic value was considered but not applied.

```json
{
  "event": "ai.decision_rejected",
  "job_id": "...",
  "timestamp": "...",
  "rejected_id": "cta_follow_001",
  "reason": "duration 20s is below cta_pattern minimum 30s",
  "filter_mismatch": {"duration": 20, "duration_range": [30, 120]}
}
```

### 6. Validation Fixups Applied

Logged when AI output failed validation and a field was corrected to a safe default.

```json
{
  "event": "ai.validation_fixup",
  "job_id": "...",
  "timestamp": "...",
  "field": "playback_speed",
  "ai_value": 2.5,
  "clamped_to": 1.5,
  "reason": "playback_speed exceeds max 1.5 — clamped to safe max"
}
```

### 7. Fallback Reasons

Logged when AI augmentation could not be applied and the render fell back to defaults.

```json
{
  "event": "ai.fallback",
  "job_id": "...",
  "timestamp": "...",
  "reason": "no_knowledge_files",
  "detail": "knowledge/processed/ is empty — AI augmentation skipped",
  "fallback_used": "safe_defaults"
}
```

Possible `reason` values:
- `no_knowledge_files` — knowledge directory empty
- `no_index` — faiss.index missing and rebuild failed
- `no_matching_rules` — filters matched zero knowledge items
- `validation_failed` — CreativeBrief or ScenePlan failed validation entirely
- `ai_exception` — unexpected exception in AI layer (detail contains traceback summary)

### 8. Final Render Plan Summary

Logged after all decisions are made and the render plan is finalised.

```json
{
  "event": "ai.render_plan_summary",
  "job_id": "...",
  "timestamp": "...",
  "plan": {
    "hook_pattern_id": "tiktok_hook_001",
    "subtitle_style": "bounce",
    "subtitle_emphasis": "highlight_problem_keyword",
    "pacing_rule_id": "pacing_medium_fast_001",
    "playback_speed": 1.1,
    "cut_interval_range": [3, 5],
    "visual_rule_id": "visual_brightness_001",
    "first_frame_check": true,
    "cta_rule_id": null,
    "cta_applied": false,
    "fallback_count": 0
  },
  "knowledge_ids_used": ["tiktok_hook_001", "pacing_medium_fast_001", "visual_brightness_001"],
  "heuristic_decisions": 2,
  "validation_fixups": 0
}
```

---

## Log File Location

```
data/logs/{job_id}_ai_trace.jsonl
```

One file per job. Each line is one event (JSON Lines format). Same directory
as the existing job log (`{job_id}.log`).

The file is optional — renders proceed normally if logging fails. Never raise
from trace logging code.

---

## Implementation Guidance

When implementing:

1. Create `app/ai/tracing.py` with a `AITraceLogger` class.
2. `AITraceLogger.__init__(job_id, log_dir)` — opens the `.jsonl` file.
3. One method per event type: `log_input_filters()`, `log_retrieved()`, etc.
4. All methods catch all exceptions — tracing must never crash the render.
5. File is flushed after each write (no buffering).
6. `render_pipeline.py` creates an `AITraceLogger` instance at the start of
   each job and passes it to the knowledge retrieval layer.

---

## Why This Is Needed

Without this log:
- QA failures are opaque: "render was bad" with no explanation.
- Developer cannot distinguish "AI chose wrong rule" from "AI fell back silently".
- A/B testing knowledge changes has no ground truth.
- Debugging knowledge item errors requires re-running the entire pipeline.

With this log:
- Open `data/logs/{job_id}_ai_trace.jsonl` to see exactly which rules were
  applied, which were rejected, what was clamped, and why.
- Cross-reference with `{job_id}.log` (render events) to correlate AI decisions
  with render outcomes.

---

## Implementation Status (Phase 5.2)

| Item | Status |
|---|---|
| `AITraceLogger` class | IMPLEMENTED — `app/ai/tracing.py` |
| `log_input_filters()` | IMPLEMENTED |
| `log_knowledge_retrieved()` | IMPLEMENTED — logs IDs and scores only (not full rule text) |
| `log_rules_selected()` | IMPLEMENTED |
| `log_fallback()` | IMPLEMENTED |
| `log_render_plan_summary()` | IMPLEMENTED |
| Log path | `data/logs/{job_id}_ai_trace.jsonl` |
| Wired into render_pipeline.py | YES — creates `AITraceLogger(job_id)` in AI director block |
| Never raises | CONFIRMED — all methods catch all exceptions |

---

## Implementation Status (Phase 5.3)

| Event | Status |
|---|---|
| `ai.execution_hints` | IMPLEMENTED — `log_execution_hints(hints, source_knowledge_ids)` |
| `ai.validation_fixup` | IMPLEMENTED — `log_validation_fixup(fixups)` |
| `ai.decision_rejected` | IMPLEMENTED — `log_decision_rejected(reason, detail=None)` |
| Wired in render_pipeline.py | YES — execution hints, fixups, and advisory-only rejections logged after Phase 5.3 block |
| Never raises | CONFIRMED — all three new methods catch all exceptions |

---

## Implementation Status (Phase 5.4)

| Event | Status |
|---|---|
| `ai.pacing_applied` | IMPLEMENTED — `log_pacing_applied(config)` added to `AITraceLogger` |
| Wired in render_pipeline.py | YES — after `build_ai_pacing_config()` call in early pacing block; logs applied or rejected with reason |
| `ai.decision_rejected` reason: `user_duration_override` | IMPLEMENTED — logged when user explicit limits override AI |
| `ai.decision_rejected` reason: `no_pacing_hint` | IMPLEMENTED — logged when execution hints have no cut_interval values |
| Never raises | CONFIRMED |

---

## Changelog

| Date | Change |
|---|---|
| 2026-05-23 | Initial planning document — Phase 5.1 |
| 2026-05-23 | Phase 5.2 — `AITraceLogger` implemented and wired into `render_pipeline.py` |
| 2026-05-23 | Phase 5.3 — `log_execution_hints`, `log_validation_fixup`, `log_decision_rejected` added; wired for execution hints and advisory rejections |
| 2026-05-23 | Phase 5.4 — `log_pacing_applied()` added; `ai.pacing_applied` event IMPLEMENTED; wired in render_pipeline.py early pacing block |
