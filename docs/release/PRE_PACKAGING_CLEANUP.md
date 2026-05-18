# Pre-Packaging Cleanup

**Branch**: `feature/ai-output-upgrade`  
**Date**: 2026-05-18  
**Target**: PACKAGING-RC  
**Rule**: No behavior changes. If behavior changes, stop.

---

## SAFE_DELETE

Files deleted in this pass. All confirmed with reference search before removal.

| File | Size | Reason |
|---|---|---|
| `backend/static/index.html.v2.bak` | 94 KB | Explicitly marked for removal in `UI_ARCHITECTURE.md` after "one release cycle of stable production." DOM IDs in this file (`editorStatusLine`, `editorOrigDur`) no longer exist in live `index.html`. |
| `backend/static/css/app.css.v2.bak` | 517 KB | Same explicit marker in `UI_ARCHITECTURE.md`. Pre-v3 CSS backup. Not loaded, not referenced in any active HTML. |
| `backend/static-v3/` (dir, 26 files) | 1.04 MB | Orphan build. `ui_gate.py` only knows `v2` and `legacy` — v3 directory is never mounted, never referenced in any Python, PowerShell, BAT, or JS file. Not in any `extraResources` filter. Bundled into Electron package as dead weight. |
| `backend/static-v4/` (dir, 26 files) | 0.85 MB | Same as static-v3. |
| `backend/static/js/editor-modal.js` | 10 KB | Orphan legacy module. Not in any `<script src>` tag in `index.html`. No references in any other JS file. All DOM IDs it targets (`editorStatusLine`, `editorOrigDur`, `editorDurBadge`, `editorVideo`, `editorVideoOverlay`) are absent from current `index.html` and all partials. Contains Vietnamese placeholder text from a pre-v3 prototype iteration. |

**Total reclaimed from package**: ~2.46 MB

---

## SAFE_REFACTOR

### Documentation accuracy fix — AGENTS.md

`AGENTS.md` lines 133 and 169 referenced `backend/static/css/app.css` as the active stylesheet. This was correct when written but became stale after the v3 CSS migration. The active entry point is now `backend/static/css/v3/app.css`.

**Change**: Updated both lines to reference the v3 modular CSS system. No behavior change — documentation only.

---

## RISKY_KEEP

Files not deleted. Kept with notes.

| File | Size | Reason kept |
|---|---|---|
| `backend/static/css/app.css` | 527 KB | Documented rollback option in `UI_ARCHITECTURE.md` ("Rollback: `index.html` CSS link → `/static/css/app.css`"). Not loaded by default. Removable after one full release cycle of stable production with v3 CSS. Also incorrectly referenced in `AGENTS.md` (now corrected). |
| `backend/static-v2/` | ~2 MB | Referenced by `ui_gate.py` and `tests/test_ui_gate.py`. Served when `STATIC_UI_VERSION=v2` env var is set. Not dead — it's an intentional alternate UI gate. |
| `tmp_verify_output/` | — | Protected by `AGENTS.md`: "Do not edit `tmp_verify_output/`." |
| `tmp_verify_server.log` | 13 KB | Temp log. Not referenced anywhere. Kept because it's tracked in git and not causing harm. Safe to remove manually if desired. |
| `doc/` directory | — | Separate from `docs/`, contains engineering workflow docs. Referenced by `cowork/README.md`. Not deleted per docs preservation rule. |

---

## DEAD_CSS

| File | Status | Notes |
|---|---|---|
| `backend/static/css/app.css` | Dead (not loaded) | 527 KB monolithic stylesheet. `index.html` loads `css/v3/app.css` instead. None of its rules are applied in any browser session. Retained as rollback option per `UI_ARCHITECTURE.md`. |
| `backend/static/css/v3/*.css` | Active | All 9 v3 CSS files are loaded via `@import` from `v3/app.css`. No orphan selectors detected between files. `hardening.css` contains intentional override rules (phase hotfixes); these are not duplicates — they fix specific layout regressions with documented reasons. |

**Finding**: Within the v3 system, `display: none !important` appears 14 times across 4 files. All occurrences are purposeful view-state guards or media query rules — none are duplicates of each other.

---

## DUPLICATE_LOGIC

### `_sanitize_speed()` defined in two service files

**Files**: `backend/app/services/render_engine.py:429` and `backend/app/services/motion_crop.py:381`

**Code** (identical in both):
```python
def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))
```

**Why not merged now**: `render_engine.py` imports from `motion_crop.py` at module level. `motion_crop.py` already uses deferred (lazy) imports inside functions to break the circular dependency. Moving `_sanitize_speed` to a shared module would require a third file or careful import ordering. Risk of introducing an import cycle outweighs the benefit of eliminating one duplicate function at this stage.

**Recommendation**: After packaging stabilizes, extract to `backend/app/core/media_utils.py` and import from both.

### Remaining inline speed-clamp patterns

`render_pipeline.py:3954` and `render_pipeline.py:4092` each contain inline `max(0.5, min(1.5, ...))` patterns that differ from `_get_effective_playback_speed()` in intentional ways:
- Line 3954: uses `or 1.07` default (not 1.0) and deliberately excludes platform delta (hook overlay duration should not vary by platform)
- Line 4092: `seg.get("variant_playback_speed") or max(...)` — first checks segment-level override, then falls back to payload+delta; uses `or 1.07` default

These are NOT consolidation candidates — the differences are load-bearing.

---

## SMOKE_RESULTS

Smoke test method: static analysis of all call sites and load paths. No runtime execution available in this environment.

| Flow | Status | Notes |
|---|---|---|
| Import (file picker → editor) | PASS | `index.html` script list unchanged. All 50 active JS modules still present. |
| Render (editor → pipeline) | PASS | `render_pipeline.py`, `render_engine.py`, and all imported modules unchanged. |
| Review (review queue) | PASS | `review-queue.js` unchanged. Review view partial unchanged. |
| Rerender (steering → rerender) | PASS | `editor-view.js`, `clip-steering.js` unchanged. `v3TriggerRerender()` path intact. |
| Retry | PASS | `_retryInFlight` guard in `review-queue.js` unchanged. |
| Open folder | PASS | `openStoredOutputPath` call in `review-queue.js` unchanged. |
| UI gate (v2 alt UI) | PASS | `ui_gate.py` and `test_ui_gate.py` unchanged. `static-v2/` preserved. |
| CSS render | PASS | `index.html` loads `css/v3/app.css`. All 9 v3 modules intact. No changes to v3 CSS files. |
| Package build | PASS (static) | `build-offline-exe.ps1` and `desktop-shell/package.json` unchanged. `extraResources` filter excludes `.venv`, `__pycache__`, `.pytest_cache`, `*.pyc`. Deleted files (static-v3, static-v4, .bak, editor-modal.js) were dead weight that bundled silently — their absence reduces package size by ~2.46 MB with no runtime impact. |

---

## Summary

| Category | Count | Δ Size |
|---|---|---|
| Files deleted | 5 items (2 files + 2 dirs + 1 JS file) | −2.46 MB from package |
| Files refactored | 1 (AGENTS.md — docs accuracy) | — |
| Files marked risky-keep | 5 | — |
| Duplicate logic documented | 1 function pair | — |
| Behavior changes | 0 | — |
