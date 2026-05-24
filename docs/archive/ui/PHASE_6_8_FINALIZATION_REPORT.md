# Phase 6.8 — Final Product Hardening + Optional Editing Operations

**Status**: COMPLETE  
**Date**: 2026-05-23  
**Branch**: `restructure/output-timeline-architecture`  
**Prerequisite**: Phase 6.7 (Electron cut-over + static-v2 activation)

---

## Declaration

> **Phase 6 is COMPLETE.**

The React v2 frontend is production-built, activated, Electron-ready, and all editing operations are fully wired end-to-end. Architecture is frozen.

---

## 1. Apply Trim Flow

**Endpoint**: `POST /api/jobs/{job_id}/parts/{part_no}/trim`

```json
Request:  { "start_sec": 5.0, "end_sec": 20.0, "output_mode": "new_job" }
Response: { "status": "ok", "job_id": "...", "part_no": 1,
            "output_file": "...trimmed/part1_trim_5.0_20.0.mp4",
            "duration_sec": 15.0, "trim_start_sec": 5.0, "trim_end_sec": 20.0 }
```

**Implementation**:
- Source path resolved from DB (`job_id` + `part_no`) — never from client input
- `probe_video_metadata()` determines actual duration before clamping
- `cut_video()` (existing `clip_ops.py`) performs stream-copy with accurate-cut fallback
- Output stored under `<source_dir>/trimmed/` — original file never mutated
- Minimum trim: 1.0s; both bounds clamped to `[0, duration]`
- `output_mode="new_job"` is the default and only safe mode

**Frontend**: "Apply Trim" button in `EditorMetadataPanel` — enabled only when `trimDuration >= 1s AND trimDuration < durationSec`. Shows loading state during request. Displays success notification with output duration.

---

## 2. Re-render Selection Flow

**Endpoint**: `POST /api/jobs/{job_id}/parts/{part_no}/rerender`

```json
Request:  { "start_sec": 5.0, "end_sec": 20.0,
            "effect_preset": "cinematic",   // optional
            "subtitle_style": "tiktok_bounce_v1" }  // optional
Response: { "status": "queued", "new_job_id": "rerender_..._abc12345",
            "parent_job_id": "...", "parent_part_no": 1,
            "trim_start_sec": 5.0, "trim_end_sec": 20.0 }
```

**Implementation**:
- Generates new `job_id` with `rerender_{parent[:20]}_{uuid[:8]}` format
- Inherits original payload, overrides `source_video_path`, `trim_start_sec`, `trim_end_sec`
- Strips `youtube_url`/`urls` (local-only re-render)
- Stores `parent_job_id` + `parent_part_no` in payload for lineage tracking
- Enqueues via `job_manager.submit_job()` — returns immediately (async processing)
- If enqueue fails (e.g. engine import error), job stays in DB as "queued" and recovers on restart

**Frontend**: "Re-render Selection" button — enabled same conditions as Apply Trim. On success, redirects to History panel so user can watch new job progress.

---

## 3. Export Clip Flow

**Endpoint**: `POST /api/jobs/{job_id}/parts/{part_no}/export`

```json
Request:  { "destination_dir": "/home/user/exports" }
Response: { "status": "ok", "job_id": "...", "part_no": 1,
            "source_file": "part1.mp4",
            "exported_to": "/home/user/exports/part1.mp4",
            "destination_dir": "/home/user/exports" }
```

**Implementation**:
- `destination_dir` must be absolute and within safe roots (`home`, `CHANNELS_DIR`, `TEMP_DIR`)
- Path traversal blocked: resolved path checked with `is_relative_to()`
- Filename derived from source only — no user-supplied filenames
- Creates destination directory if safe; avoids overwrite with UUID suffix
- Uses `shutil.copy2()` (preserves timestamps)

**Frontend**: Export dir text input + "Export Clip" button. Button disabled when input is empty or whitespace-only. On success, shows notification with destination path. Does not navigate away (unlike Re-render).

---

## 4. CSP Hardening

**Applied to**: `GET /` and `GET /index.html` only when `STATIC_UI_VERSION=v2`

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:;
  media-src 'self' blob:;
  connect-src 'self' ws://127.0.0.1:8000 ws://localhost:8000;
  font-src 'self' data:;
  frame-ancestors 'none';
```

Additional headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`

**Why these choices**:
- `'unsafe-inline'` in `style-src` — React inline styles require it; cannot use nonces in static builds
- `ws://` explicit origins — Electron same-origin WebSocket requires explicit ws:// (not wss://)
- `blob:` in `media-src` — video player may use Blob URLs for range-request streaming
- `data:` in `font-src` — CSS custom properties may include data-URI fonts
- Legacy UI (`static/`) not affected — CSP only applies when `_UI_VERSION == "v2"`
- API routes not affected — middleware only injects on UI path matches

---

## 5. TypeScript Cleanup

**Before**: 16 `tsc -b` errors across 4 files  
**After**: 0 errors

| File | Issue | Fix |
|---|---|---|
| `vite.config.ts` | `test` key unknown on `UserConfigExport` | Changed `defineConfig` import to `vitest/config` |
| `tests/api.test.ts` | `fs`, `path`, `__dirname` not found | Added `@types/node` + `"types": ["node"]` to tsconfig.app.json |
| `tests/electron-cutover-readiness.test.ts` | Same Node.js globals | Same fix |
| `tests/static-readiness.test.ts` | Same Node.js globals | Same fix |
| `tests/navigation-polish.test.tsx` | `within` unused | Removed unused import |
| `tsconfig.app.json` | `baseUrl` deprecation warning | Added `"ignoreDeprecations": "5.0"` |

---

## 6. Final Electron Readiness

| Check | Status |
|---|---|
| `STATIC_UI_VERSION=v2` activates correct static dir | ✓ Confirmed (ui_gate.py) |
| Same-origin API calls work (`BASE_URL=''`) | ✓ Confirmed (vite proxy in dev, same-origin in prod) |
| WebSocket URL resolves correctly when `BASE_URL=''` | ✓ `computeWsBase()` uses `window.location.origin` |
| `backend/static-v2/` committed + current | ✓ Updated to Phase 6.8 build |
| Launch scripts: `run-desktop-v2.ps1`, `run-backend-v2.ps1` | ✓ Unchanged from Phase 6.7 |
| Electron env passthrough (`...process.env`) | ✓ No main.js changes needed |

---

## 7. Rollback Verification

To roll back to legacy UI: unset `STATIC_UI_VERSION` or set to `legacy`.  
`ui_gate.py` falls back gracefully to `backend/static/` without raising.  
All API endpoints are unchanged — rollback is transparent to the backend.

---

## 8. Test Summary

### Frontend
| Suite | Tests |
|---|---|
| editor-operations.test.tsx | 12 |
| trim-flow.test.tsx | 9 |
| export-flow.test.tsx | 7 |
| **Total new** | **28** |
| **Total all** | **426 / 426** |

### Backend
| Suite | Tests |
|---|---|
| test_trim_api.py | 13 |
| test_rerender_selection_api.py | 8 |
| test_export_clip_api.py | 7 |
| test_csp_headers.py | 8 |
| **Total new** | **37 / 37** |
| **Total all** | **7385 pass, 8 pre-existing failures** |

`tsc -b`: **0 errors**  
`vite build`: **success** (231.84 kB JS, 12.08 kB CSS)

---

## 9. Remaining Known Limitations

| Item | Status | Notes |
|---|---|---|
| Re-render uses full render pipeline | By design | Segment-specific re-render would require deeper pipeline integration (Phase 7 scope) |
| Export: no Electron file-picker bridge | Deferred | Manual path input works. Electron `dialog.showOpenDialog` bridge is Phase 7 scope |
| Apply Trim produces standalone file, not job | By design | Trim is a fast FFmpeg operation; creating a full job record would add overhead |
| CSP `style-src 'unsafe-inline'` | Necessary | React inline styles cannot be nonce'd in static builds; acceptable for local app |
| 8 pre-existing backend test failures | Pre-existing | remotion_adapter ×4, ai_optional_dependencies ×1, ai_phase36 ×2, ai_visibility ×1 — not introduced in Phase 6 |
| `test_quality_api_contract.py`, `test_ui_backend_contract.py`, `test_ui_static_v2_gate.py::TestHealthEndpoint` | Pre-existing | Use `from backend.app.main import app` — only work from project root, not `backend/` dir |

---

## 10. Architecture Freeze

Phase 6 is complete. The following are frozen:

- **Backend API contract** — as documented in `docs/ui/UI_BACKEND_CONTRACT.md`
- **Frontend architecture** — Zustand stores, React component tree, API layer, WebSocket transport
- **Electron integration** — `STATIC_UI_VERSION` env var, `ui_gate.py`, `main.py` static mount
- **Build artifact location** — `backend/static-v2/` is the released build, tracked in git

---

## 11. Recommended Next Steps

**Option A — Claude Agent Teams migration**  
Migrate AI orchestration to multi-agent architecture for parallel clip analysis.

**Option B — Phase 7 Filter Intelligence expansion**  
Add real-time preview filters, timeline scrubbing, waveform visualization, Electron file-picker bridge.

---

## Phase 6 Complete Checklist

- [x] Phase 6.0 — UI Foundation Architecture
- [x] Phase 6.1 — Render Setup Screen
- [x] Phase 6.2 — History Screen + Job Actions
- [x] Phase 6.3 — Quality Panel
- [x] Phase 6.4 — Live Job Progress Panel
- [x] Phase 6.5 — Editor Screen
- [x] Phase 6.6 — Frontend Integration Polish
- [x] Phase 6.7 — Electron Cut-over
- [x] Phase 6.8 — Final Product Hardening + Optional Editing Operations

**Phase 6: COMPLETE**
