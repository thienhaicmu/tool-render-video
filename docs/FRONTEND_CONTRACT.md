# Frontend Contract

## HTTP API

### Submit Render Job

```
POST /api/render/process
Content-Type: application/json
Body: RenderRequest (see below)
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "queued",
  "message": "Job queued"
}
```

### Poll Job Status

```
GET /api/jobs/{job_id}
```

**Response:** Full job object with `status`, `stage`, `progress_percent`, `result_json` (when complete).

### WebSocket Live Progress

```
GET /api/jobs/{job_id}/ws  (upgrade to WebSocket)
```

Every event has exactly three top-level keys:

```json
{
  "job": {
    "job_id": "abc123",
    "status": "running",
    "stage": "rendering",
    "progress_percent": 45,
    "message": "Rendering part 2/5"
  },
  "parts": [
    {
      "part_no": 1,
      "status": "done",
      "progress_percent": 100,
      "output_file": "/path/to/part_001.mp4"
    },
    {
      "part_no": 2,
      "status": "rendering",
      "progress_percent": 60
    }
  ],
  "summary": {
    "total_parts": 5,
    "completed_parts": 1,
    "failed_parts": 0,
    "elapsed_sec": 38.2
  }
}
```

`parts` is always present (may be `[]`). Never omit any of the three top-level keys.

HTTP polling (`GET /api/jobs/{id}`) must remain fully functional as a WebSocket alternative.

---

## RenderRequest Schema

Key fields accepted by `POST /api/render/process`:

```typescript
interface RenderRequest {
  // Source (required — one of these two)
  source_mode?: "local"            // default
  source_video_path?: string       // absolute path to local file
  edit_session_id?: string         // editor session ID (alternative to source_video_path)

  // Editor trim (only with edit_session_id)
  edit_trim_in?: number            // seconds
  edit_trim_out?: number           // seconds
  edit_volume?: number             // 1.0 = original, 0.5 = half

  // Output
  output_mode?: "manual" | "channel"  // default "manual"
  channel_code?: string               // required when output_mode="channel"
  output_dir?: string                 // required when output_mode="manual"
  render_output_subdir?: string
  cleanup_temp_files?: boolean        // default true
  keep_source_copy?: boolean          // default false

  // Clip selection
  output_count?: number            // number of clips to produce
  min_duration_sec?: number
  max_duration_sec?: number

  // AI
  ai_provider?: "gemini" | "openai" | "claude"
  gemini_api_key?: string
  openai_api_key?: string
  claude_api_key?: string

  // Subtitles
  subtitle_enabled?: boolean
  subtitle_style?: string          // "viral" | "clean" | "story" | "gaming"
  subtitle_translate_enabled?: boolean
  subtitle_translate_target_lang?: string
  subtitle_edits?: SubtitleEdit[]

  // Voice
  voice_enabled?: boolean
  voice_source?: "manual" | "model"
  tts_engine?: "edge" | "xtts"
  voice_script?: string            // when voice_source="manual"

  // Text overlays
  text_layers?: TextLayerConfig[]

  // Encoding
  video_codec?: string             // "h264" | "h265"
  video_crf?: number
  motion_aware_crop?: boolean
}
```

**Rejected fields (HTTP 400):**
- `source_mode` anything other than `"local"` → "Use standalone Downloader"
- `output_mode` other than `"manual"` or `"channel"` → validation error

**Deprecated fields (silently ignored):**
- `youtube_url`, `youtube_urls` — present for backward compat, not processed

---

## Job Status Values

```
queued → running → completed
                 → completed_with_errors (partial success)
                 → failed
                 → cancelled
```

Partial success (`completed_with_errors`): some clips rendered successfully. `result_json.failed_parts` lists which part numbers failed. Successfully rendered clips are accessible in `result_json.outputs`.

---

## Result JSON Key Fields

Available in `result_json` when job reaches `completed` or `completed_with_errors`:

```typescript
interface ResultJson {
  outputs: string[]              // paths to all successfully rendered files
  output_ranking: OutputRank[]   // sorted by output_rank_score desc
  best_clip: OutputRank          // highest-ranked clip
  best_exports: OutputRank[]     // top-N auto-exported clips
  failed_parts: number[]         // part indices that failed
  is_partial_success: boolean
  selected_segments_count: number
  successful_outputs_count: number
  failed_outputs_count: number
  segments: ScoredSegment[]      // AI-selected segment metadata
  voice_summary: object
  subtitle_translate_summary: object
  recovery_notes: string[]
}

interface OutputRank {
  output_rank_score: number      // weighted score (see AI_INTEGRATION.md)
  is_best_output: boolean        // true for highest-ranked output
  is_best_clip: boolean          // alias for is_best_output
  output_file: string
  output_rank: number            // 1-based position
  part_no: number
  viral_score: number
  hook_score: number
  retention_score: number
}
```

---

## Editor Session API

### Create Session

```
POST /api/editing/sessions
Body: { "source_path": "/absolute/path/to/video.mp4" }
Response: { "session_id": "sess_abc123", "duration": 120.5, ... }
```

### Preview Stream

```
GET /api/editing/sessions/{session_id}/preview
Range header supported — returns H.264 transcoded preview
```

### Delete Session

```
DELETE /api/editing/sessions/{session_id}
```

Sessions expire after `PREVIEW_SESSION_TTL_HOURS` (default 6h). Expired sessions are cleaned up in the periodic maintenance loop and in the `finally` block when a render job using that session completes.

---

## Download API

Downloads are independent of the render pipeline. They download video files to disk; those files are then rendered via `source_mode="local"`.

```
POST /api/download/batch
Body: { "urls": ["https://..."], "output_dir": "/path" }
Response: { "ids": ["dl_abc123"] }

GET /api/download/{id}
Response: { "status", "progress", "speed_str", "eta_str", "output_path" }
```

Supported platforms: YouTube, TikTok, Instagram, Facebook, Douyin, generic (yt-dlp fallback).

---

## Health Endpoint

```
GET /health
Response:
{
  "status": "ok",
  "ui_version": "v2" | "legacy",
  "db_path": "/absolute/path/to/app.db",
  "db_fallback_active": false
}
```

`db_fallback_active: true` indicates the database is being written to the fallback location (`%LOCALAPPDATA%`) instead of the primary path — a split-DB condition that requires operator attention.
