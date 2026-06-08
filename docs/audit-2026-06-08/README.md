# Audit 2026-06-08 — CTO Workflow Review

24-phase architectural audit of the AI Video Render Studio conducted
2026-06-08 against `main @ 50127a3` (post-Batch-10 closure + CTO
audit fix + E2E FFmpeg test). Method: evidence-based forensic
investigation of code (no test-pass shortcuts). 4 parallel research
agents + 1 single-thread follow-up after rate-limit. Output: 16+
findings across 4 batches; 9-commit closure sprint executed in-session.

## Table of Contents

| Doc | Contents |
|-----|----------|
| [README.md](README.md) | This file — index + commit ledger + status |
| [AUDIT_FINDINGS.md](AUDIT_FINDINGS.md) | Batch A+B forensic findings (V8 / V9 / B- IDs with file:line evidence) |
| [STRATEGIC.md](STRATEGIC.md) | Batch C+D — gap analysis, RenderPlan readiness, CTO verdict |
| [PLAN.md](PLAN.md) | Execution plan with per-task status (Sprint 1 → 4) |

## Source vs Target Architecture

**Source (the user's stated vision):**
```
Local Video → Transcript → Creator Context Builder → AI Director → RenderPlan → Render Engine → Output
```

**Current state (from code):**
- L2.5 on the 0–5 RenderPlan readiness scale.
- ~58% of the target workflow correctly wired end-to-end.
- AI decides ~25% of the pipeline; Render Engine ~65%; defaults ~10%.

## Commit Ledger — 9 commits on `feature/audit-2026-06-08-fixes`

| # | Commit | Tier | Tasks | Closures |
|---|--------|------|-------|----------|
| 1 | `b4a5052` | LOW | T1.5 + T1.6 + T1.7 | MAX_SRT_CHARS NameError; 3 always-empty result_json stubs; 7 stale `select_segments` docstring refs |
| 2 | `48a5173` | CRITICAL | T1.1 + T1.2 | V9-C1/C2/D2 false-success path; V9-A1/G1 resume bypass of Sacred Contract #8 |
| 3 | `a32833e` | MEDIUM | T1.3 | V9-E1 — FE HTTP polling fallback when WS exhausts |
| 4 | `0a20349` | HIGH | T1.4 | V8-B5 + UP26 + UP27 + v2 — 19 dead intent fields stripped from wire surface |
| 5 | `7f57475` | MEDIUM | T2.4 | V8-A1 — `target_duration` wired into LLM prompt as soft target |
| 6 | `2c2c201` | CRITICAL | T2.2 | V9-F3 — OpenCV motion loops honor cancel signal |
| 7 | `f2b035f` | TEST | VW-1 + T1.4 follow-up | Sprint 4 regression guards (11 new tests) + 2 more dead fields caught by guard |
| 8 | `7d15005` | FIX | T3.2 + VW-3 | B-10-B status-string asymmetry; V8-C2 WS handler enriches AI metadata |
| 9 | `1c8635b` | HIGH (x2) | T2.3 + T2.1 | B-10-A — ANALYZING + SCENE_DETECTION now emitted (Sacred Contract #4 spec made true); V9-F2 — Whisper between-segment cancel poll |

### Test Suite

| | Before | After |
|---|---|---|
| Tests | 771 | **782** |
| Net new behavioural / structural guards | — | **11** |

### Sacred Contracts

| Contract | Status |
|----------|--------|
| #1 result_json frozen keys (output_rank_score, is_best_output, is_best_clip) | Unchanged |
| #2 RenderRequest additive defaults | PRESERVED. All 21 stripped fields stay in RenderRequest. |
| #3 AI returns None never raise | Unchanged |
| #4 JobStage transition names | STRENGTHENED. ANALYZING + SCENE_DETECTION now actually emitted. |
| #5 JobPartStage transition names | Unchanged |
| #6 `_emit_render_event` signature | Unchanged. WS shape additive (parts gain 4 optional keys). |
| #7 `data/app.db` sole authority | Unchanged |
| #8 `qa_pipeline` never bypassed | **RESTORED IN FULL.** Resume path now goes through the same gate as fresh renders. |

## Batch A Findings — Status Map

| ID | Title | Severity | Status |
|----|-------|----------|--------|
| V9-C1 / V9-C2 / V9-D2 | AI returns None → 0 outputs → status="completed" → success toast | **CRITICAL** | ✅ Closed (T1.1) |
| V8-C1 | `_emit_render_event` JSONL never reaches FE WS | **CRITICAL** | ⏳ Deferred (T3.1 — 1-week sprint) |
| V9-A1 / V9-G1 | Resume-skip bypasses full `_validate_render_output` | HIGH | ✅ Closed (T1.2) |
| V9-E1 | FE has no HTTP polling fallback | HIGH | ✅ Closed (T1.3) |
| V8-B5 | FE sends Phase-G zombie flags (4 fields) | HIGH | ✅ Closed (T1.4) |
| UP26 4 fields (clip_lock/exclude/structure_bias/subtitle_emphasis) | Dead Pro Timeline Steering | HIGH | ✅ Closed (T1.4) — strip only; LLM wiring deferred |
| UP27 asset_music_profile | Dead UP27 field | MEDIUM | ✅ Closed (T1.4) |
| v2 dead (energy_style, output_language, narration_style) | Validated then ignored | MEDIUM | ✅ Closed (T1.4) |
| max_export_parts, part_order | Engine ignores | MEDIUM | ✅ Closed (T1.4 follow-up) |
| V8-A1 | `target_duration` validated, never used | HIGH | ✅ Closed (T2.4) |
| V8-A7 | `playback_speed=1.07` silent default | HIGH | ⏳ Deferred — needs UI design |
| V8-A12 | `clip_lock`/`clip_exclude` never reach LLM | HIGH | ⏳ Strategic (fields removed; LLM wire is separate work) |
| V8-D1 | Local ranking recomputes, overrides AI score | HIGH | ⏳ Strategic (Sprint 2+ of 90-day roadmap) |
| V8-C2 | `clip_name`/`ai_title`/`ai_reason` not persisted | HIGH | ✅ Closed (VW-3 — WS handler enriches; HTTP path already enriched per FINDING-C03) |
| V9-F2 | Whisper uninterruptible | HIGH | ✅ Closed (T2.1) |
| V9-F3 | OpenCV motion crop uninterruptible | HIGH | ✅ Closed (T2.2) |
| V9-F5 | Cancel registry restart loss | MEDIUM | ⏳ Strategic (persistence task) |
| B-12-A | NVENC_SEMAPHORE gap 4 sites | HIGH | ⏳ Strategic (Sprint 2+) |
| B-10-A | ANALYZING + SCENE_DETECTION stages never emitted | HIGH | ✅ Closed (T2.3) |
| B-10-B | `partial` status synthesized but never persisted | MEDIUM | ✅ Closed (T3.2) |
| P2-4 | MAX_SRT_CHARS NameError silently disabled truncation warning | LOW | ✅ Closed (T1.5) |

**Closed:** 16. **Deferred — design discussion:** 5. **Critical-tier deferred:** 1 (T3.1).

## Decisions Documented for Future Sprints

- **V8-A7 `playback_speed=1.07` silent default** — fix requires either UI control (FE form addition) or BE default change (Sacred Contract #2 stored-payload replay implications). Defer pending product/design discussion.
- **T3.1 event-bus → FE WS bridge** — closes V8-C1. ~1 week sprint. Largest remaining observability gap.
- **UP26 wire to LLM (V8-A12)** — `clip_lock` / `clip_exclude` semantic wiring on top of the LLM prompt. Needs prompt-design work.
- **V8-D1 ranking source visibility** — surface "AI rank vs local recompute" choice in result_json + FE.
- **V9-F5 persistent cancel signal** — survives backend restart.

## PR

https://github.com/thienhaicmu/tool-render-video/compare/main...feature/audit-2026-06-08-fixes
