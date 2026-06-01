"""
constants.py — Named constants cho toàn bộ v2.

Quy tắc:
- Tất cả magic numbers phải có tên ở đây
- Nhóm theo domain, comment giải thích đơn vị
- Không import từ bất kỳ module v2 nào khác
"""

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_DEFAULT_MODEL    = "llama-3.1-8b-instant"
GROQ_MAX_SRT_CHARS    = 12_000    # ký tự — ~3000 tokens, tránh vượt context window
GROQ_MAX_TOKENS       = 1_024     # tokens response tối đa
GROQ_TEMPERATURE      = 0.2       # thấp → output ổn định, ít sáng tạo
GROQ_REQUEST_TIMEOUT  = 30        # giây

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_DEFAULT_MODEL = "small"   # balance: tốc độ vs độ chính xác
WHISPER_LANGUAGE_AUTO = "auto"

# ── Segment constraints ───────────────────────────────────────────────────────
MIN_PART_DURATION_SEC  = 15.0     # giây — ngắn hơn thì không đủ nội dung
MAX_PART_DURATION_SEC  = 60.0     # giây — dài hơn thì không phù hợp short-form
DEFAULT_OUTPUT_COUNT   = 5        # số clip output mặc định
MAX_OUTPUT_COUNT       = 20

# ── Render ────────────────────────────────────────────────────────────────────
MAX_CONCURRENT_PARTS   = 4        # ThreadPoolExecutor workers
FFMPEG_TIMEOUT_SEC     = 300      # giây — timeout cho 1 FFmpeg call
NVENC_MAX_SESSIONS     = 3        # giới hạn cứng của GPU NVENC consumer

# ── QA / Output validation ────────────────────────────────────────────────────
MIN_OUTPUT_FILE_BYTES  = 1_000_000  # 1 MB — nhỏ hơn = corrupt / truncated
MIN_OUTPUT_DURATION_SEC = 3.0       # giây — ngắn hơn = render lỗi

# ── Platform ──────────────────────────────────────────────────────────────────
PLATFORM_TIKTOK         = "tiktok"
PLATFORM_REELS          = "reels"
PLATFORM_YOUTUBE_SHORT  = "youtube_short"
SUPPORTED_PLATFORMS     = {PLATFORM_TIKTOK, PLATFORM_REELS, PLATFORM_YOUTUBE_SHORT}

# ── Video ─────────────────────────────────────────────────────────────────────
DEFAULT_ASPECT_RATIO   = "9:16"   # vertical short-form
DEFAULT_VIDEO_CODEC    = "h264"
DEFAULT_CRF            = 23
