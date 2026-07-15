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

Dẫn xuất (không phải env): `LOGS_DIR`, `COOKIES_DIR`, `CACHE_DIR`, `BGM_DIR`,
`BUNDLED_BGM_DIR`. Tất cả được `mkdir` lúc import. Nhạc nền quét theo thứ tự ưu
tiên: `{BGM_DIR}/{mood}/*.mp3` (của người dùng) → `{BUNDLED_BGM_DIR}/{mood}`
(`<repo>/assets/bgm`, đóng gói theo repo) → `default/` của mỗi tầng. Nạp thư viện
free: `python backend/scripts/fetch_free_bgm.py` (tải CC0+CC-BY vào `assets/bgm`,
commit vào repo để khỏi tải lại; ghi công CC-BY ở `assets/bgm/ATTRIBUTION.txt`).

Story Mode nhạc nền **per-scene/per-beat**: AI gán mood + vị trí nhạc (schema
super-prompt `s4` — placed BGM intro/outro/under/none mỗi beat); pipeline dựng 1
track khớp timeline + duck dưới lời kể. Bật/tắt bằng env `STORY_AUTO_BGM` (mặc
định `1`; đặt `0` để tắt hoàn toàn). Bộ env Story Mode đầy đủ: xem §11.

Cache dir cũng nhận: `XDG_CACHE_HOME`, `TORCH_HOME`, `HF_HOME`,
`TRANSFORMERS_CACHE`, `OLLAMA_MODELS`, `TEMP`/`TMP`, `FONTCONFIG_FILE` —
`main.py` đặt `setdefault` để chuyển model/cache về thư mục ổn định.

## 2. Mạng & bảo mật

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `ALLOW_REMOTE` | `0` | API **không có auth**. `main.py` từ chối khởi động nếu bind non-loopback mà không đặt `1`. Docker image đặt `1` |
| `ENABLE_DEVTOOLS` | `0` (off) | Mount `POST /api/dev/command` (chạy shell, không auth). Chỉ mount khi `1` **và** bind loopback (fail-closed). Không bao giờ bật ở production |
| `ENABLE_V2` | `1` | Thử mount router `v2.*` (module v2 hiện không có trong source → import fail êm, log warning) |

### Content Studio preview guard (CM-1, 2026-07-07)

Các endpoint `/api/content/visual/preview` + `/api/content/narration/preview` **không có auth** (loopback) và một visual preview có thể gọi provider **trả phí** (Imagen/Veo) — 1 asset mỗi lần bấm. Ba guard per-process, in-memory:

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `CONTENT_PREVIEW_RATE_PER_MIN` | `20` | Rate limit dùng chung cho cả hai endpoint (call/phút). `0` = tắt. Vượt → `429` |
| `CONTENT_PREVIEW_DAILY_CAP` | `0` (unlimited) | Trần số visual preview **trả phí** mỗi ngày (chỉ đếm khi asset thực sự do provider paid tạo, KHÔNG tính khi fallback về local). Vượt → `429` |
| `CONTENT_PREVIEW_PAID_DISABLED` | `0` | `1` = chặn hẳn provider paid (`ai_image`/`ai_video`) ở preview → `403`; nguồn free (`stock`/`ai_image_free`) không bị ảnh hưởng |

Quan sát: counter Prometheus `content_preview_total{endpoint,provider,outcome}` (`outcome ∈ ok|rate_limited|budget_capped|paid_disabled|failed`) trên `/metrics`.

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
| `RENDER_FUSE_CUT` | `1` | Cắt fuse trong `part_cut` (gộp cut + encode vào 1 lệnh FFmpeg, bỏ intermediate `raw_part.mp4`). `0` = tắt khẩn cấp, quay về đường legacy. Bật mặc định sau smoke-check A/B 2026-07 (3 lỗi fuse đã vá — xem docstring `_fuse_safe_active`) |
| `MICRO_PACING_MIN_TRIM_MS` | — | Ngưỡng micro-pacing trim |
| `ENABLE_QSV` | `1` | Bậc QSV (Intel iGPU Quick Sync) trong chuỗi encoder card-first NVENC → QSV → CPU. Mỗi bậc probe runtime thật — máy không có phần cứng tự rơi bậc dưới. `0` = bỏ bậc QSV (về hành vi NVENC→CPU cũ) |
| `MICRO_PACING_GPU` | `1` | Pass re-encode của micro-pacing chạy NVENC (cq 17, p5) khi job resolve ra NVENC, thay vì libx264 CPU (~90-110s/clip 60s). Bật mặc định theo quyết định chủ dự án 2026-07 (máy render khách có GPU; encode chính vốn đã NVENC). Máy không GPU tự về libx264; NVENC lỗi tự retry libx264; `0` = tắt khẩn cấp |
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

### TTS / Lồng tiếng (Gemini TTS — engine opt-in, 2026-07-02)

`tts_engine="gemini"` (RenderRequest) bật engine Gemini TTS (online, model
preview, audio có watermark SynthID). Mọi lỗi tự fallback về chuỗi
Edge → Piper → XTTS — không bao giờ mất narration. Cache synthesis theo
hash tại `TEMP_DIR/gemini_tts_cache/` (cùng text không tốn quota lần 2).

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `GEMINI_TTS_MODEL` | `gemini-3.1-flash-tts-preview` | Model TTS |
| `GEMINI_TTS_VOICE` | theo gender (`Kore`/`Charon`) | Ghi đè prebuilt voice |
| `GEMINI_TTS_STYLE` | theo ngôn ngữ + content_type | Ghi đè câu chỉ dẫn giọng đọc (mặc định: bảng vi/en có tempo; `rate` ±3% trở lên thêm hint nhanh/chậm) |
| `GEMINI_TTS_TIMEOUT_SEC` | `120` | Timeout một lời gọi TTS |
| `GEMINI_TTS_MAX_CONCURRENCY` | `2` | Số call TTS đồng thời (part chạy song song) — chặn burst RPM làm cool key pool oan |

Ghi chú vận hành (O-1..O-4, 2026-07-02): call TTS đi qua **key rotation pool**
(429 → xoay key kế, 503/504 → thử key kế không cool) giống 6 wrapper LLM —
một key cạn quota không còn làm render rớt về giọng Edge giữa video. Cache
`gemini_tts_cache/` được prune định kỳ (TTL 30 ngày, cùng lớp với
`xtts_cache`).

2026-07-03: UI mặc định chọn `tts_engine="gemini"` (ô **AI Voice** ở tab
Narration — Gemini / Edge / XTTS). Backend `RenderRequest.tts_engine` vẫn mặc
định `"edge"` (Sacred Contract #2) — chỉ FE đổi default.

### Recap — phụ đề & narration

| Biến | Default | Ý nghĩa |
|------|---------|---------|
| `RECAP_BURN_NARRATION_SUBTITLE` | `0` (tắt) | Bật lớp caption tự động của recap (đốt lời narrator, style riêng). Mặc định OFF — recap chỉ dùng phụ đề theo nút `add_subtitle` của UI. `=1` để bật lại |
| `RECAP_SUBTITLE_STYLE` | dark-card | Ghi đè `force_style` ASS cho caption narration recap (khi bật lớp trên) |
| `RECAP_CONCAT_GPU` | `1` | Cho phép re-encode concat episode dùng NVENC (fallback libx264). Bước ghép giờ ưu tiên copy-stream (title card khớp fps/sample-rate scene) nên hiếm khi cần re-encode |

## 6. AI / LLM

Xem bảng đầy đủ trong [AI_INTEGRATION.md](AI_INTEGRATION.md). Chính:
`LLM_EMIT_RENDER_PLAN` (1), `AI_PROVIDER_DEFAULT` (gemini), `LLM_FALLBACK_ENABLED`,
`GEMINI_API_KEY`/`OPENAI_API_KEY`/`CLAUDE_API_KEY`, `AI_CLOUD_*`,
`GEMINI_DEFAULT_MODEL`/`GEMINI_THINKING_BUDGET`/`GEMINI_REQUEST_TIMEOUT`,
`*_MAX_SRT_CHARS`, `REWRITE_MAX_INPUT_CHARS`, `PROMPTS_MAX_SRT_CHARS`.

Narration rewrite rate-limit protection (per-part calls run in parallel → can
burst a free-tier RPM limit and fail → narration falls back / loses reaction):

| Env | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `LLM_REWRITE_MAX_CONCURRENCY` | `1` | Số lời gọi rewrite LLM đồng thời (1 = tuần tự, tránh burst 429). Tăng khi dùng tier trả phí |
| `LLM_REWRITE_MIN_INTERVAL_SEC` | `0` | Khoảng cách tối thiểu giữa 2 lời gọi rewrite (giây). Vd `4.0` cho ~15 RPM free tier |
| `*_REWRITE_TEMPERATURE` | `0.85` | Nhiệt độ rewrite (gemini/openai/claude) |

### Content Mode planning provider (CM-2, 2026-07-07)

Content Director (`render_format="content"`) giờ chạy trên orchestrator dùng chung `content_director.py` → cả **gemini / openai / claude** đều lập được ContentPlan, nên `LLM_FALLBACK_ENABLED=1` fallback qua provider khác **hoạt động thật** (trước chỉ gemini). Gate two-pass CU-4 (`CONTENT_MULTIPASS`, `CONTENT_MULTIPASS_MIN_CHARS`) nay đọc ở `content_director` cho mọi provider.

| Env | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `CONTENT_PLAN_MODE` | `fast` | CM-7: `fast` = 1 pass plan (mặc định, không đổi). `quality` = thêm 1 pass narration-refine (tái dùng prompt refine sẵn có qua content_director — không thêm prompt) để lời kể mượt scene→scene + khớp thời lượng. **Experimental** — nên đo bằng ai_eval trước khi bật default |
| `CONTENT_PLAN_REPAIR` | `1` | CM-8: khi parse plan hỏng cả sau salvage, chạy 1 vòng LLM-repair (model tự sửa JSON) rồi parse lại. `0` = tắt. Prompt version log qua `content_director` (`CONTENT_PLAN_PROMPT_VERSION`) |
| `CONTENT_ENCODER` | `cpu` | W5-7: encoder cho scene-mux burn + xfade assembler của Content Mode. `cpu` (mặc định) = libx264 (byte-identical). `auto`/`nvenc` = **opt-in** dùng `h264_nvenc` khi GPU sẵn sàng (qua `_run_ffmpeg_with_retry` → tự khoá `NVENC_SEMAPHORE`, cap dùng chung). **Đo trên RTX 3060: KHÔNG speedup (0.86–1.01×)** — scene content filter-bound + tranh session NVENC với clip render → default để CPU. `content_background` LUÔN CPU bất kể biến này |
| `OPENAI_CONTENT_MAX_TOKENS` | `8192` | Token tối đa cho plan Content (lớn hơn story vì plan nhiều scene) |
| `OPENAI_CONTENT_TEMPERATURE` | `0.5` | Nhiệt độ plan Content (OpenAI) |
| `CLAUDE_CONTENT_MAX_TOKENS` | `8192` | Token tối đa cho plan Content (Claude) |
| `CLAUDE_CONTENT_TEMPERATURE` | `0.5` | Nhiệt độ plan Content (Claude) |
| `CLAUDE_CONTENT_CACHE` | `1` | Prompt caching (ephemeral) cho lời gọi plan Content của Claude |

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
| `CONTENT_RESUME_KEEP_HOURS` | `72` | CM-4: giữ thư mục temp của job `interrupted`/`paused` (theo mtime) để `/resume` tái dùng scene đã render, thay vì render lại. Quá hạn vẫn prune (plan còn trong DB). `0` = tắt (hành vi trước CM-4) |
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

## 11. Story Mode (`render_format="story"`)

> Bổ sung 2026-07-11 (grep `os.getenv("STORY_...")` toàn `backend/app`). Story Mode
> v2 = orchestrator riêng ([story_pipeline_v2.py](../backend/app/features/render/engine/pipeline/story_pipeline_v2.py)),
> tách hoàn toàn khỏi clips/recap/content. Mỗi tối ưu có kill-switch riêng — đặt
> `=0`/`=1` (tuỳ chiều) để rollback về hành vi cũ.

### Planning (super-plan)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_COMPILER` | `1` (on) | **GĐ1 Story Compiler** — plan qua 3 call: Understanding (facts + quote-verify) → Writer (kịch bản văn xuôi screenplay-lite, KHÔNG JSON) → Structure (đổ khuôn StoryPlan). Kèm validator định thức giữa các pass + 1 vòng repair kịch bản có chủ đích. `0` = về đường 1-call cũ, bit-identical (prompt s24, schema cũ, multiline off khi unset) |
| `STORY_SCRIPT_REPAIR` | `1` | (Compiler) 1 vòng Writer-repair khi kịch bản thiếu MAJOR event (targeted — chỉ nêu event thiếu). `0` = tắt |
| `OPENAI_STORY_WRITER_MAX_TOKENS` / `_TEMPERATURE` | `16384` / `0.8` | Budget + nhiệt call Writer (prose) — tương tự `GEMINI_STORY_WRITER_*`, `CLAUDE_STORY_WRITER_*` |
| `STORY_READINESS_GATE` | `1` (on) | **GĐ4b** — Production Readiness Validator chạy trước khi tốn ảnh/TTS/encode (8 nhóm: content/continuity/identity/background/composition/tts/duration/storage). FAIL-set tối thiểu (timeline rỗng, không visual, thư mục xuất không ghi được, đĩa <`STORY_MIN_FREE_GB_FAIL`=1GB) mới chặn render; còn lại WARNING lên monitor + `/plan` (field `readiness`). `0` = chỉ log |
| `STORY_TTS_REUSE` / `STORY_CUE_REUSE` | `1` / `1` | **GĐ4c targeted reuse** — resume KHÔNG TTS lại beat đã có audio hợp lệ trên đĩa và KHÔNG encode lại cue clip đã xong (gián đoạn giữa chừng chỉ làm phần thiếu). `0` = làm lại toàn bộ như trước |
| `STORY_CHAR_RESOLVER` | `1` (on) | **GĐ3** — engine gán asset nhân vật DETERMINISTIC từ kho thật (hard-filter giới tính + chấm điểm mô tả VI→EN + UNIQUE — 2 nhân vật không trùng mặt) thay vì AI tự chọn slug; prompt chỉ còn mục BACKGROUNDS; identity lock xuyên chương qua `characters.asset_slug` (migration 0026); trạng thái per-character (`matched_exact/matched/needs_approval/missing`) trả về `/plan`+`/validate` (`asset_resolution`) và hiện chip ở Review. `0` = về AI-pick cũ |
| `STORY_AI_PROVIDER` | `openai` | Provider chạy super-plan (ghi đè bằng `ai_provider` trong payload) |
| `STORY_SUPER_MODEL` | `gpt-4o` | Model super-plan |
| `STORY_PLAN_REPAIR` | `1` | Chạy 1 vòng LLM-repair khi parse plan hỏng (Sacred #3 vẫn None nếu repair fail). `0` = tắt |
| `STORY_MAX_IMAGES` | `15` | **Ceiling** số key-visual/truyện — trần chi phí ảnh (parser cap + gen enforce) |
| `STORY_MAX_SOURCE_CHARS` | `60000` | Cap độ dài truyện nguồn đọc vào prompt |
| `STORY_MAX_CHAPTER_CHARS_SINGLE` | `18000` | (Đường 1-call cũ) trên ngưỡng này → tách 2 super-call nối timeline (chunk-merge). Compiler đọc cả chương trong 1 lần |

> **GĐ1 (2026-07-15):** `STORY_MULTILINE_BEATS` đổi ngữ nghĩa: `1` ép bật, `0` ép tắt,
> **unset = theo `STORY_COMPILER`** (compiler bật → beat mang `lines[]` + nhãn nhịp
> `pace`/`pause`). `/api/story/plan` có bản async: `POST /api/story/plan/async` →
> `{plan_job_id}` + `GET /api/story/plan/async/{id}` (FE dùng mặc định — 3 call
> tuần tự có thể chạy nhiều phút với chương dài).

### Ảnh (visual)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_IMAGE_MODEL` | `gpt-image-1` | Model sinh key-visual (provider `gpt_image`) |
| `STORY_IMAGE_MAX_TIER` | `medium` | Clamp tier tối đa mỗi Visual (`low`/`medium`/`high`) |
| `STORY_MAX_PREMIUM_IMAGES` | `0` (unlimited) | Trần số ảnh **trả phí** (gpt_image); phần dư → nền đặc (fallback). Chặn spend truyện dài |
| `STORY_REFERENCE_SHEETS` | `1` | Reference-sheet nhân vật (Q3) → image-edit giữ nhân vật nhất quán. **Chỉ** provider `gpt_image`; Free bỏ qua. `0` = tắt |
| `STORY_REFSHEET_QUALITY` | `high` | Tier ảnh reference-sheet |
| `STORY_ENV_REFERENCE_SHEETS` | `0` (off) | Reference-sheet **bối cảnh** (G6). Chỉ `gpt_image` + series; opt-in vì tốn thêm 1 ảnh/setting, lợi ích chưa chứng minh |
| `STORY_LIBRARY_FIRST` | `0` (off) | Ưu tiên asset offline (`asset_library/`) khớp theo tên nhân vật/scene TRƯỚC khi gen AI — free + nhất quán. Auto-match nền cho visual char-less (Phase A) |
| `STORY_SVG_GEN` | `0` (off) | Ép **vẽ SVG procedural** (chibi, $0 offline) cho mọi visual, không cần đổi provider. Tương đương `story_image_provider="svg"` toàn cục (Phase B). Lỗi/thiếu `resvg-py` → degrade về gpt-image. FE mặc định đã gửi `svg` nên env này là override thủ công |
| `STORY_THUMBNAIL` | `1` | Sinh thumbnail ở bước finalize. `0` = tắt |

### Lồng tiếng (TTS)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_TTS_ENGINE_OVERRIDE` | `""` | Ép 1 engine cho toàn Story (kill-switch). Rỗng = route theo ngôn ngữ: vi→`gemini`, en/ja→`elevenlabs`, khác→`gemini` (đều fallback về chuỗi edge/piper/xtts) |
| `STORY_ELEVEN_MODEL` | `eleven_multilingual_v2` | Model ElevenLabs (EN/JA) |
| `STORY_ELEVEN_VOICE_FEMALE` | `21m00Tcm4TlvDq8ikWAM` | Voice ID ElevenLabs mặc định (nữ) |
| `STORY_ELEVEN_VOICE_MALE` | `TxGEqnHWrfWFTfGW9XjX` | Voice ID ElevenLabs mặc định (nam) |

### Render / tốc độ

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_RENDER_WORKERS` | `2` | Số luồng render cue song song (libx264/CPU — không đụng NVENC). `1` = serial (rollback byte-identical) |
| `STORY_IMAGE_WORKERS` | `3` | Số luồng sinh ảnh song song (I/O thuần). `1` = serial |
| `STORY_CUE_CRF` | `15` | CRF cue trung gian (near-lossless — Q4 bỏ hình phạt double-encode, xfade là pass chất lượng duy nhất) |
| `STORY_CUE_PRESET` | `veryfast` | Preset libx264 cho cue trung gian |
| `STORY_SOURCE_AUDIO_KEEP_DB` | `-6` | Mức (dB) giữ audio gốc của base video khi beat dùng `source_audio` (A4) |

### Nhạc nền (BGM)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_AUTO_BGM` | `1` | Trộn BGM per-scene (best-effort). `0` = tắt hoàn toàn (về hành vi không nhạc) |
| `STORY_BGM_PLACED` | `1` | s4 placed-BGM (nhạc đặt đúng chỗ intro/outro/under/none mỗi beat). `0` = về mood-runs liên tục (legacy) |

### Series memory (G1 — nhiều chương)

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `STORY_SERIES_MEMORY` | `1` | Ghi/đọc canonical characters + rolling summary để chương sau ground trên chương trước. No-op khi `story_series_id` rỗng |
| `STORY_SERIES_CONTEXT_CHARS` | `4000` | Cap ký tự prior-context nạp vào super-plan chương sau |
| `STORY_SERIES_SUMMARY_CHARS` | `1500` | Cap ký tự rolling summary lưu mỗi chương |
| `STORY_SERIES_SUMMARY_SECTION_CHARS` | `2000` | Cap ký tự mỗi section khi dựng summary |

> Lưu ý: nhiều biến không có "mặc định" trong bảng nghĩa là giá trị mặc định nằm
> sâu trong module liên quan; tra trực tiếp `os.getenv(...)` tại file đó khi cần
> con số chính xác.
