# Configuration — AI Video Render Studio

> Cập nhật 2026-06-29 từ source (grep `os.getenv` toàn `backend/app`). Biến đọc từ
> môi trường thực hoặc file `.env` ở gốc repo (`core/config.py` load qua
> python-dotenv, `override=False` → env thực luôn thắng).

## 1. Đường dẫn dữ liệu (`core/config.py`)

Gốc dữ liệu `APP_DATA_DIR`:
- Dev: `<repo>/data`.
- Packaged (PyInstaller): `%APPDATA%/RenderVideoTool/data`.

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `APP_DATA_DIR` | (xem trên) | Gốc mọi dữ liệu runtime |
| `DATABASE_PATH` | `APP_DATA_DIR/app.db` | SQLite — nguồn chân lý job |
| `REPORTS_DIR` | `APP_DATA_DIR/reports` | Report render |
| `CHANNELS_DIR` | `<repo>/channels` hoặc `APP_DATA_DIR/channels` | Output + log theo channel |
| `TEMP_DIR` | `APP_DATA_DIR/temp` | Thư mục làm việc tạm |

Dẫn xuất (không phải env): `LOGS_DIR`, `COOKIES_DIR`, `CACHE_DIR`, `BGM_DIR`.
Tất cả được `mkdir` lúc import. BGM người dùng đặt tại `{BGM_DIR}/{mood}/*.mp3`.

Cache dir cũng nhận: `XDG_CACHE_HOME`, `TORCH_HOME`, `HF_HOME`,
`TRANSFORMERS_CACHE`, `OLLAMA_MODELS`, `TEMP`/`TMP`, `FONTCONFIG_FILE` —
`main.py` đặt `setdefault` để chuyển model/cache về thư mục ổn định.

## 2. Mạng & bảo mật

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `ALLOW_REMOTE` | `0` | API **không có auth**. `main.py` từ chối khởi động nếu bind non-loopback mà không đặt `1`. Docker image đặt `1` |
| `ENABLE_DEVTOOLS` | `0` (off) | Mount `POST /api/dev/command` (chạy shell, không auth). Chỉ mount khi `1` **và** bind loopback (fail-closed). Không bao giờ bật ở production |
| `ENABLE_V2` | `1` | Thử mount router `v2.*` (module v2 hiện không có trong source → import fail êm, log warning) |

## 3. Hàng đợi job & tài nguyên

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `MAX_CONCURRENT_JOBS` | `cpu//2` | Số job chạy song song (scheduler) |
| `MAX_RENDER_JOBS` | `= MAX_CONCURRENT_JOBS` | Số pipeline vào vùng encode cùng lúc (`JOB_SEMAPHORE`) |
| `MAX_JOB_AGE_SECONDS` | `7200` | Watchdog huỷ job chạy quá lâu. `0` = tắt |
| `NVENC_MAX_SESSIONS` | `3` | Số phiên NVENC GPU (`NVENC_SEMAPHORE`). **Không tăng quá giới hạn phần cứng** |
| `SHUTDOWN_TIMEOUT_SEC` | `30` | Thời gian graceful shutdown |

## 4. FFmpeg & render

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `FFMPEG_TIMEOUT_SECONDS` | — | Timeout mỗi lệnh FFmpeg |
| `RENDER_MIN_FREE_DISK_MB` / `RENDER_WARN_FREE_DISK_MB` | — | Gate/ cảnh báo dung lượng trống trước render |
| `RENDER_FUSE_CUT` | — | Bật cắt fuse trong `part_cut` |
| `MICRO_PACING_MIN_TRIM_MS` | — | Ngưỡng micro-pacing trim |
| `SUBTITLE_CAPCUT` | — | Style phụ đề kiểu CapCut |
| `S4_THUMBNAIL_QUALITY_ENABLED` | — | Bật chấm chất lượng thumbnail |
| `PREVIEW_SESSION_TTL_HOURS` | — | TTL phiên preview nguồn |
| `RENDER_DEBUG_LOG` | `0` | Ghi artifact debug (timeline JSON, scene) |

## 5. Whisper / transcription

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `WARMUP_WHISPER_MODEL` | `small` | Model nạp sẵn lúc startup |
| `WHISPER_MODEL_CACHE_MAX` | `2` | LRU model OpenAI-whisper |
| `FW_MODEL_CACHE_MAX` | `2` | LRU model faster-whisper |
| `WHISPER_BATCH_SIZE` | 8 (CUDA)/4 (CPU) | batch_size |
| `WHISPER_CONTENT_HASH_CACHE` | off | Cache transcription theo sha256 nội dung |
| `LLM_WHISPER_MODEL` / `LLM_WHISPER_AUTO_SELECT` / `LLM_WHISPER_TIMEOUT_MULT` | — | Whisper trong nhánh LLM |
| `TIMED_NARRATION_TTS_CONCURRENCY` | — | Số luồng TTS narration |

## 6. AI / LLM

Xem bảng đầy đủ trong [AI_INTEGRATION.md](AI_INTEGRATION.md). Chính:
`LLM_EMIT_RENDER_PLAN` (1), `AI_PROVIDER_DEFAULT` (gemini), `LLM_FALLBACK_ENABLED`,
`GEMINI_API_KEY`/`OPENAI_API_KEY`/`CLAUDE_API_KEY`, `AI_CLOUD_*`,
`GEMINI_DEFAULT_MODEL`/`GEMINI_THINKING_BUDGET`/`GEMINI_REQUEST_TIMEOUT`,
`*_MAX_SRT_CHARS`, `REWRITE_MAX_INPUT_CHARS`, `PROMPTS_MAX_SRT_CHARS`.

## 7. Download (yt-dlp)

| Biến | Ý nghĩa |
|------|---------|
| `YTDLP_AUTO_UPDATE` | `0` để tắt auto-update yt-dlp lúc startup |
| `YTDLP_COOKIEFILE` | Đường dẫn file cookie |
| `YTDLP_COOKIES_FROM_BROWSER` | Lấy cookie từ trình duyệt |
| `YTDLP_PROXY` | Proxy tải |
| `YTDLP_WALLCLOCK_TIMEOUT` / `DOWNLOAD_WALLCLOCK_TIMEOUT` | Timeout tải |
| `OLLAMA_URL` / `OLLAMA_MODEL` | (warmup) endpoint Ollama nếu dùng |

## 8. DB / backup / cleanup

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `DB_TIMEOUT` | `30` | Timeout kết nối SQLite (giây) |
| `JOB_RETENTION_DAYS` | `0` | Xoá job non-active quá tuổi. `0` = tắt. UI Settings ghi đè qua DB |
| `CLEANUP_INTERVAL_SEC` | `1800` | Chu kỳ vòng cleanup nền |
| `LOG_KEEP_LAST` | `30` | Giữ N log job gần nhất |
| `LOG_KEEP_DAYS` | `10` | Xoá log job cũ hơn |
| `LOG_LEVEL` | — | Mức log |
| `DB_BACKUP_DIR` / `DB_BACKUP_KEEP_LAST` / `DB_BACKUP_EVERY_N_JOBS` / `DB_BACKUP_MIN_INTERVAL_SEC` | — | Backup DB định kỳ |

## 9. Sự kiện / WebSocket

| Biến | Ý nghĩa |
|------|---------|
| `EVENT_BROADCASTER_QUEUE_SIZE` | Kích thước hàng đợi broadcaster |
| `EVENT_BROADCASTER_MAX_SUBS` | Số subscriber tối đa |

## 10. UI tĩnh

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STATIC_UI_VERSION` | `legacy` | `v2` → phục vụ `backend/static-v2/` (UI React hiện tại) |

> Lưu ý: nhiều biến không có "mặc định" trong bảng nghĩa là giá trị mặc định nằm
> sâu trong module liên quan; tra trực tiếp `os.getenv(...)` tại file đó khi cần
> con số chính xác.
