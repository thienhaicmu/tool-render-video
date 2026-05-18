# RC-1 Stability Sweep

**Branch**: `feature/ai-output-upgrade`  
**Date**: 2026-05-18  
**Commits audited**: `b67a1c1` → `95c58a0` (6 commits)  
**Method**: Static code analysis + agent-assisted survey of render_pipeline.py, subtitle_engine.py, CSS v3, and frontend JS

---

## Legend

| Tag | Meaning |
|---|---|
| ✅ PASS | Verified correct, no action required |
| ⚠️ P1 | Should fix before creator testing |
| ⚠️ P2 | Fix in next sweep, low blast radius |
| ⚠️ P3 | Known gap, investigate when reproduced |
| 🔴 REGRESSION | Introduced in this branch, not pre-existing |
| 📋 MANUAL QA | Requires runtime testing, cannot static-verify |

---

## Track 1 — Render Integrity

### 1.1 Subtitle Stack

| Check | Status | Notes |
|---|---|---|
| Normal render: subtitle follows speech | ✅ PASS | `slice_srt_by_time` with `rebase_to_zero=True` correctly rebases to clip t=0 |
| Resume: CTA at correct timestamp | ✅ PASS | SUBTITLE-HOTFIX-1 P0 fix: `_read_srt_meta` populates `_srt_meta` from cache |
| Resume: no double hook text / emphasis | ✅ PASS | SUBTITLE-HOTFIX-1 P1 fix: `_srt_source_is_fresh` gates all 5 mutation paths |
| TikTok timing aligned with video | ✅ PASS | SUBTITLE-HOTFIX-1 P2 fix: `_get_effective_playback_speed` now used by both slice and validator |
| Duration validation RN001 false-positive | ✅ PASS | SUBTITLE-HOTFIX-1.1 fix: `_render_speed` now calls `_get_effective_playback_speed` |
| P4 hook format exception kills render | ✅ PASS | SUBTITLE-HOTFIX-1 P4 fix: `apply_hook_subtitle_format` wrapped in try/except |
| Multi-part: different subtitle content per clip | 📋 MANUAL QA | File paths are unique per part; `subtitle_file_chain` debug log now available. Structural guarantee exists; runtime verify needed |
| `variant_playback_speed` affects subtitle slice speed | ⚠️ P2 | `_eff_speed` uses `_get_effective_playback_speed` which reads `payload.playback_speed` — does not check `seg.get("variant_playback_speed")`. Variant-specific speed renders at a different speed than subtitle timing |
| P3: identical subtitles root cause confirmed | ⚠️ P3 | No structural collision found in normal code path. Upstream candidates: overlapping `seg["start"]`/`seg["end"]` from segment_builder, or sparse `full_srt` covering all parts. Not fixable without real repro data |

**Recommended action for P2 variant speed gap**: After confirming the variant_playback_speed path is active in production, pass `seg.get("variant_playback_speed") or payload.playback_speed` into `_get_effective_playback_speed` or as a direct override.

---

### 1.2 Multi-Variant Render

| Check | Status | Notes |
|---|---|---|
| Aggressive/balanced/story_first selected independently | ✅ PASS | Three separate scoring functions (hook-weighted, quality-weighted, payoff-weighted) at `_build_variant_segments:449-451` |
| Different CTA tone per variant | ✅ PASS | `_select_cta_text` dispatches on `variant_type` — aggressive→"comment", story_first→"follow", balanced→content default |
| Variant carries distinct subtitle_style | ✅ PASS | `variant_subtitle_style` mapped in `_build_variant_segments` |
| Variant carries distinct playback_speed | ✅ PASS | `variant_playback_speed` applied (±0.05 from base) |
| Limited source variety chip | ✅ PASS | Pool collapse detected and logged `multi_variant_collapsed`; `selection_reason` annotated with "[limited source variety — all variants share same source clip]" |
| Small pool: render continues with all 3 | ✅ PASS (by design) | No abort; all 3 variants returned even if identical segment. Output files may be identical. This is expected; the UI chip signals it |
| `selection_reason` present on every variant | 📋 MANUAL QA | Field annotated in `_build_variant_segments`; verify it reaches the review card |

---

### 1.3 Rerender / Retry Loop

| Check | Status | Notes |
|---|---|---|
| retry_count from payload, not form state | ✅ PASS | `retry_count = max(0, min(5, int(payload.retry_count)))` resolved at render start from frozen payload |
| Payload frozen across retry attempts | ⚠️ P1 | Payload object is **not cloned/frozen**. Mutations to `payload` inside `_process_one_part` (e.g., `seg["cta_applied"]`) are on the segment dict, not on `payload` itself. No direct risk found, but no defensive copy exists. Recommend auditing for any `payload.x = ...` assignments inside the part loop |
| Steering signals preserved between rerenders | ⚠️ P2 | Signals are request-local (per-payload). A "rerender" from the UI sends a new request; steering from the previous render is not automatically carried. UI must re-send them. Verify the UI preserves and re-sends `clip_lock`/`clip_exclude`/`structure_bias` on rerender |
| Out-of-bounds steering signal: warned to creator | ⚠️ P2 | If `clip_lock` or `clip_exclude` range is outside source duration, the segment is silently skipped with no warning emitted. Creator receives no feedback that their steering signal was ignored |

---

### 1.4 Assets (logo / intro / outro / music / brand subtitle)

| Check | Status | Notes |
|---|---|---|
| Missing asset file → safe skip | ✅ PASS | All three functions (`_maybe_prepend_asset_intro`, `_maybe_append_asset_outro`, `_maybe_apply_asset_logo`) check file existence and size before attempting concat; return early with `asset_missing` event on failure |
| Asset concat exception → safe skip | ✅ PASS | Each function wraps its FFmpeg concat in try/except, logs warning, continues render |
| `asset_missing` event emitted | ✅ PASS | All three emit a WARNING-level render event with path and part_no context |
| Music profile / brand subtitle safe-skip | 📋 MANUAL QA | Not found in render_pipeline.py — likely in subtitle_engine or post-processing. Verify these paths have equivalent guards |

---

### 1.5 Recovery System

| Check | Status | Notes |
|---|---|---|
| Subtitle transcription failure → render continues | ✅ PASS | Caught at lines 2749-2763; `full_srt_available=False`; `recovery_success` event emitted with `strategy="skip_subtitles"` |
| Recovery note appears in final render message | ✅ PASS | `_recovery_notes` list accumulated throughout job, included in completion message |
| NVENC failure → codec fallback | 📋 MANUAL QA | `nvenc_available()` checked once for parallelism; actual NVENC→libx264 fallback in render_engine.py (not directly observable in pipeline). Verify codec fallback chain in render_engine |
| Motion crop failure → silent continue | ⚠️ P1 | Motion cache key computation failure sets `_motion_ck=None` and continues — no recovery event emitted to UI. Creator sees no indication that motion-aware crop was disabled for a part |
| Render part exception → recovery_success event | ⚠️ P1 | Individual part render failures are classified and logged but do NOT emit a `recovery_success` event. Only transcription-phase failures do. Creator cannot distinguish "completed all parts" from "completed with silent part failure" from the event stream alone |

---

## Track 2 — UI Integrity

### 2.1 Scroll

| Check | Status | Notes |
|---|---|---|
| Render output panel scrolls | ✅ PASS | H-HOTFIX-2: `#render_output_panel { flex: 1; min-height: 0; overflow-y: auto }` |
| No remaining flex+overflow:hidden clip traps | ✅ PASS | All `overflow:hidden` on flex containers either have `min-height:0` or are for border-radius clipping only (cards) |
| Scroll containers have min-height:0 | ✅ PASS | hardening.css:50-62 explicitly guards all primary scroll containers |
| rqBody horizontal scrollbar | ✅ PASS | POST-FREEZE fix: `overflow-x: hidden` added to `.rqBody` |
| Resize: layout stable | 📋 MANUAL QA | Cannot static-verify; test at multiple breakpoints |
| Sticky header: render output header stays pinned | ✅ PASS | `.renderOutputHeader { position: sticky; top: 0; z-index: 10 }` inside the correct flex scroll owner |
| Sticky header: no stacking context breakage | ✅ PASS | No transform/opacity/will-change on `.renderOutputHeader`; z-index hierarchy clean (modal:1100 > dropdown:1000 > header:10) |

---

### 2.2 Review Flow

| Check | Status | Notes |
|---|---|---|
| Favorite / dismiss / keep keyboard shortcuts | ✅ PASS | K/F/D/R wired with `preventDefault()`; only fire on `.rqCard[tabindex=0]`, not on inputs |
| Keyboard shortcut conflicts | ✅ PASS | No conflicts found; shortcuts scoped to focused card |
| Undo dismiss survives page reload | ✅ PASS | State persisted to localStorage; restored on init |
| Open folder action | 📋 MANUAL QA | Handler wired; verify Electron IPC or native OS call actually fires |
| Retry: duplicate request on rapid clicks | ⚠️ P1 | `retry()` in review-queue.js is async with no AbortController, no pending-request guard, no debounce. Multiple rapid clicks send multiple identical requests to `/api/render/process`. Each spawns a separate job. Recommended fix: set a `_retryPending` flag, reset on response/error |

---

### 2.3 Workspace

| Check | Status | Notes |
|---|---|---|
| At least one CTA always visible | ✅ PASS | "Start Creating" always rendered; "Continue Series" conditional on `series_detected && confidence >= 0.35` |
| No dead-end state after render failure | ✅ PASS | `render-ui.js` reset path clears error state and re-enables UI |
| Error block shows on failure | ✅ PASS | `abp_error_block` toggles on failure; recovery path exists |
| Workspace state survives series fingerprint parse error | ✅ PASS | Graceful fallback to empty state on localStorage parse error |

---

## Track 3 — Performance Sanity

### 3.1 Cache Integrity

| Check | Status | Notes |
|---|---|---|
| Scene cache key includes file mtime + size | ✅ PASS | `(source_path, mtime, size)` → MD5; 72h TTL |
| Motion cache key includes render parameters | ✅ PASS | Key includes start, end, aspect_ratio, scale_x/y, reframe_mode, content_type — very strong isolation |
| Transcription cache resistant to filename collision | ✅ PASS | Key includes mtime + size; same filename with new content gets new cache key |
| Cache entries invalidate on file change | ✅ PASS | mtime/size change creates different key; stale entries naturally expire at TTL |
| Cache file locking under parallel renders | ⚠️ P2 | All three caches share `tempfile.gettempdir()/render_cache/` with no file lock. Race window: Job A stats file → Job B writes cache → Job A reads stale entry. Low probability under current workloads; no locking mechanism |
| Cached SRT content verified on hit | ⚠️ P2 | No CRC/hash check on transcription cache hit. A truncated or corrupted SRT cache file would be used as-is; only the size==0 guard catches complete empties |

### 3.2 Long Session / Memory

| Check | Status | Notes |
|---|---|---|
| Per-job tracking lists cleared between jobs | 📋 MANUAL QA | `_recovery_notes`, `_sub_translate_attempts`, etc. are initialized fresh per `run_render_pipeline` call. Verify no global mutable lists accumulate across calls |
| 10+ render long session | 📋 MANUAL QA | Static analysis cannot detect memory leaks; run sustained batch and monitor RSS |
| Overnight batch queue stability | 📋 MANUAL QA | Cannot static-verify; test with batch queue enabled |

---

## Track 4 — Trust

### 4.1 DNA / Series

| Check | Status | Notes |
|---|---|---|
| DNA applied per-render (not per-channel globally) | ✅ PASS | `creator_dna` is per-payload; no persistent channel-level DNA state |
| Two concurrent renders of same channel: DNA isolation | ✅ PASS | Global caches keyed on file metadata only, not DNA state; no interference |
| Series / episode continuity | ⚠️ P2 | No series continuity logic detected — `continuity_score` field exists on segments but is not carried across renders. Each render treats source independently. For series users, clips may repeat between episodes |

### 4.2 Steering Observability

| Check | Status | Notes |
|---|---|---|
| clip_lock applied before scoring output | ✅ PASS | Applied after viral scoring, before sort: exclude → lock → reorder |
| structure_bias applied to scoring weights | ✅ PASS | Hook/balanced/story multipliers adjusted at sort time |
| Steering signal ignored: creator informed | ⚠️ P2 | Out-of-bounds `clip_lock`/`clip_exclude` ranges silently skipped. No warning event emitted. Creator believes their steering was applied; it wasn't. Recommend: emit a `steering_signal_ignored` event with reason and range |
| Steering carried across rerender | ⚠️ P2 | Request-local only. UI must re-send signals on every rerender. Verify UI does this |

### 4.3 Recovery Observability

| Check | Status | Notes |
|---|---|---|
| Subtitle failure visible to creator | ✅ PASS | `recovery_success` event + recovery note in completion message |
| Voice/narration failure visible to creator | ✅ PASS | Same `recovery_success` pattern |
| Motion crop failure visible to creator | ⚠️ P1 | Silent continue with no event; creator cannot distinguish intentional no-crop from crop failure |
| Individual part render failure visible | ⚠️ P1 | Part failure classified and logged to server log but no `recovery_success` or `part_degraded` event emitted to the UI event stream. Creator sees "render complete" without knowing one clip failed silently |

---

## P0/P1/P2 Summary

### 🔴 Regressions (introduced in this branch — already fixed)

| Issue | Fixed in | Status |
|---|---|---|
| RN001 false positive on TikTok (duration validation) | SUBTITLE-HOTFIX-1.1 | ✅ Fixed |
| CTA appended at t=0 on resume | SUBTITLE-HOTFIX-1 | ✅ Fixed |
| Double hook / emphasis on resume | SUBTITLE-HOTFIX-1 | ✅ Fixed |
| Render output panel clipping (no scroll) | POST-FREEZE BUGFIX | ✅ Fixed |
| rqBody horizontal scrollbar risk | POST-FREEZE BUGFIX | ✅ Fixed |

### ⚠️ P1 — Fix before creator testing

| ID | Area | Issue | Recommended fix |
|---|---|---|---|
| RC1-P1-01 | Review flow | `retry()` lacks pending-request guard; rapid clicks spawn duplicate jobs | Add `_retryPending` flag + AbortController in review-queue.js |
| RC1-P1-02 | Recovery | Motion crop failure emits no UI event | Emit `recovery_success` / `part_degraded` event with `strategy="skip_motion_crop"` at motion cache failure point |
| RC1-P1-03 | Recovery | Individual part render failure not surfaced in event stream | Emit `part_degraded` event when part exception is classified; include part_no and error code |

### ⚠️ P2 — Fix in next sweep

| ID | Area | Issue | Recommended fix |
|---|---|---|---|
| RC1-P2-01 | Subtitle | `variant_playback_speed` not used in subtitle slice speed | Pass variant speed into `_get_effective_playback_speed` or as direct override |
| RC1-P2-02 | Steering | Out-of-bounds steering signals silently dropped | Emit `steering_signal_ignored` event with timestamp range and reason |
| RC1-P2-03 | Steering | Steering not auto-carried on rerender | Verify UI re-sends steering payload on every rerender action |
| RC1-P2-04 | Cache | No file locking on shared render cache | Low priority: add advisory lock or per-job subdirectory |
| RC1-P2-05 | Cache | No integrity check on transcription cache hit | Add size sanity check (min expected size per minute of audio) |
| RC1-P2-06 | Series | No cross-render episode continuity | Design decision needed; document as known gap for series creators |
| RC1-P2-07 | Payload | No defensive copy of payload in part loop | Audit for `payload.x = ...` mutations inside `_process_one_part`; add `copy.copy(payload)` at job entry if any found |

### ⚠️ P3 — Investigate when reproduced

| ID | Area | Issue |
|---|---|---|
| RC1-P3-01 | Subtitle | Identical subtitle content across parts — no root cause confirmed in static analysis; requires real repro with timestamps |

---

## Manual QA Checklist

These items cannot be verified by static analysis. Run before creator testing.

- [ ] **RC1-QA-01** — Normal render: `subtitle_file_chain` log shows different `first_line` per part
- [ ] **RC1-QA-02** — Resume render: CTA timestamp > 0, no duplicate hook text in subtitle file
- [ ] **RC1-QA-03** — TikTok render: `playback_speed_resolution` log shows `effective_speed=1.15` (or whatever base+0.08 is)
- [ ] **RC1-QA-04** — Platform parity: same source on TikTok / YouTube / Instagram all produce `RN001=None`
- [ ] **RC1-QA-05** — Multi-variant: 3 output files present, `selection_reason` chip visible on each review card
- [ ] **RC1-QA-06** — Limited source variety: pool-collapse chip visible when source has < 3 viable segments
- [ ] **RC1-QA-07** — Retry rapid clicks: single job created (not multiple), `_retryPending` guard fires *(after RC1-P1-01 fix)*
- [ ] **RC1-QA-08** — Asset missing: render completes, `asset_missing` event visible in job log
- [ ] **RC1-QA-09** — Keyboard shortcuts: K/F/D/R all fire correctly from focused review card
- [ ] **RC1-QA-10** — Scroll: render output panel scrolls at all window heights; sticky header stays pinned
- [ ] **RC1-QA-11** — NVENC unavailable: verify codec fallback path in render_engine produces valid output
- [ ] **RC1-QA-12** — 10-clip batch: no OOM, no UI slowdown, all jobs complete
