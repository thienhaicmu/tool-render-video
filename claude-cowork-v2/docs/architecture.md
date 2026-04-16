# Architecture

## High-Level Flow

```
User Input (UI / API)
  → Job Queue (SQLite + ThreadPoolExecutor)
    → Download Stage (yt-dlp)
    → Scene Detection (ffmpeg scene filter)
    → Segment Building (ffmpeg trim)
    → Transcription (Whisper)
    → Render (ffmpeg + NVENC/CPU fallback)
    → Report Writing
  → Job Completion
    → Upload (Playwright, optional)
```

## Key Design Decisions

### Job Queue
- Uses Python `ThreadPoolExecutor(max_workers=4)`
- Jobs stored in SQLite; recovered on server restart
- Status: queued → starting → [stage] → done/failed

### Database
- SQLite with WAL mode for concurrent read/write
- Render thread writes progress; WebSocket polls reads
- Single file at `data/render.db`

### Fallback Chain
Every expensive operation has a fallback:
- NVENC GPU encode → CPU x264
- Adaptive download → combined stream
- Move artifact → copy artifact
- WebSocket progress → HTTP polling

### Executor Isolation
Each render job runs in its own thread. Stage functions are pure:
they receive explicit paths and return explicit results.
No global mutable state in the render pipeline.

### Preview Sessions
Temporary in-memory dict + JSON file on disk.
Sessions expire after 6 hours. Cleaned on startup and after render.

## API Surface

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/render/prepare-source` | POST | Download + create preview session |
| `/api/render/preview/<session_id>/<segment>` | GET | Stream preview video |
| `/api/render/start` | POST | Submit render job |
| `/api/jobs/<job_id>` | GET | Job status (HTTP) |
| `/api/jobs/<job_id>/ws` | WS | Job progress stream |
| `/api/channels` | GET/POST | Channel management |
| `/api/upload/start` | POST | Start upload job |

## Dependency Graph

```
pipeline.ts (orchestrator)
  ├── task-intake.ts
  ├── normalize-prompt.ts
  │     └── doc-loader.ts, prompt-loader.ts, schema.ts
  ├── build-task-pack.ts
  │     └── prompt-loader.ts, doc-loader.ts
  ├── run-claude-task.ts
  │     └── logger.ts, ids.ts
  ├── collect-results.ts
  ├── review-task.ts
  │     └── prompt-loader.ts, schema.ts
  ├── generate-final-summary.ts
  └── archive-artifacts.ts
        └── schema.ts
```
