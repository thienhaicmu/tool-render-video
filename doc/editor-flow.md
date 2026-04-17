# Editor Flow — Technical Reference

This document describes the full editor → render workflow as implemented.
For a high-level overview see [README.md](../README.md#editor-workflow).

---

## Overview

The editor flow is a two-phase workflow:

1. **Prepare** — download or validate the source video; create a session with a browser-playable preview
2. **Render** — the user configures the job in the editor UI, then submits; the pipeline reuses the prepared source

The key property: **the source video is downloaded exactly once** (during prepare). The render job reuses it via `edit_session_id`. If the session is gone when render starts, the job fails with a clear error — it never re-downloads silently.

---

## Phase 1: Prepare Source

### Endpoint

```
POST /api/render/prepare-source
Content-Type: application/json

{
  "source_mode": "youtube" | "local",
  "youtube_url": "...",          // required when source_mode=youtube
  "source_video_path": "..."     // required when source_mode=local
}
```

### Backend steps

1. Generate `session_id = uuid4()`
2. Create `work_dir = data/temp/preview/{session_id}/`
3. **YouTube**: call `download_youtube(url, work_dir)` → source file in `work_dir`
4. **Local**: validate file exists on disk → use in-place (no copy)
5. Probe duration with ffprobe
6. Transcode to H.264 preview if source codec is not H.264:
   - Tries `h264_nvenc` first if GPU is available
   - Falls back to `libx264`
   - Timeout: `min(3600, 120 + 2 × duration_sec)` seconds
   - Returns original file unchanged if transcode fails
7. Call `_save_session(session_id, {...})`:
   - Writes to `_PREVIEW_SESSIONS` (in-memory dict, fast lookup)
   - Writes `work_dir/session.json` (disk fallback, survives server restart)
8. Return:
   ```json
   {
     "session_id": "...",
     "title": "...",
     "duration": 1234.5,
     "export_dir": "data/temp/preview/{session_id}/exports"
   }
   ```

### Preview endpoint

The browser streams the H.264 preview from:
```
GET /api/render/preview-video/{session_id}
```
Returns the `preview_path` (transcoded H.264) if it exists, else `video_path` (original).
Supports HTTP range requests for seek-while-loading.

---

## Phase 2: Editor UI

### Frontend state (`_ev` object)

| Field | Set by | Value |
|---|---|---|
| `sessionId` | `openEditorView_withSession` or `openEditorView` | `pd.session_id` |
| `exportDir` | same | `pd.export_dir` |
| `duration` | same | `pd.duration` |
| `pendingPayload` | `prepareAndOpenEditor` | base payload from main form |

### Entry points

**YouTube path** (`prepareAndOpenEditor`):
1. Calls `POST /api/render/prepare-source` (YouTube)
2. On success: `openEditorView_withSession(pd, url, payload)` — sets `_ev.sessionId`, `_ev.exportDir`

**Local file path** (`prepareAndOpenEditor`):
1. Calls `openEditorView(sourceMode, path, payload)` — async
2. `openEditorView` internally calls `POST /api/render/prepare-source` (local)
3. On success: sets `_ev.sessionId`, `_ev.exportDir`

### What the editor sets

Before submitting, `startRenderFromEditor()` overwrites these payload fields:

| Field | Value |
|---|---|
| `edit_session_id` | `_ev.sessionId` |
| `edit_trim_in` | trim in seconds (0 = none) |
| `edit_trim_out` | trim out seconds (0 = none) |
| `edit_volume` | 0.0–2.0 (1.0 = original) |
| `sub_font`, `sub_font_size`, `sub_color`, `sub_highlight`, `sub_outline`, `sub_margin_v` | from subtitle controls |
| `subtitle_style` | `'pro_karaoke'` |
| `subtitle_only_viral_high` | `false` (all parts get subtitles in editor mode) |
| `text_layers` | normalized array (see below) |
| `aspect_ratio`, `playback_speed`, `min_part_sec`, `max_part_sec`, `output_fps`, etc. | from render controls |
| `encoder_mode` | from device selector |
| `output_mode` | `'manual'` (always) |
| `channel_code` | `''` (always cleared) |
| `render_output_subdir` | `''` (always cleared) |
| `output_dir` | see Output Dir section |

### Output Dir Resolution

```
raw = payload.output_dir (from original payload, backslashes normalized to /)

if raw is empty:
    raw = _ev.exportDir   (= data/temp/preview/{session_id}/exports)

if raw is still empty:
    → show error in evStatusLine, abort, re-enable start button

leaf = last path segment of raw
if leaf not in ['video_output', 'video_out']:
    raw = raw + '/video_output'

payload.output_dir = raw
```

This ensures `output_dir` always ends in `video_output` or `video_out`, which is required by `_validate_output_dir` on the backend.

### text_layers Normalization

Before the layer array is assigned to `payload.text_layers`, each layer passes through three normalizers:

```javascript
const _toOutline = (v) =>
  (v && typeof v === 'object') ? v :
  { enabled: false, thickness: typeof v === 'number' ? Math.max(0, Math.min(8, v)) : 2 };

const _toShadow = (v) =>
  (v && typeof v === 'object') ? v :
  { enabled: false, offset_x: 2, offset_y: 2 };

const _toBg = (v) =>
  (v && typeof v === 'object') ? v :
  { enabled: false, color: '#00000099', padding: 10 };
```

These convert any legacy flat values to the object shape required by `TextLayerOutline`, `TextLayerShadow`, and `TextLayerBackground` in `schemas.py`. They run on the frontend before submission, so Pydantic never receives flat values.

### Font Alignment

`evTxtFont` (text layer font selector) and `evSubFont` (subtitle font selector) use the same 12-font list:
Bungee, Anton, Bebas Neue, Oswald, Impact, Arial Black, Segoe UI Black, Archivo Black, Teko, Luckiest Guy, Montserrat, Roboto.

All 12 are in `VALID_FONTS` in `services/text_overlay.py` (which has 14 entries including Arial and Segoe UI for programmatic use).

### Error Handling in UI

`_submitRenderPayload` returns `{ ok: bool, error: string | null }`.

`startRenderFromEditor` on the result:
- **Success (`ok: true`)** — stops video playback, clears `evVideo`, calls `setView('render')`
- **Failure (`ok: false`)** — re-enables `evStartBtn`, shows error message in `evStatusLine` (red), editor stays open for retry

---

## Phase 3: Render Pipeline (Session Reuse)

### Validation (`_validate_render_source`)

When `edit_session_id` is non-empty in the payload:
- Validates `output_mode` is `"channel"` or `"manual"`
- Validates `output_dir` leaf name only
- **Skips** `source_mode` / `youtube_url` / `source_video_path` validation entirely

This allows the editor flow to submit without a valid `youtube_url` in the payload (the URL is still present from the original form, but not required).

### Pipeline (session branch)

```python
edit_session_id = payload.edit_session_id.strip()
sess = load_session_fn(edit_session_id) if edit_session_id else None

if edit_session_id and not sess:
    raise RuntimeError(
        f"Editor session '{edit_session_id}' not found — "
        "the session may have expired or the server was restarted. "
        "Please re-open the editor to re-prepare the source."
    )

if sess:
    source_path = Path(sess["video_path"])
    if not source_path.exists():
        raise RuntimeError(f"Editor session video not found: {source_path}")
    source = {
        "title": sess.get("title", source_path.stem),
        "slug": slugify(...),
        "duration": sess.get("duration") or probe_duration(source_path),
        "filepath": str(source_path),
    }
    # pipeline continues with this source — no download
```

After the render completes, `cleanup_session_fn(edit_session_id)` removes the session from memory and deletes `data/temp/preview/{session_id}/`.

---

## Session Lookup (`_load_session`)

```python
def _load_session(session_id: str) -> dict | None:
    # Fast path: in-memory
    if session_id in _PREVIEW_SESSIONS:
        return _PREVIEW_SESSIONS[session_id]
    # Disk fallback: survives server restart
    meta_path = PREVIEW_DIR / session_id / "session.json"
    if meta_path.exists():
        data = json.loads(meta_path.read_text())
        if Path(data.get("video_path", "")).exists():
            _PREVIEW_SESSIONS[session_id] = data   # re-warm cache
            return data
    return None
```

The disk fallback means a session survives a server restart as long as `session.json` and `video_path` still exist on disk.

---

## Session Expiry

Sessions are cleaned up in two ways:

1. **Explicit cleanup**: `_cleanup_preview_session(session_id)` is called at the end of `run_render_pipeline` after the render completes (or fails after using the session source).

2. **Startup pruning**: `prune_preview_dirs(TEMP_DIR, max_age_hours=6)` runs on every server startup and removes any `data/temp/preview/` subdirectory older than 6 hours.

If a session is cleaned up before the user submits the render:
- The pipeline raises `RuntimeError` immediately
- The job is marked `failed`
- The error message tells the user to re-open the editor
- No re-download occurs

---

## Sequence Diagram

```
Browser                  routes/render.py           orchestration/render_pipeline.py
   │                           │                               │
   │  POST /prepare-source     │                               │
   │──────────────────────────►│                               │
   │                           │ download/validate             │
   │                           │ _save_session(id, data)       │
   │  {session_id, export_dir} │                               │
   │◄──────────────────────────│                               │
   │                           │                               │
   │  [user configures editor] │                               │
   │                           │                               │
   │  POST /process            │                               │
   │  {edit_session_id: id, …} │                               │
   │──────────────────────────►│                               │
   │                           │ _validate_render_source       │
   │                           │ (output_dir only)             │
   │                           │ upsert_job(queued)            │
   │                           │ submit_job → process_render   │
   │  {job_id}                 │                               │
   │◄──────────────────────────│                               │
   │                           │                               │
   │                           │──── run_render_pipeline ─────►│
   │                           │     load_session_fn(id)       │
   │                           │                               │ load from _PREVIEW_SESSIONS
   │                           │                               │ or session.json fallback
   │                           │                               │
   │                           │                               │ source = sess["video_path"]
   │                           │                               │ [scene detect → segments → render]
   │                           │                               │ cleanup_session_fn(id)
   │                           │                               │ upsert_job(done)
```
