# Configuration — Environment Variables & Feature Flags

## Core Paths

| Var | Default | Purpose |
|-----|---------|---------|
| `APP_DATA_DIR` | Platform-dependent | Root for all runtime data |
| `DATABASE_PATH` | `APP_DATA_DIR/app.db` | SQLite database path |
| `CHANNELS_DIR` | Required, no default | Channel output root |
| `TEMP_DIR` | `APP_DATA_DIR/temp` | Temporary render files |
| `CACHE_DIR` | `APP_DATA_DIR/cache` | Scene detection, transcription cache |
| `LOGS_DIR` | `APP_DATA_DIR/logs` | Log files |
| `COOKIES_DIR` | `APP_DATA_DIR/cookies` | yt-dlp cookie files |

## Server

| Var | Default | Purpose |
|-----|---------|---------|
| `STATIC_UI_VERSION` | `"legacy"` | `"v2"` to serve `static-v2/`, else `static/` |
| `ENABLE_DEVTOOLS` | `"0"` | `"1"` enables `POST /api/dev/command` (loopback only) |
| `ENABLE_V2` | `"1"` | `"0"` to skip v2 route import attempt |
| `CLEANUP_INTERVAL_SEC` | `"1800"` | Seconds between periodic cleanup runs |
| `SHUTDOWN_TIMEOUT_SEC` | `"30"` | Graceful shutdown budget (seconds) |
| `LOG_LEVEL` | `"INFO"` | Root log level |
| `LOG_KEEP_LAST` | `"30"` | Job logs to retain per channel |
| `LOG_KEEP_DAYS` | `"10"` | Max age (days) for job logs |
| `WARMUP_WHISPER_MODEL` | `"small"` | Whisper model to pre-load at startup |

## AI Providers

| Var | Default | Purpose |
|-----|---------|---------|
| `AI_CLOUD_ENABLED` | `"0"` | Enable AI cloud calls |
| `AI_CLOUD_PROVIDER` | `"gemini"` | Default provider (`gemini`/`openai`/`claude`) |
| `AI_PROVIDER_DEFAULT` | `"gemini"` | Fallback when `payload.ai_provider` not set |
| `AI_CLOUD_MODEL` | provider default | Override model name for any provider |
| `GEMINI_API_KEY` | `""` | Google Gemini API key |
| `OPENAI_API_KEY` | `""` | OpenAI API key |
| `CLAUDE_API_KEY` | `""` | Anthropic Claude API key |
| `GEMINI_MAX_SRT_CHARS` | `"60000"` | Max SRT chars sent to Gemini |
| `OPENAI_MAX_SRT_CHARS` | `"30000"` | Max SRT chars sent to OpenAI |
| `CLAUDE_MAX_SRT_CHARS` | `"50000"` | Max SRT chars sent to Claude |
| `GEMINI_REQUEST_TIMEOUT` | `"120"` | Gemini HTTP timeout (seconds) |
| `LLM_MAX_SRT_CHARS` | `"6000"` | Shared cap used in prompts.py |
| `LLM_WHISPER_MODEL` | `"base"` | Whisper model used during LLM pre-render |

## Render Pipeline — Feature Flags

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_EMIT_RENDER_PLAN` | `"1"` | Enable Call 2 / RenderPlan path (flipped ON at Sprint 7.6a) |
| `FEATURE_RAW_PART_SKIP` | `"0"` | Fuse cut+render — skip writing `raw_part.mp4` |
| `FEATURE_RAW_PART_SKIP_MOTION_AWARE` | `"0"` | Extend fuse to motion-aware case |
| `FEATURE_BASE_CLIP_FIRST` | `"0"` | Render base clip without overlays first |
| `FEATURE_OVERLAY_AFTER_BASE_CLIP` | `"0"` | Composite overlays onto base clip |
| `RENDER_DEBUG_LOG` | `"0"` | Enable verbose render debug logging |
| `S4_THUMBNAIL_QUALITY_ENABLED` | `"0"` | Generate thumbnail quality metadata |
| `S4_CANDIDATE_INTELLIGENCE_ENABLED` | `"0"` | Cache AI candidate scoring |
| `S4_SPEAKER_AWARE_CUTS_ENABLED` | `"0"` | Speaker-aware cut boundaries |

## Encoding & Performance

| Var | Default | Purpose |
|-----|---------|---------|
| `MAX_CONCURRENT_JOBS` | `cpu_count()` | Max parallel render jobs in queue |
| `MAX_RENDER_JOBS` | `MAX_CONCURRENT_JOBS` | Max parallel parts per job |
| `NVENC_MAX_SESSIONS` | `"3"` | Max simultaneous NVENC GPU encode sessions |
| `FFMPEG_TIMEOUT_SECONDS` | `"3600"` | FFmpeg subprocess timeout |
| `PREVIEW_SESSION_TTL_HOURS` | `"6"` | Editor session expiry |

## Download

| Var | Default | Purpose |
|-----|---------|---------|
| `YTDLP_WALLCLOCK_TIMEOUT` | `"300"` | yt-dlp download timeout (seconds) |
| `YTDLP_COOKIEFILE` | `""` | Path to Netscape cookie file |
| `YTDLP_COOKIES_FROM_BROWSER` | `""` | Browser name for cookie extraction |
| `YTDLP_PROXY` | `""` | Proxy URL for yt-dlp |

## Database & Backup

| Var | Default | Purpose |
|-----|---------|---------|
| `DB_BACKUP_DIR` | `APP_DATA_DIR/backups` | Backup destination |
| `DB_BACKUP_KEEP_LAST` | `"10"` | Number of backups to retain |
| `DB_BACKUP_EVERY_N_JOBS` | `"5"` | Trigger backup every N completed jobs |
| `DB_BACKUP_MIN_INTERVAL_SEC` | `"3600"` | Minimum seconds between backups |

## Cache (set by main.py at startup)

These redirect model caches to `APP_DATA_DIR` to avoid polluting system directories:

| Var | Set to |
|-----|--------|
| `XDG_CACHE_HOME` | `APP_DATA_DIR/cache` |
| `TORCH_HOME` | `APP_DATA_DIR/torch` |
| `HF_HOME` | `APP_DATA_DIR/huggingface` |
| `TRANSFORMERS_CACHE` | `APP_DATA_DIR/huggingface/hub` |
| `OLLAMA_MODELS` | `APP_DATA_DIR/ollama/models` |
| `TEMP`, `TMP` | `APP_DATA_DIR/tmp` (Windows override) |

---

## Feature Flag Notes

### `FEATURE_RAW_PART_SKIP`
Skips writing `raw_part.mp4` as an intermediate file. Instead, seek is applied input-side in the encode step. Saves ~1 minute per clip on large source files. Only applies when `motion_aware_crop=False` (motion tracking requires the intermediate file).

### `FEATURE_BASE_CLIP_FIRST` + `FEATURE_OVERLAY_AFTER_BASE_CLIP`
Together implement a two-pass encode: render base clip (no subtitles/overlays) first, then composite overlays onto it. Both must be ON for the compositing path to activate.

### `LLM_EMIT_RENDER_PLAN`
When ON (default), Call 2 asks the AI for a full `RenderPlan`. `_scored_from_render_plan()` converts it to `scored[]`, overwriting the Call 1 result. When OFF, only Call 1 segment selection is used.

### `S4_*` flags
Sprint 4 feature experiments. All default OFF. No production usage confirmed.

### `NVENC_MAX_SESSIONS`
Consumer GPU NVENC hardware limit is typically 3-5 sessions. Exceeding it fails ALL active encodes simultaneously with a generic FFmpeg error. Do not raise without knowing the target hardware limit.
