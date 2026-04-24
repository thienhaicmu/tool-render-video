# Architecture

## System overview

Render Studio is a **single-machine, local-first** application. There are no cloud services, no external databases, and no background daemons beyond the FastAPI server.

```
┌─────────────────────────────────────────────────┐
│  Electron Desktop Shell  (desktop-shell/main.js) │
│  - Spawns Python backend                         │
│  - Serves BrowserWindow at http://127.0.0.1:8000 │
│  - IPC: dialog:pickDirectory, shell:openPath     │
└────────────────────┬────────────────────────────┘
                     │ HTTP (localhost:8000)
┌────────────────────▼────────────────────────────┐
│  FastAPI Backend  (backend/app/main.py)          │
│  Uvicorn · Python 3.11+                         │
│                                                  │
│  Routes                                          │
│  ├── /api/render/*     Render pipeline           │
│  ├── /api/download/*   Batch video downloader    │
│  ├── /api/jobs/*       Job status polling        │
│  ├── /api/upload/*     TikTok uploader           │
│  ├── /api/channels/*   Channel management        │
│  ├── /api/voice/*      Voice profile list        │
│  └── /api/devtools/*   Maintenance tools         │
│                                                  │
│  Services                                        │
│  ├── downloader.py     yt-dlp wrapper            │
│  ├── render_pipeline.py   Orchestration          │
│  ├── scene_detector.py    PySceneDetect          │
│  ├── subtitle_engine.py   Whisper + SRT/ASS      │
│  ├── tts_service.py       Edge TTS               │
│  ├── audio_mix_service.py FFmpeg audio mix       │
│  ├── translation_service.py  Google Translate    │
│  ├── render_engine.py     FFmpeg encode          │
│  ├── job_manager.py       ThreadPoolExecutor     │
│  └── db.py                SQLite                 │
│                                                  │
│  Storage                                         │
│  ├── data/app.db           SQLite (jobs, parts)  │
│  ├── data/logs/            JSON-lines event logs │
│  ├── data/temp/            Working files         │
│  └── channels/<code>/      Output trees          │
└─────────────────────────────────────────────────┘
         │
         │ subprocess
         ▼
   ffmpeg / ffprobe / whisper / edge-tts / playwright
```

---

## Component map

### Backend routes

| Route prefix | File | Responsibility |
|---|---|---|
| `/api/render` | `routes/render.py` | prepare-source, render jobs, quick-process |
| `/api/download` | `routes/download.py` | batch download queue |
| `/api/jobs` | `routes/jobs.py` | poll job + part status |
| `/api/upload` | `routes/upload.py` | TikTok upload orchestration |
| `/api/channels` | `routes/channels.py` | channel CRUD |
| `/api/voice` | `routes/voice.py` | voice profile + list API |
| `/api/devtools` | `routes/devtools.py` | maintenance, QA runner |

### Key services

| Service | Purpose |
|---|---|
| `downloader.py` | yt-dlp wrapper with proxy sanitization and multi-client retry |
| `render_pipeline.py` | Orchestrates all render stages in sequence |
| `scene_detector.py` | PySceneDetect ContentDetector with auto frame-skip |
| `segment_builder.py` | Splits scenes into timed segments within min/max bounds |
| `viral_scorer.py` | Scores segments (motion, hook, viral) for ordering |
| `subtitle_engine.py` | Whisper → SRT; SRT slice; SRT → ASS karaoke/bounce |
| `tts_service.py` | Microsoft Edge TTS via `edge-tts` library |
| `audio_mix_service.py` | FFmpeg filter_complex for narration mixing |
| `translation_service.py` | `deep_translator` Google free API, chunked |
| `render_engine.py` | FFmpeg encode: crop, subtitle burn, text overlays, effects |
| `job_manager.py` | In-process `ThreadPoolExecutor`; deduplication by job_id |
| `db.py` | SQLite: `jobs` + `job_parts` tables |

---

## Data flow: full render from YouTube

```
Browser click "Start Render"
  │
  ├─ POST /api/render/prepare-source
  │    └─ download_youtube(url, work_dir)     → source.mp4 in TEMP
  │    └─ _ensure_h264_preview()              → preview_h264.mp4 (if not h264)
  │    └─ _save_session(session_id, {...})    → TEMP/preview/{id}/session.json
  │    └─ returns session_id, duration, title
  │
  ├─ Frontend opens Editor view
  │    └─ user adjusts trim / volume / settings
  │
  └─ POST /api/render/process (payload includes edit_session_id)
       └─ submit_job → ThreadPoolExecutor
            └─ run_render_pipeline()
                 ├─ load_session → source_path (from TEMP)
                 ├─ edit trim/volume → edited_{stem}.mp4 (if needed)
                 ├─ keep_source_copy → os.link() or shutil.copy2()
                 ├─ detect_scenes()
                 ├─ build_segments_from_scenes()
                 ├─ score_segments()
                 ├─ transcribe_to_srt() — full video once
                 └─ ThreadPoolExecutor (per-part parallel)
                      ├─ cut_video()
                      ├─ slice_srt_by_time()
                      ├─ translate_srt_file() (optional)
                      ├─ srt_to_ass_karaoke() / srt_to_ass_bounce()
                      ├─ render_part_smart()
                      └─ mix_narration_audio() (if voice enabled)
```

---

## Storage layout

### `data/` (runtime)

```
data/
├── app.db                  SQLite — jobs, job_parts
├── logs/
│   ├── app.log             All structured JSON events
│   ├── error.log           ERROR-level events only
│   └── request.log         HTTP 4xx validation rejections
├── temp/
│   ├── preview/{session_id}/   Editor session files
│   │   ├── session.json
│   │   ├── source.mp4 (or preview_h264.mp4)
│   │   └── preview_transcript.json
│   ├── {job_id}/               Render working files
│   │   ├── source.mp4 (YouTube download)
│   │   ├── edited_*.mp4 (if trim/volume applied)
│   │   ├── {slug}_part_*.mp4 (raw cuts)
│   │   ├── {slug}_part_*.srt
│   │   ├── {slug}_part_*.ass
│   │   └── {slug}_full.srt
│   └── downloads/{job_id}/item_NNN/   Download tab temp
├── whisper_cache/          Downloaded Whisper model weights
├── torch/                  PyTorch cache
├── huggingface/            HuggingFace model cache
└── ollama/models/          Ollama model storage
```

### `channels/<code>/` (output)

```
channels/T1/
├── upload/
│   ├── video_output/       Rendered parts (final output)
│   ├── source/             Source archive (when keep_source_copy=true)
│   └── hashtags.txt
├── uploaded/               Successfully uploaded files
├── failed/                 Upload-failed files
├── logs/                   Per-job render logs
└── browser_profile/        Playwright browser profile
```

---

## Job system

Jobs are tracked in SQLite with two tables:

**`jobs`** — one row per job
- `job_id` UUID
- `kind` — `render` | `download` | `render_batch`
- `status` — `queued` | `running` | `completed` | `failed` | `interrupted`
- `stage` — current `JobStage` enum value
- `progress_percent` 0–100
- `payload_json` — full request payload (enables resume)
- `result_json` — output paths, counts

**`job_parts`** — one row per segment within a render job
- `part_no`, `part_name`, `status` (`JobPartStage`)
- `start_sec`, `end_sec`, `duration`, `viral_score`
- `progress_percent`, `output_file`

On server startup, any job in `queued` or `running` state is marked `interrupted`. The user can resume from the UI.

---

## Logging

Three log destinations, all JSON-lines format:

| File | Content | When written |
|---|---|---|
| `data/logs/app.log` | All `_emit_render_event()` calls | Always |
| `data/logs/error.log` | ERROR/CRITICAL events only | On failure |
| `data/logs/request.log` | HTTP 4xx validation rejections | Before pipeline starts |
| `channels/<code>/logs/{job_id}.log` | Per-job human-readable lines | During render |

---

## Proxy handling for yt-dlp

`downloader._resolve_ytdlp_proxy(context)` returns the value passed as `"proxy"` in all yt-dlp option dicts:

1. `YTDLP_PROXY` env var → used as-is (user override)
2. System env vars (`HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY`) → checked for bad hosts (loopback: `127.0.0.1`, `localhost`, `::1`, `0.0.0.0`)
3. `urllib.request.getproxies()` → same bad-host check
4. Nothing found → `""` (explicit no-proxy, prevents yt-dlp auto-detecting a stale OS proxy like `127.0.0.1:9`)

Bad proxy hosts (loopback) are silently disabled. A `download.proxy.disabled` warning is logged.
