# PRODUCT STATE — QUALITY-UP26: Pro Timeline Control

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): pro timeline steering`
**Status:** Shipped

---

## Summary

Adds creator steering signals on top of the existing AI selection pipeline. **No pipeline rewrite. No manual editing. No new ML.** The AI still selects and edits; the creator can now nudge it with intent.

**Creator goal:** "I can guide what the AI picks, without doing the editing myself."

---

## Philosophy

| Layer | Who controls | Precedence |
|---|---|---|
| Clip Lock | Creator — explicit "include this" | Highest — always respected |
| Clip Exclude | Creator — explicit "never this" | Filters before scoring |
| Structure Bias | Creator — gentle re-weight hint | Above DNA/platform, below lock |
| DNA / Platform | Inferred / set | Default steering |
| AI scoring | Automatic | Baseline |

Creator explicit choices always win. Auto logic is fallback only. Never override creator intent.

---

## Features

### Clip Lock (`clip_lock`)
- Creator clicks **✓ Keep** on a completed clip card
- That timestamp range is promoted to the **front of the scored pool** after slice (after `max_export_parts` cap)
- Persisted in `localStorage` (72h TTL, max 10 entries) via `ClipSteering` module
- Injected into payload as `clip_lock: [{start_sec, end_sec, label, ts}]`

### Clip Exclude (`clip_exclude`)
- Creator clicks **✕ Avoid** on a completed clip card
- That timestamp range is **filtered from the scored pool before ranking**
- Same localStorage persistence as clip_lock
- Injected into payload as `clip_exclude: [{start_sec, end_sec, label, ts}]`

### Structure Bias (`structure_bias`)
- Three-pill Quick Strategy Bar group: **More Hook** / **Balanced** / **More Story**
- Stored in hidden `#qsStructureBias` input; synced via `evSyncQsBar()` / `evQsSet('structure', val)`
- Applied as multipliers to **both** sort paths (combined + standard):
  - `hook`: `_sb_hook_mult=1.25`, `_sb_viral_mult=0.85` — boosts hook score weight
  - `story`: `_sb_hook_mult=0.85`, `_sb_viral_mult=1.15` — boosts viral/story score weight
  - `balanced` (default): both = 1.0 — no change
- Gentle nudge only; cannot destroy a dominant score

### Subtitle Emphasis (`subtitle_emphasis`)
- Advanced settings select: **Subtle** / **Balanced** / **Aggressive**
- Applied to `payload.sub_font_size` **before** the per-part render loop reads it:
  - `subtle`: `max(24, base * 0.82)`
  - `aggressive`: `min(120, base * 1.20)`
  - `balanced`: no change
- Reuses existing `sub_font_size` path — no subtitle engine changes

### Review Loop (Keep / Avoid buttons)
- Appear on **done** clip cards with valid timestamp range
- One click → `ClipSteering.lockClip()` or `ClipSteering.excludeClip()` → `showToast` confirmation
- Decisions persist for next render session (72h TTL)

---

## Files Changed

### `backend/app/models/schemas.py`
- Added 4 optional fields to `RenderRequest`:
  - `clip_lock: Optional[list[dict]] = None`
  - `clip_exclude: Optional[list[dict]] = None`
  - `structure_bias: Optional[str] = None`
  - `subtitle_emphasis: Optional[str] = None`

### `backend/app/orchestration/render_pipeline.py`
- After `score_segments()`: clip_exclude filtering with `_in_exclude_range()` + observability event `clip_excluded`
- After DNA extraction: `_sb_hook_mult`/`_sb_viral_mult` setup from `structure_bias`; subtitle_emphasis → `payload.sub_font_size` adjustment
- In combined sort path: multipliers applied to `vs * 0.80` and `hs * (...)` terms
- In standard sort path: multipliers applied to `viral_score` and `hook_score` terms
- After `max_export_parts` slice: clip_lock promotion with `_in_lock_range()` + observability event `clip_locked`

### `backend/static/js/clip-steering.js` (NEW)
- `ClipSteering` IIFE module
- `lockClip(startSec, endSec, label)`, `excludeClip(...)`, `getClipLock()`, `getClipExclude()`, `getPayload()`, `clear()`, `getCount()`
- `LS_KEY='clip_steering_v1'`, `MAX_ENTRIES=10`, `TTL_MS=72h`

### `backend/static/js/editor-view.js`
- `evQsSet()`: added `structure` group handler → updates `#qsStructureBias`
- `evSyncQsBar()`: syncs Structure pill active state from `#qsStructureBias`
- `startRenderFromEditor()`: injects `structure_bias`, `subtitle_emphasis`, `clip_lock`, `clip_exclude` into payload

### `backend/static/js/render-ui.js`
- Before clip card loop: defines `window.csKeepClip()` and `window.csAvoidClip()` global helpers
- Clip card template: `<div class="clipCardSteerRow">` with Keep and Avoid buttons for done clips

### `backend/static/js/batch-queue.js`
- `_buildPayload()`: adds `structure_bias`, `subtitle_emphasis`, `clip_lock`, `clip_exclude`

### `backend/static/index.html`
- Quick Strategy Bar: added Structure group (More Hook / Balanced / More Story pills) + `<input type="hidden" id="qsStructureBias" value="balanced">`
- Advanced settings: added `#evSubtitleEmphasis` select (Subtle / Balanced / Aggressive)
- Script tags: added `<script src="/static/js/clip-steering.js"></script>` after batch-queue.js

### `backend/static/css/app.css`
- Added `.clipCardSteerRow`, `.clipCardBtnKeep`, `.clipCardBtnAvoid` styles

---

## What Was Intentionally NOT Changed

| Not Changed | Reason |
|---|---|
| `score_segments()` internals | Structure bias applies after scoring, before sort |
| Subtitle rendering engine | Only `sub_font_size` adjusted; all existing paths unchanged |
| Cancel / retry / resume flow | Untouched |
| Batch queue job lifecycle | Steering fields added to payload only |
| Any ML / ranking model | No model involved; multipliers are deterministic heuristics |
| DNA / platform bias logic | Steering sits above DNA in hierarchy but doesn't touch DNA code |

---

## Observability Events

| Event | When | Level |
|---|---|---|
| `clip_excluded` | clip_exclude filtering removes ≥1 segment | INFO |
| `clip_locked` | clip_lock promotes ≥1 segment to front | INFO |

---

## Manual QA Checklist

### A — Structure bias: More Hook
- [ ] Set Structure pill to "More Hook"
- [ ] Render: hook-forward clips should rank higher vs Balanced
- [ ] Log: structure_bias=hook visible (add log if needed)

### B — Structure bias: More Story
- [ ] Set Structure pill to "More Story"
- [ ] Render: longer narrative clips should rank slightly higher

### C — Balanced (default)
- [ ] Default pill is "Balanced" (active on open)
- [ ] Render results identical to pre-UP26 (multipliers = 1.0)

### D — Subtitle emphasis: Subtle
- [ ] Set Subtitle Size to "Subtle"
- [ ] Output clips: font visibly smaller than Balanced

### E — Subtitle emphasis: Aggressive
- [ ] Set Subtitle Size to "Aggressive"
- [ ] Output clips: font visibly larger; capped at 120px

### F — Clip Keep
- [ ] Render a video; click "✓ Keep" on a clip card
- [ ] Toast appears: "Clip marked as Keep"
- [ ] Re-render: that timestamp range promoted to index 0 in clip pool

### G — Clip Avoid
- [ ] Click "✕ Avoid" on a clip card
- [ ] Toast appears: "Clip marked as Avoid"
- [ ] Re-render: that timestamp range absent from output

### H — Batch inherits steering
- [ ] Add files to Batch Queue while Structure = "More Hook"
- [ ] Rendered batch clips should reflect hook bias

### I — TTL / persistence
- [ ] Keep/Avoid decisions survive page reload (< 72h)
- [ ] `ClipSteering.clear()` in console removes them

### J — No regression: normal render unaffected
- [ ] Balanced structure, balanced subtitle, no Keep/Avoid → identical output to pre-UP26

### K — Hierarchy respected
- [ ] clip_lock always wins over structure bias (locked clip appears first regardless of bias)
- [ ] clip_exclude always wins (excluded clip never appears regardless of bias)
