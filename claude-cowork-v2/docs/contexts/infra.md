# Infrastructure Context

## Deployment Model

This is a **local desktop application**. It is not a cloud-hosted service.

- Packaged as an Electron app for Windows 11
- Backend runs as a child process of the Electron main process
- SQLite database lives at `data/render.db` relative to project root
- All model caches redirected to `data/` to avoid filling C: drive

## Environment Variables (Production)

Set in Electron's main process before spawning the backend:

| Variable | Purpose |
|----------|---------|
| `XDG_CACHE_HOME` | Redirect generic cache (e.g., yt-dlp) |
| `TORCH_HOME` | Redirect PyTorch model cache |
| `HF_HOME` | Redirect HuggingFace model cache |
| `OLLAMA_MODELS` | Redirect Ollama model storage |
| `TEMP` / `TMP` | Redirect temp files to project data dir |

## ffmpeg

ffmpeg is bundled with the application. The binary path is resolved via
`bin_paths.py` using a priority list:
1. `FFMPEG_PATH` env var
2. Project-local `bin/ffmpeg.exe`
3. System PATH

Never assume ffmpeg is on PATH in production.

## Port

Backend listens on `127.0.0.1:8000` by default.
Port is configurable but the frontend must be rebuilt to change it.
Port conflicts are detected at startup — if port is in use, the Electron
shell shows an error and exits gracefully.

## Disk Space

Each render job can produce:
- Source video: up to 2 GB (1080p 60min)
- Segments: up to 500 MB (20 x 25MB clips)
- Output clips: up to 200 MB (20 x 10MB encoded)
- Logs: < 1 MB

Operators must ensure > 10 GB free on the data drive before running.

## Backup

SQLite WAL mode is safe for hot backup with:
```
sqlite3 data/render.db ".backup data/render.db.bak"
```
