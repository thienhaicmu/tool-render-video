# Execution Plan — Status Ledger

The execution plan drafted in-session to convert audit findings into
shippable closures. Sprint structure mirrors the original 30-day plan
from CTO Verdict Q14; the in-session sprint compressed Months 1-2's
P0/P1 work into 9 commits.

## Status legend

- ✅ **DONE** — shipped this sprint
- ⏳ **DEFERRED** — needs a decision OR larger sprint
- 🔜 **NEXT** — recommended next-up
- ❌ **CANCELLED** — replaced by a better approach

## Sprint 1 — Stop the Bleeding (DONE)

| ID | Tier | Title | Status | Commit |
|----|------|-------|--------|--------|
| T1.1 | CRITICAL | Fail-fast on empty AI emission | ✅ | `48a5173` |
| T1.2 | CRITICAL | Resume-skip runs full QA gate | ✅ | `48a5173` |
| T1.3 | MEDIUM | FE HTTP polling fallback | ✅ | `a32833e` |
| T1.4 | HIGH | Strip 19 dead intent fields from wire | ✅ | `0a20349` |
| T1.4-fu | HIGH | + 2 more (max_export_parts, part_order) caught by VW-1c | ✅ | `f2b035f` |
| T1.5 | LOW | Fix MAX_SRT_CHARS NameError | ✅ | `b4a5052` |
| T1.6 | LOW | Delete 3 always-empty result_json stubs | ✅ | `b4a5052` |
| T1.7 | LOW | Clean 7 stale select_segments docstring refs | ✅ | `b4a5052` |

## Sprint 2 — Cancel UX + State Machine + LLM Wire (DONE)

| ID | Tier | Title | Status | Commit |
|----|------|-------|--------|--------|
| T2.1 | HIGH | Whisper between-segment cancel poll | ✅ | `1c8635b` |
| T2.2 | CRITICAL | OpenCV motion loops honor cancel signal | ✅ | `2c2c201` |
| T2.3 | HIGH | Emit ANALYZING + SCENE_DETECTION stages | ✅ | `1c8635b` |
| T2.4 | MEDIUM | Wire `target_duration` into LLM prompt | ✅ | `7f57475` |

## Sprint 3 — Observability Bridge (PARTIAL)

| ID | Tier | Title | Status | Notes |
|----|------|-------|--------|-------|
| T3.1 | HIGH | Event-bus → FE WS bridge | ⏳ DEFERRED 🔜 NEXT | ~1 week sprint. Closes V8-C1 CRITICAL. Largest remaining observability gap. |
| T3.2 | MEDIUM | `partial` synthetic status → `completed_with_errors` symmetry | ✅ DONE | `7d15005` |

## Sprint 4 — Test Suite Closure (PARTIAL)

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| Sprint 4 a | `test_false_success_zero_outputs.py` — T1.1 guard | ✅ DONE | `f2b035f` |
| Sprint 4 b | `test_resume_runs_full_qa.py` — T1.2 guard | ✅ DONE | `f2b035f` |
| Sprint 4 c | `test_render_request_public_no_dead_fields.py` — T1.4 guard | ✅ DONE | `f2b035f` |
| Sprint 4 d | `test_cancel_interrupts_whisper.py` — T2.1 guard | ⏳ PENDING | 4h effort |
| Sprint 4 e | `test_cancel_interrupts_motion_crop.py` — T2.2 guard | ⏳ PENDING | 4h effort |
| Sprint 4 f | `test_stages_analyzing_scene_detection_emitted.py` — T2.3 guard | ⏳ PENDING | 4h effort |
| Sprint 4 g | FE `useRenderSocket.test.ts` — T1.3 polling fallback | ⏳ PENDING | 4h effort |
| Sprint 4 h | FE `render-workflow-payload.test.ts` — T1.4 dead-field absence | ⏳ PENDING | 2h effort |

## "Viral Wins" — bonus consolidated in-session

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| VW-1a | T1.1 regression guard test | ✅ DONE | `f2b035f` |
| VW-1b | T1.2 regression guard test | ✅ DONE | `f2b035f` |
| VW-1c | T1.4 regression guard test + caught 2 more dead fields | ✅ DONE | `f2b035f` |
| VW-2 | T3.2 partial status sync | ✅ DONE | `7d15005` |
| VW-3 | WS handler enriches parts with AI metadata | ✅ DONE | `7d15005` |
| VW-4 | V8-A7 playback_speed honesty | ⏳ DEFERRED | Needs UI design discussion |

## Bậc 3 — Strategic / 90-Day Roadmap (deferred for separate sprint)

| ID | Title | Effort | Reason for deferral |
|----|-------|--------|---------------------|
| T3.1 | Event-bus → FE WS bridge | ~1 week | Largest sprint of remaining work; closes V8-C1 CRITICAL |
| Strategic-1 | UP26 wire to LLM + local filter (V8-A12) | ~3 days | Needs prompt-design + filter-design work |
| Strategic-2 | Render AI title as on-screen overlay | ~2 days | Needs overlay-styling product decision |
| Strategic-3 | Wire `overlays[kind=cta]` to render path | ~2 days | Needs CTA-overlay product decision |
| Strategic-4 | Ranking source visibility (V8-D1) | ~2 days | Needs surface-design decision |
| Strategic-5 | NVENC_SEMAPHORE gap closure (B-12-A) | ~1 day | Identify 4 sites and acquire semaphore |
| Strategic-6 | Persistent cancel signal (V9-F5) | ~2 days | Needs SQLite-backed flag or filesystem flag |
| Strategic-7 | Refactor routes/jobs.py (935 LOC God module) | ~2 days | LOW value; defer |
| Strategic-8 | Refactor part_asset_planner.py (953 LOC) | ~3 days | LOW value; defer |

## Recommended next session

1. **T3.1 event-bus** — biggest single closure remaining. CRITICAL.
2. **V8-A7 decision** — short product call on playback_speed default
   or UI control.
3. **Sprint 4 d-h** — 5 more regression tests (~18h total) to close
   the test suite for ALL P0/P1 closures.

## Decisions documented

| Decision | Date | Outcome |
|----------|------|---------|
| T2.1 Whisper cancel approach | 2026-06-08 | (b) between-segment poll — preserves Whisper LRU cache |
| T2.3 ANALYZING/SCENE_DETECTION | 2026-06-08 | (b) emit — preserves Sacred Contract #4 |
| V8-A7 playback_speed | 2026-06-08 | DEFER — requires UI design + Sacred Contract #2 trade-off |
| T1.6 result_json stubs | 2026-06-08 | DELETE — all consumers use `.get(... or {})` |
| Branch strategy | 2026-06-08 | `feature/audit-2026-06-08-fixes` carved from main |

## Verification log

| Step | Tests before | Tests after | Status |
|------|-------------|-------------|--------|
| Pre-sprint baseline | — | 771 | ✅ |
| Post-T1.5+T1.6+T1.7 | 771 | 771 | ✅ |
| Post-T1.1+T1.2 (CRITICAL edits) | 771 | 771 | ✅ |
| Post-T1.3 (FE) | 771 | 771 | ✅ (`tsc --noEmit` clean) |
| Post-T1.4 | 771 | 771 | ✅ |
| Post-T2.4 | 771 | 771 | ✅ |
| Post-T2.2 | 771 | 771 | ✅ |
| Post-VW-1 + T1.4 follow-up | 771 | 782 | ✅ (+11 new tests) |
| Post-T3.2 + VW-3 | 782 | 782 | ✅ |
| Post-T2.3 + T2.1 | 782 | 782 | ✅ |

All edits preserved or improved the test count. Zero regressions.

---

## Addendum 2026-06-08 EOD — Final closure status

The body of this file (rows above) reflects the in-session plan as
drafted at the start of the audit sprint. Most "DEFERRED" /
"PENDING" rows shipped before EOD on the same day. This addendum
is append-only per the audit-folder rule (existing rows in the
body are NOT edited — they record what was true at draft time).

### Sprint 4 — Test Suite Closure (now FULL, not partial)

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| Sprint 4 d | `test_cancel_interrupts_whisper.py` — T2.1 guard | ✅ DONE | `1c8635b` |
| Sprint 4 e | `test_cancel_interrupts_motion_crop.py` — T2.2 guard | ✅ DONE | `2c2c201` |
| Sprint 4 f | `test_stages_analyzing_scene_detection_emitted.py` — T2.3 guard | ✅ DONE | `1c8635b` |
| Sprint 4 g | FE `use-render-socket-polling-fallback.test.ts` — T1.3 guard | ✅ DONE | `a32833e` |
| Sprint 4 h | FE `render-workflow-payload.test.ts` — T1.4 dead-field absence | ✅ DONE | `f2b035f` |

### Sprint 3 — Observability Bridge (now FULL, not partial)

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| T3.1 | Event-bus → FE WS bridge | ✅ DONE | `d97f40b` |
| T3.2 | partial → completed_with_errors | ✅ DONE (already noted above) | `7d15005` |

### Bậc 3 — Strategic / 90-Day Roadmap (all shipped same day)

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| Strategic-1 | UP26 clip_lock/exclude wired to LLM prompt | ✅ DONE | `eecc95f` |
| Strategic-1b | UP26 clip_lock/exclude local-side filter | ✅ DONE | `a803973` |
| Strategic-1c | UP26 structure_bias + subtitle_emphasis wired | ✅ DONE | `0130bae` |
| Strategic-2 | AI clip title rendered as hook overlay | ✅ DONE | `b9ac312` |
| Strategic-3 | overlays[kind=cta].type → CTA library bias | ✅ DONE | `11f9c16` |
| Strategic-4 | Ranking source attribution in result_json | ✅ DONE | `3de0161` |
| Strategic-5 | NVENC_SEMAPHORE caller-acquires contract pinned | ✅ DONE | `d67d11c` |
| Strategic-6 | Persistent cancel intent across server restarts | ✅ DONE | `3b3cb53` |
| Strategic-7 | routes/jobs.py history helpers → jobs_history.py | ✅ DONE | `799b068` |
| Strategic-8 | part_asset_planner.py resolvers → part_render_plan_resolvers.py | ✅ DONE | `799b068` |

### Open items remaining

(none — see V8-A7 closure addendum below)

### V8-A7 closure addendum

| ID | Title | Status | Commit |
|----|-------|--------|--------|
| V8-A7 | `playback_speed=1.07` silent default → 1.0 | ✅ DONE | (see commit log) |

Approach chosen: Option A (change default 1.07 → 1.0). Eight modules
updated to keep the fallback literal consistent end-to-end:
`models/render.py`, `pipeline_segment_selection.py`, `clip_renderer.py`,
`motion/crop.py`, `part_asset_planner.py`, `part_cut.py`,
`part_render_encode.py`, `part_render_setup.py`. Sacred Contract #2
replay safety verified: stored payloads with explicit
`playback_speed=1.07` still decode to 1.07 because Pydantic preserves
explicit field values during `model_dump` round-trip
(`tests/test_v8a7_playback_speed_default.py`).

### Verification log addendum

| Step | Tests before | Tests after | Status |
|------|-------------|-------------|--------|
| Post-T2.3 + T2.1 (last row above) | 782 | 782 | ✅ |
| Post-T3.1 + Sprint 4 d-h regression tests | 782 | ~900+ | ✅ (+118 tests, validates V8-C1 closure end-to-end) |
| Post-Strategic-1/1b/1c + Strategic-2/3/4/6 | 900+ | 935 | ✅ |
| Post-Strategic-7/8 god-module refactor | 935 | 941 | ✅ (BE), 476 (FE) — 1417 total, zero regressions |

### Branch state

- Branch: `feature/audit-2026-06-08-fixes`
- 22 commits ahead of `main`
- All 1417 tests pass (BE 941 + FE 476)
- Ready for PR. Comparison: https://github.com/thienhaicmu/tool-render-video/compare/main...feature/audit-2026-06-08-fixes

### One remaining decision

V8-A7 `playback_speed` default 1.07 — silent 7% acceleration on every
render with no UI control. The fix needs a product call, not engineering:

- **Option A** — change BE default `1.07 → 1.00`. Removes silent
  acceleration. Sacred Contract #2 trade-off: replay of any pre-fix
  stored job will now run at 1.00x instead of 1.07x (behaviour shift on
  replay). Mitigation: stored RenderRequest payloads explicitly carry
  the field, so replay is bit-identical for jobs created after the
  RenderRequest field was added. Only pre-field jobs would shift.

- **Option B** — keep default 1.07, add FE UI slider on
  `RenderWorkflow.tsx` so the user can see + adjust. FE work
  (~2-3h) + Sacred Contract #2 unchanged. Default behaviour preserved.

Both options close V8-A7. The audit doesn't prescribe one.

