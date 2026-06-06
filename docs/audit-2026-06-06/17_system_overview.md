# 17 — System Overview

> NEW canonical reference. Rebuilt from code on 2026-06-06. Cross-references existing docs only where they accurately reflect current source.

## What the system is

An **offline-first desktop application** that ingests a long video, uses LLM + Whisper + computer-vision heuristics to pick the most "viral" 15–60 s clips, and renders them in vertical aspect with subtitles, narration, motion-aware crop, and overlays. Output is short-form vertical video ready for TikTok / YouTube Shorts / Instagram Reels.

## Top-level surfaces

| Surface | Tech | Code |
|---|---|---|
| Desktop shell | Electron 31 | [desktop-shell/](../../desktop-shell/) |
| Frontend SPA | React 18 + Vite 5 + Zustand 4 | [frontend/src/](../../frontend/src/) |
| Backend API | FastAPI + Uvicorn (single process) | [backend/app/](../../backend/app/) |
| Job execution | In-process priority heap + `ThreadPoolExecutor` | [backend/app/jobs/manager.py](../../backend/app/jobs/manager.py) |
| Job state | SQLite WAL @ `data/app.db` | [backend/app/db/](../../backend/app/db/) |
| Render execution | FFmpeg + ffprobe (subprocess) | [features/render/engine/encoder/](../../backend/app/features/render/engine/encoder/) |
| ASR | OpenAI Whisper (+ optional faster-whisper, whisperX) | [features/render/engine/subtitle/transcription/](../../backend/app/features/render/engine/subtitle/transcription/) |
| LLM clip selection | Anthropic Claude / OpenAI / Google Gemini (lazy-imported) | [features/render/ai/llm/providers/](../../backend/app/features/render/ai/llm/providers/) |
| Motion crop | OpenCV trackers + MediaPipe | [features/render/engine/motion/](../../backend/app/features/render/engine/motion/) |
| TTS narration | edge-tts (default) + optional XTTS | [features/render/engine/audio/](../../backend/app/features/render/engine/audio/) |
| Downloader | yt-dlp + per-platform adapters | [features/download/](../../backend/app/features/download/) |
| Telemetry | Prometheus client (`/metrics`) | [routes/metrics.py](../../backend/app/routes/metrics.py) |

## Sacred invariants

| # | Invariant | Live? |
|---|---|---|
| 1 | `result_json` always carries `output_rank_score`, `is_best_output`, `is_best_clip` | ✓ verified |
| 2 | `RenderRequest` new fields default to disabled | ✓ verified |
| 3 | AI modules return `None` on failure, never raise | ✓ at module level; LLM pipeline does raise (Phase 2/4) |
| 4 | Job stage names frozen: `QUEUED → DOWNLOADING → RENDERING → DONE` (+ `FAILED`, `CANCELLED`) | ✓ enforced by convention; no SQL `CHECK` |
| 5 | Part stage names frozen: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` (+ `FAILED`, `SKIPPED`) | ✓ same |
| 6 | WS event shape `{job, parts, summary}` | ✓ verified at [routes/jobs.py:680](../../backend/app/routes/jobs.py) |
| 7 | `data/app.db` is the only job state | ✓ enforced; 4 raw `sqlite3.connect` sites all sanctioned |
| 8 | `qa_pipeline` validation never bypassed | ✓ verified |

## Networking

The whole system is **localhost-only by design**. Electron spawns the backend on `127.0.0.1:8000`. There is no exposed external port, no auth layer, and no remote management surface. The CSP middleware is the only HTTP-level protection ([main.py:177](../../backend/app/main.py)).

## Hard constraints

| Constraint | Where |
|---|---|
| `NVENC_MAX_SESSIONS` ≤ GPU hardware limit (default 3) | [encoder/ffmpeg_helpers.py:27-28](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py) |
| `MAX_CONCURRENT_JOBS = cpu_count // 2` (default) | [jobs/manager.py](../../backend/app/jobs/manager.py) |
| FFmpeg timeout 3600 s default | [encoder/ffmpeg_helpers.py](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py) |
| Job queue drain timeout 30 s default | [main.py:333](../../backend/app/main.py) |

## What the system is NOT

- Not multi-user. No auth, no isolation.
- Not horizontally scalable. SQLite + single FastAPI process + in-process queue.
- Not cloud-storage-aware. No boto3/azure/gcs imports (Phase 5 verified).
- Not GPU-pool-aware beyond NVENC semaphore. No CUDA stream management.

End of 17_system_overview.md.
