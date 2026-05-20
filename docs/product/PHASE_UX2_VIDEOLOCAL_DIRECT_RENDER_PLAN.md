# PHASE UX-2 — VideoLocal Direct Render Plan
## Remove Source Duplication

**Date:** 2026-05-20  
**Scope:** Backend + render pipeline simplification only. No UI redesign.  
**Source of truth:** Live code trace — all file references verified.

---

## AUDIT SUMMARY (Read This First)

**The critical finding:** For Electron desktop app local video, the render pipeline already uses the original file path directly. There is NO source copy for render. However, two real duplication issues exist:

1. `_ensure_h264_preview()` creates a transcoded H.264 copy in TEMP_DIR during editor open — needed for Chromium playback, but unnecessary for H.264-native files.
2. `keep_source_copy: true` hardcoded in `render-engine.js:75` causes every YouTube download to be **moved/copied from TEMP to `/upload/source/`** after render — persistent disk usage that accumulates.

---

## SECTION 1 — CURRENT FLOW AUDIT

### 1.1 Local Video Path (Electron Desktop App)

```
[1] User clicks file picker
    backend/static/index.html
    → <input id="local_video_file_picker" type="file" accept="video/*">
    → <button onclick="browseLocalVideo()">

[2] File picker event fires
    backend/static/js/render-config.js:8 — onLocalVideoPicked(ev)
    → file.path (Electron native OS path, e.g. C:\Videos\clip.mp4)
    → selectedLocalVideoPath = realPath           (render-config.js:25)
    → source_video_path DOM field = realPath      (render-config.js:27)
    → _pendingLocalFile = null                    (no upload queued)

[3] User clicks "Open in Editor"
    backend/static/js/render-engine.js:159-161
    → sourceMode === 'local' branch
    → openEditorView('local', localVideoPath, payload)
    → NO /api/render/prepare-source call here (that is YouTube-only pre-download)

[4] Editor opens, calls prepare-source for local
    backend/static/js/editor-view.js:1184-1188
    → POST /api/render/prepare-source
       body: { source_mode: 'local', source_video_path: 'C:\Videos\clip.mp4' }

[5] Backend prepare-source — local branch
    backend/app/routes/render.py:392-433
    → validates file exists                       (render.py:393-395)
    → _probe_video_duration(src)                  (render.py:414)
    → _ensure_h264_preview(src, work_dir)         (render.py:415)  ← COPY RISK
    → _save_session(session_id, {
           video_path: 'C:\Videos\clip.mp4',      ← ORIGINAL path
           preview_path: TEMP_DIR/preview/{sid}/preview_h264.mp4,
           source_mode: 'local'
       })
    → returns { session_id, duration, title }

[6] Editor stores session_id
    editor-view.js:1191, 1198
    → _ev.sessionId = pd.session_id
    → pendingPayload.edit_session_id = pd.session_id

[7] Video preview served via transcoded file
    editor-view.js:1204
    → GET /api/render/preview-video/{session_id}
    → serves preview_h264.mp4 (or original if already H.264)

[8] User starts render
    render-engine.js → startRenderFromEditor() → submit payload
    payload.edit_session_id = session_id
    payload.source_video_path = 'C:\Videos\clip.mp4'

[9] Render pipeline resolves source path
    backend/app/orchestration/render_pipeline.py:1963-1990
    → sess = load_session_fn(edit_session_id)
    → source_path = Path(sess["video_path"])   ← ORIGINAL path, not preview
    → source_path = 'C:\Videos\clip.mp4'       ← unchanged from user selection

[10] keep_source_copy check
    render_pipeline.py:2148-2171
    → payload.keep_source_copy = True (hardcoded in render-engine.js:75)
    → is_temp_source = str(source_path).startswith(str(TEMP_DIR))  ← FALSE
    → log: "local_source.passthrough path=C:\Videos\clip.mp4 (source copy skipped)"
    → NO COPY MADE

[11] Render executes on original file
    → All ffmpeg operations use source_path = 'C:\Videos\clip.mp4'
    → Scene detection, transcription, part rendering: all use original
```

**Verdict: Render itself has zero source duplication for local video.**

### 1.2 The H.264 Preview Copy (`_ensure_h264_preview`)

```
backend/app/routes/render.py:289-341

_ensure_h264_preview(src, work_dir, duration_sec):
  out = TEMP_DIR/preview/{session_id}/preview_h264.mp4

  if out.exists() and out.stat().st_size > 0:
      return out                           ← CACHED, no re-transcode

  if _is_browser_safe_preview(src):
      return src                           ← H.264 MP4: NO COPY, returns original

  # Source is HEVC, AV1, or unsupported codec:
  ffmpeg -i src -c:v libx264 -crf 28 ... preview_h264.mp4
  return out                               ← TRANSCODED COPY in TEMP_DIR
```

- **H.264 MP4 (most local videos):** returns `src` unchanged — **zero copy**
- **HEVC/AV1/other:** creates `preview_h264.mp4` in TEMP_DIR — copy is created, but:
  - Required for Chromium editor playback
  - Located in TEMP_DIR (separate from user's files)
  - NOT used for render (render uses original)
  - Cleaned up when session/job completes

### 1.3 YouTube Source Copy (Real Problem)

```
[A] YouTube download
    render-engine.js:125-131
    → POST /api/render/prepare-source { source_mode: 'youtube', youtube_url: ... }
    → backend downloads to TEMP_DIR/preview/{session_id}/video.mp4

[B] Render payload has keep_source_copy: true
    render-engine.js:75
    → hardcoded in default payload object

[C] Render pipeline keep_source_copy check
    render_pipeline.py:2148-2171
    → keep_source_copy = True
    → is_temp_source = True  (source IS in TEMP_DIR)
    → _reserve_source_path_in_dir(keep_source_dir, slug, ext)
    → shutil.move(temp_path, upload/source/slug.mp4)   ← PERSISTENT COPY
    → source_path = upload/source/slug.mp4             ← now points to copy

[D] Render runs on the moved copy
    → {channel}/upload/source/slug.mp4 persists after render
    → Accumulates over time — one file per YouTube render
```

**Verdict: YouTube source copy IS the real problem.** `keep_source_copy: true` causes every YouTube download to persist indefinitely in `/upload/source/`.

### 1.4 Browser Fallback Upload (Not Electron Issue)

```
render-config.js:96-119 — uploadLocalFileIfNeeded()
  → Only called if _pendingLocalFile != null
  → _pendingLocalFile is set ONLY when file.path is empty (browser, not Electron)
  → In Electron: file.path always exists → _pendingLocalFile = null → upload skipped

POST /api/render/upload-local
  → render.py:807-834
  → Saves to {channel}/upload/source/{slugified-name}.mp4
  → Returns path to the copy
  → Only reached in browser environment — NOT Electron desktop app
```

**Verdict: Browser upload endpoint creates a copy, but is never triggered in Electron.**

---

## SECTION 2 — SOURCE COPY DEPENDENCY AUDIT

### What currently assumes `/upload/source/` exists?

| File | Location | Assumption | Used When |
|---|---|---|---|
| `render.py` | line 817 | Creates `{channel}/upload/source/` | Browser file upload (non-Electron) |
| `render.py` | line 1423-1424 | `_reserve_source_path()` creates `/upload/source/` | YouTube `keep_source_copy=True` |
| `render_pipeline.py` | line 2150-2154 | `keep_source_dir = output_dir / "source"` | YouTube `keep_source_copy=True` |
| `render_pipeline.py` | line 2159 | `_reserve_source_path_in_dir(keep_source_dir, ...)` | YouTube `keep_source_copy=True` |
| `render_pipeline.py` | line 2163-2167 | `shutil.move` / `shutil.copy2` | YouTube source persistence |

### What does NOT depend on `/upload/source/`:
- Scene detection: uses `source_path` (original or TEMP for YouTube)
- Transcription: uses `source_path`
- Thumbnail extraction: uses rendered output parts, not source
- Waveform: uses source_path
- Subtitle generation: uses SRT from transcription, not source path
- Review Queue: reads `source_video_path` from stored payload (original path)
- Rerender/resume: uses stored `video_path` from session (original path)
- Cache keys: keyed by `source_path + mtime + size` (original file)

**Conclusion:** `/upload/source/` is only needed for two cases: YouTube source persistence and browser-mode upload. Local Electron render has zero dependency on it.

---

## SECTION 3 — DIRECT PATH FEASIBILITY

### For local video (Electron): Already direct. Risk table is moot.

The render pipeline already operates on the original file path. The risks below apply to confirming this stays true:

| Scenario | Risk | Current Behavior | Status |
|---|---|---|---|
| Windows path with spaces | Medium | `Path().resolve()` handles correctly | OK |
| Unicode filename | Medium | Python pathlib handles UTF-8 paths | OK |
| Path with special chars (`[`, `]`, `&`) | High | ffmpeg needs quoted args — already done via list args, not shell | OK |
| File locked by another process | Medium | ffmpeg opens read-only; most players don't exclusive-lock | OK |
| Network drive path | High | Latency spikes during read; no retry logic | RISK |
| File > 4GB | Low | Warning shown in UI; pipeline handles large files | OK |
| File moved during render | High | ffmpeg fails mid-render; no recovery | RISK (see Section 4) |
| Drive disconnects | High | ffmpeg fails; job marked failed | RISK (see Section 4) |

### For YouTube source persistence: Change is required.

Changing `keep_source_copy: false` means:
- YouTube source files are deleted after render (TEMP cleanup)
- Rerenders from YouTube require re-download
- Disk usage normalized — no accumulation in `/upload/source/`

---

## SECTION 4 — SAFETY DESIGN

### Local Video: File Deleted/Moved During Render

**Current behavior:** No detection. ffmpeg fails at the frame where the missing data would be read. Job marked `failed`. Partial output parts may exist.

**Required behavior:**
1. On render start: stat the file, store `{mtime, size, inode}` in job context
2. Every N seconds during long renders: re-stat, compare. If changed: emit warning event
3. On ffmpeg exit code != 0: check if source still exists. If missing: emit specific error "Source file was moved or deleted during render"
4. Cleanup partial outputs on detection

**Graceful error message (creator-safe):**
```
"Render stopped: the source video file was moved or deleted.
Path: C:\Videos\clip.mp4
Please re-open the editor and confirm the file is still accessible."
```

### Drive Disconnects

**Current behavior:** OS error propagates through ffmpeg stderr. Job marked `failed` with raw ffmpeg error.

**Required behavior:** Catch `FileNotFoundError` and `OSError` with errno 5/6/21 around ffmpeg invocation. Emit creator-safe error with reconnect suggestion.

### User Renames Source File

Same as "file deleted" — `Path.exists()` check at render start catches this immediately with a clear error before ffmpeg begins.

---

## SECTION 5 — PIPELINE PATCH PLAN

### PATCH 1 — Fix YouTube source persistence (P0)

**FILE:** `backend/static/js/render-engine.js`

**CURRENT (line 75):**
```javascript
keep_source_copy: true,
```

**FINAL:**
```javascript
keep_source_copy: false,
```

**Note:** `backend/app/models/schemas.py:122` already defaults `keep_source_copy: bool = False`. The JS payload builder at render-engine.js:75 hardcodes `true`, overriding the schema default. Patch 1 restores alignment with the schema intent.

**RISK:** Low  
**WHY:** Prevents YouTube temp downloads from persisting to `/upload/source/` after render completes. Rerenders of YouTube videos will re-download. This is acceptable — rerender is rare and YouTube sources change anyway.  
**REGRESSION:** Test rerender for YouTube jobs — confirm re-download works correctly.

---

### PATCH 2 — Source file pre-flight check (P1)

**FILE:** `backend/app/orchestration/render_pipeline.py`

**CURRENT:** No pre-render file validation for local sources.

**FINAL:** Add before ffmpeg execution:
```python
# render_pipeline.py — after source_path is resolved, before first ffmpeg call
if source_mode == "local":
    if not source_path.exists():
        raise RuntimeError(
            f"Source file not found. It may have been moved or deleted.\nPath: {source_path}"
        )
    _src_stat_at_start = source_path.stat()
```

**RISK:** Low  
**WHY:** Provides a clean, creator-safe error instead of raw ffmpeg stderr when source is missing at render start.

---

### PATCH 3 — Remove dead `_reserve_source_path` for local (P2, verify-only)

**FILE:** `backend/app/orchestration/render_pipeline.py`

**CURRENT (line 2148-2171):**
```python
if payload.keep_source_copy:
    ...
    is_temp_source = str(source_path).startswith(str(TEMP_DIR))
    if is_temp_source:
        # copy/move to /upload/source/
    else:
        # passthrough log — no copy
```

**FINAL:** With `keep_source_copy=False` from Patch 1, this block is never entered. No code change required — the `if payload.keep_source_copy:` guard prevents it.

**RISK:** None (dead path)  
**WHY:** Confirmed by log line 2171: "local_source.passthrough path=... (source copy skipped)".

---

### PATCH 4 — Old /upload/source/ cleanup endpoint (P2)

**FILE:** `backend/app/routes/render.py`

**FINAL:** Add admin endpoint:
```python
@router.delete("/cleanup-source-copies")
def cleanup_source_copies(channel_code: str = Query("T1")):
    """Remove accumulated YouTube source copies from /upload/source/."""
    source_dir = CHANNELS_DIR / channel_code / "upload" / "source"
    if source_dir.exists():
        files = list(source_dir.glob("*"))
        for f in files:
            f.unlink(missing_ok=True)
        return {"deleted": len(files), "dir": str(source_dir)}
    return {"deleted": 0, "dir": str(source_dir)}
```

**RISK:** Low (admin-only, non-destructive to render pipeline)

---

### PATCH 5 — Verify `_ensure_h264_preview` skips H.264 sources (confirm, no code change)

**FILE:** `backend/app/routes/render.py:300`

**CURRENT:**
```python
if _is_browser_safe_preview(src):
    return src  # original path, no copy
```

**FINAL:** Verify `_is_browser_safe_preview` correctly identifies H.264 MP4 as browser-safe. If it does, no copy is created for typical local videos. If HEVC/AV1 is common in the user base, consider adding a user-facing note.

**RISK:** None (existing logic, just needs verification)

---

## SECTION 6 — TEMP + CACHE STRATEGY

### Allowed directory structure post-UX-2:

```
{channel}/
  upload/
    source/          ← DEPRECATED for YouTube. Keep for browser-upload fallback only.
                       Will be empty after Patch 1 for typical Electron usage.
  render_output/     ← Final rendered parts (keep forever until user deletes)
    {job_id}/
      part_001.mp4
      part_002.mp4
      thumbnail.jpg

TEMP_DIR/
  preview/
    {session_id}/    ← Editor preview files. Auto-cleaned when session expires.
      preview_h264.mp4   (only if source wasn't H.264)
      exports/
  jobs/
    {job_id}/        ← Intermediate ffmpeg outputs. Cleaned on job completion.
      segments/
      clips/
      srt/

CACHE_DIR/
  scenes/            ← Scene detection cache. Keyed by file path+mtime+size.
  transcripts/       ← Whisper transcript cache. Same key strategy.
```

### What each stores:

| Folder | Contents | Lifetime | Cleanup trigger |
|---|---|---|---|
| `TEMP_DIR/preview/{sid}` | H.264 preview, exports | Session lifetime | Session DELETE or expiry |
| `TEMP_DIR/jobs/{job_id}` | Segment clips, temp SRT | Job lifetime | Job complete/fail |
| `CACHE_DIR/scenes` | Scene JSON | Until source file changes | Automatic (key includes mtime) |
| `CACHE_DIR/transcripts` | SRT files | Until source file changes | Automatic (key includes mtime) |
| `{channel}/upload/source` | Browser uploads, old YT copies | Manual | Patch 4 cleanup endpoint |
| `{channel}/render_output` | Final parts | User-controlled | Never auto-deleted |

---

## SECTION 7 — RERENDER SAFETY

### Will rerender work without source copy?

**For local video: YES, unchanged.**

Rerender path:
```
POST /api/render/resume/{job_id}
→ load job from DB
→ payload.source_video_path = 'C:\Videos\clip.mp4'   ← original path stored in DB
→ payload.edit_session_id = null (no session for resume)
→ render_pipeline.py:1992
   source_path = Path(payload.source_video_path).resolve()
→ checks source_path.exists()
→ if missing: RuntimeError "Local source video not found"
→ if present: renders directly from original
```

**For YouTube: Behavior changes with Patch 1.**

Before Patch 1: Rerender uses `{channel}/upload/source/slug.mp4` (the persistent copy)  
After Patch 1: `keep_source_copy=False` → temp file cleaned after render → rerender MUST re-download

**Action required:** After Patch 1, test YouTube rerender flow. The pipeline should detect missing temp source and re-download.

**Risk:** Medium. YouTube rerender currently relies on the persistent copy. After removing it, rerenders require internet access and YouTube availability.

---

## SECTION 8 — IMPLEMENTATION ORDER

### P0 — Confirm no regression (before any change)

1. Run a local video render end-to-end. Confirm job log shows "local_source.passthrough" (no copy).
2. Confirm `/upload/source/` is NOT written to during local render.
3. Confirm `CACHE_DIR/scenes` and `CACHE_DIR/transcripts` use original path as cache key.
4. Confirm rerender of a local video job works without touching `/upload/source/`.

### P1 — Direct render support (safe, additive)

1. **Patch 2:** Add source file pre-flight check. Tests: render with missing file → clear error.
2. **Verify `_ensure_h264_preview`:** Confirm H.264 MP4 returns `src` unchanged. Run a typical MP4 through prepare-source and confirm no transcode copy is created.

### P2 — Remove source duplication (actual change)

1. **Patch 1:** Change `keep_source_copy: true` → `false` in render-engine.js.
2. **Test YouTube flow** (see Section 9).
3. **Patch 4:** Add cleanup endpoint for existing `/upload/source/` dirs.
4. Run cleanup endpoint on existing channels.

### P3 — Cleanup dead code

1. **Evaluate** `_reserve_source_path()` at render_pipeline.py:1423 — with keep_source_copy always False, this function is now dead code. Remove after confirming P2 is stable.
2. **Evaluate** the `is_temp_source` branch at render_pipeline.py:2148-2171 — once keep_source_copy is always False, this entire block is dead. Remove after P2 validation period.

---

## SECTION 9 — TEST PLAN

### T1 — Typical H.264 local video (happy path)
- **File:** Standard 1080p H.264 MP4, ~500MB
- **Step:** Pick file → Open Editor → Start Render
- **Verify:** No files written to `/upload/source/`. `TEMP_DIR/preview/{sid}/` has NO `preview_h264.mp4` (source returned directly). Render completes. Output in `render_output/`.
- **Expected:** Fast editor open. No disk copy.

### T2 — HEVC/H.265 local video
- **File:** HEVC-encoded MP4 (common on iPhone, GoPro)
- **Step:** Pick file → Open Editor → Start Render
- **Verify:** `TEMP_DIR/preview/{sid}/preview_h264.mp4` IS created (transcode needed for editor). Render pipeline uses ORIGINAL HEVC file (not the preview copy). Output correct.
- **Expected:** Editor open is slower (transcode). Render uses original HEVC.

### T3 — Filename with spaces
- **File:** `my vacation clip.mp4`
- **Step:** Full render flow
- **Verify:** No path errors. Render completes. Cache key includes full path with spaces.

### T4 — Unicode filename
- **File:** `Tiệc sinh nhật.mp4`
- **Step:** Full render flow
- **Verify:** No path errors. `Path.resolve()` handles Vietnamese characters. Render completes.

### T5 — 5GB large local video
- **File:** 5GB MP4
- **Step:** Full render flow
- **Verify:** No OOM. No copy attempt. Render uses original path. Progress events fire normally.

### T6 — Source file moved during render (after Patch 2)
- **File:** Any local video
- **Step:** Start render. Rename or move source file while render is in progress.
- **Verify:** Job logs show "Source file was moved or deleted" error (not raw ffmpeg stderr). No crash.

### T7 — YouTube render after Patch 1 (keep_source_copy=False)
- **Step:** YouTube URL → Open Editor → Start Render
- **Verify:** After render, `/upload/source/` has NO new files. `TEMP_DIR` has been cleaned. Render output is correct.

### T8 — YouTube rerender after Patch 1
- **Step:** Complete T7. Then trigger rerender via Resume.
- **Verify:** System re-downloads YouTube source (no crash from missing persistent copy). Rerender completes.

### T9 — Subtitle render (local video)
- **Step:** Local video → Enable subtitles → Start Render
- **Verify:** Whisper transcribes from original path. SRT written to TEMP. Subtitle burned into output. No copy of source created.

### T10 — Batch render (local video)
- **Step:** Batch queue with 3 local video files
- **Verify:** Each job uses original path independently. No cross-job file sharing. No copies in `/upload/source/`.

### T11 — Review Queue after render
- **Step:** Complete a local video render. Open Review Queue.
- **Verify:** Job shows correct source filename. Clicking rerender works. No reference to `/upload/source/` path.

### T12 — Cleanup endpoint (after Patch 4)
- **Step:** Call `DELETE /api/render/cleanup-source-copies?channel_code=T1`
- **Verify:** Returns count of deleted files. `/upload/source/` dir is empty. Subsequent renders unaffected.

---

## SECTION 10 — DEFINITION OF DONE

### Success criteria:

| Criterion | How to verify |
|---|---|
| No source duplication for local video | Render completes; `/upload/source/` unchanged; no `shutil.copy` in job log |
| No source duplication for YouTube (after Patch 1) | Render completes; `/upload/source/` has no new files; TEMP cleaned |
| Faster render start for local video | Already achieved (no copy was happening). Verify with T1 timing. |
| Less disk usage | Run T7+T8 on 3 YouTube renders. Confirm `/upload/source/` stays empty. |
| Zero render regressions | T1 through T12 all pass |
| Creator-safe errors | T6 produces human-readable error, not ffmpeg stderr |
| Rerender works | T8 passes (re-download for YouTube, original path for local) |
| Review Queue unaffected | T11 passes |
| Batch render unaffected | T10 passes |

### What does NOT change:
- `source_video_path` field in payload — still the original user path
- Render pipeline source path resolution logic — already correct
- Scene detection, transcription, subtitle cache strategy — unchanged
- `_ensure_h264_preview` — already skips H.264 sources
- All ffmpeg command construction — unchanged
- VideoLocal workflow lock — upheld (source_video_path, local_video_file_picker, manual_output_dir untouched)

---

## APPENDIX — Key File Reference Map

| File | Function/Line | Role |
|---|---|---|
| `backend/static/js/render-config.js:8` | `onLocalVideoPicked()` | Electron: uses `file.path` directly, no upload |
| `backend/static/js/render-config.js:96` | `uploadLocalFileIfNeeded()` | Browser fallback: uploads file (Electron: skipped) |
| `backend/static/js/render-engine.js:75` | `keep_source_copy: true` | **PATCH 1 TARGET:** change to `false` |
| `backend/static/js/render-engine.js:159` | local branch in `startRender()` | Calls `openEditorView` directly (no pre-download) |
| `backend/static/js/editor-view.js:1184` | `openEditorView()` | Calls `prepare-source` for both local and YouTube |
| `backend/app/routes/render.py:289` | `_ensure_h264_preview()` | Creates preview copy only if source not H.264 |
| `backend/app/routes/render.py:392` | `prepare_source()` local branch | Validates file, creates H.264 preview if needed |
| `backend/app/routes/render.py:807` | `upload_local_video()` | Browser-only: copies to `/upload/source/` |
| `backend/app/routes/render.py:1423` | `_reserve_source_path()` | Creates `/upload/source/` dir for YouTube persistence |
| `backend/app/orchestration/render_pipeline.py:1992` | source resolution | Uses `source_video_path` directly for local |
| `backend/app/orchestration/render_pipeline.py:2148` | `keep_source_copy` check | **BECOMES DEAD CODE** after Patch 1 (for local) |
| `backend/app/orchestration/render_pipeline.py:2157` | `is_temp_source` guard | Already protects local files from being copied |
