# Download and Source Preparation

## Download System Role

**Stability marker: Stable contract**

The project has two related but separate download/source flows:

1. **Render source preparation**: prepares a source for editor preview and render.
2. **Download tab**: standalone batch downloader for saving public videos to disk.

Both use shared downloader infrastructure, but they are not the same product flow.

Primary files:

- `backend/app/routes/render.py`
- `backend/app/routes/download.py`
- `backend/app/services/downloader.py`

## Render Source Preparation

**Stability marker: Stable contract**

Render source preparation uses `/api/render/prepare-source`.

It can handle:

- YouTube URL input
- local file input

The endpoint validates the source, creates a preview session, probes duration, creates a browser-safe preview when needed, and returns session metadata for the editor.

Preview sessions are later consumed by `/api/render/process` through `edit_session_id`.

### What must not break: source preparation

- Preserve `session_id` behavior.
- Preserve `video_path` and `preview_path` distinction.
- Preserve local file validation.
- Preserve YouTube download health and error handling.
- Preserve editor preview routes.

## YouTube Input Flow

**Stability marker: Semi-stable implementation**

For render input, YouTube source preparation downloads through `download_youtube()`.

The downloader supports:

- multi-client yt-dlp attempts
- dynamic format fallback
- proxy sanitization
- quality rejection for too-low results
- progress callbacks
- fixed source filename behavior for pipeline stability

`source_quality_mode` is validated by `RenderRequest` and passed to the downloader.

## Local Input Flow

**Stability marker: Stable contract**

Local source mode validates the file path and probes the media. The preview session keeps the original video path and may also create a browser-safe preview copy.

The render pipeline should not mutate the user's original local file.

If source archive is enabled, the pipeline may hardlink or copy the source into the output source archive.

## Preview Session Behavior

**Stability marker: Stable contract**

Preview sessions live under:

```text
TEMP_DIR/preview/{session_id}
```

They can contain:

- `session.json`
- downloaded or referenced source
- browser-safe preview
- cached preview transcript

Routes:

- `GET /api/render/preview-video/{session_id}`
- `GET /api/render/preview-transcript/{session_id}`

Preview transcript uses a lightweight Whisper path for editor preview and should not be confused with full render transcription.

## Download Tab Flow

**Stability marker: Stable contract**

The Download tab uses `/api/download/process`.

It supports batch URLs and per-item status. It saves files to the requested output directory and is separate from render jobs.

Supported public source detection currently includes:

- YouTube
- Facebook
- Instagram
- unknown/unsupported

Standalone download jobs use the job/part system for progress and retry.

## YouTube Multi-Client Retry

**Stability marker: Semi-stable implementation**

`download_youtube()` rotates through multiple yt-dlp client/format strategies and can run a dynamic fallback based on probed formats.

Preserve the historical warning: YouTube behavior changes often. Client and format strategy details are implementation, not a permanent public contract.

## Proxy Sanitization

**Stability marker: Stable contract**

Proxy sanitization exists because stale OS proxy values can break yt-dlp.

Priority:

1. `YTDLP_PROXY`
2. proxy environment variables
3. `urllib.request.getproxies()`
4. explicit no-proxy fallback

Bad loopback proxy hosts such as `127.0.0.1`, `localhost`, `::1`, and `0.0.0.0` are disabled for yt-dlp.

Preserve this behavior. It prevents confusing download failures caused by stale local proxy settings.

## Cache and Temp Paths

**Stability marker: Semi-stable implementation**

Important runtime locations:

- preview sessions under `TEMP_DIR/preview`
- render job work files under `TEMP_DIR/{job_id}`
- download job temp folders under download temp paths
- final outputs under user-selected output directories or channel output folders

Cleanup must not delete user originals or final outputs.

## Validation and Error Messages

**Stability marker: Stable contract**

Validation protects:

- URL format
- supported source type
- output directory
- local file existence
- source availability

Friendly error mapping should preserve user-readable categories such as:

- unsupported link
- private/unavailable video
- login required
- network/proxy issue
- timeout
- download could not be completed

## Download Health Check

**Stability marker: Semi-stable implementation**

`POST /api/render/download-health` probes YouTube availability without downloading the full file. It uses related client rotation logic and returns information such as title, best height, fps, and stream counts.

This is advisory. Actual download can still fail later because public video platforms change behavior.

## Known Failure Modes

**Stability marker: Stable contract**

Preserve these warnings:

- YouTube format availability changes frequently.
- Some videos require login/cookies.
- Proxy settings can silently break downloads.
- Low-quality formats may be rejected.
- Facebook/Instagram support depends on yt-dlp behavior.
- Preview source and final render source must remain consistent.

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not promise every public URL can be downloaded.
- Do not document bypass tactics beyond current implementation facts.
- Do not expose private cookies or credentials.
- Do not freeze every yt-dlp format string as a stable API.

