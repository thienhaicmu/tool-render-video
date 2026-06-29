# AI Integration — AI Video Render Studio

> Cập nhật 2026-06-29 từ source. Vùng **HIGH**. Quy tắc an toàn AI là tuyệt đối.

## 1. Vai trò của AI

AI (LLM cloud) là **người quyết định chọn cảnh**: nhận transcript (SRT từ
Whisper) + ngữ cảnh creator, rồi phát ra một **RenderPlan** (danh sách clip +
chính sách phụ đề + chiến lược camera + audio plan + overlay). Render engine là
bộ thực thi thuần — không tự quyết nội dung.

```
Video local → Whisper (SRT) → Creator Context Builder
            → AI Director (Gemini/OpenAI/Claude) → RenderPlan
            → Render Engine (executor)
```

AI là **tuỳ chọn**: nếu không có API key hoặc AI lỗi/trả None, pipeline fallback
sang logic suy từ payload (giữ nguyên hành vi cũ — Sacred Contract #2).

## 2. Vị trí canonical

Tất cả import phải trỏ thẳng đường dẫn canonical — **không có shim**:

```
backend/app/features/render/ai/
├── llm/
│   ├── __init__.py        # dispatcher: select_render_plan(provider=...)
│   ├── providers/         # gemini.py, openai.py, claude.py
│   ├── parser.py          # parse phản hồi LLM
│   ├── prompts.py         # template prompt (an toàn format là then chốt)
│   ├── retry.py           # retry có kiểm soát
│   ├── cache.py           # cache phản hồi LLM
│   └── rewrite.py / rewrite_prompts.py / rewrite_parser.py  # viết lại phụ đề
├── context/builder.py     # dựng creator-context cho prompt
├── feedback/signals.py    # tín hiệu từ rating người dùng (bias chọn clip)
├── visibility/            # tóm tắt khả năng quan sát AI vào result_json
├── dependencies.py        # cờ availability cho dep tuỳ chọn
├── diagnostics.py         # GET /api/render/ai-diagnostics
└── tracing.py
```

## 3. Quy tắc AN TOÀN AI (tuyệt đối — Sacred Contract #3)

> Mọi hàm public trong `backend/app/features/render/ai/**` (và `app/ai/**` nếu
> có) phải **bắt mọi exception và trả `None`** khi lỗi. **Không bao giờ** để
> exception lan ra ngoài.

Lý do: pipeline gọi module AI giữa lúc render. Một exception chưa bắt → job
render abort, mất toàn bộ công sức, có thể làm hỏng thread state của job khác.
`return None` báo pipeline dùng fallback và tiếp tục.

```python
# ĐÚNG
def analyze(self, data):
    try:
        return self._run_inference(data)
    except Exception:
        return None   # caller dùng fallback

# SAI — lan exception ra ngoài, giết job
def analyze(self, data):
    return self._run_inference(data)
```

## 4. Dependency tuỳ chọn

- Package suy luận AI tuỳ chọn (torch, transformers, …) **chỉ** nằm trong
  `requirements-ai.txt`. Không thêm vào `requirements.txt`.
- Module AI phải **import được kể cả khi thiếu dep**. Dùng lazy import + cờ:

```python
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

def run_model(x):
    if not _TORCH_AVAILABLE:
        return None
    ...
```

Vi phạm → cả FastAPI fail khởi động, không render được gì.

SDK provider (`google-genai`, `openai`, `anthropic`) cũng lazy-import trong từng
provider để thiếu extra không làm chết startup.

## 5. RenderPlan (contract AI → engine)

Dataclass thuần tại `backend/app/domain/render_plan.py` (không I/O, không SDK).
Schema hiện tại `SCHEMA_VERSION = 1`.

```
RenderPlan
├── schema_version: int = 1
├── clips: list[ClipPlan]
│     start, end, rank, score, clip_name, title, reason,
│     hook_type, content_type, subtitle_style,
│     viral_score, hook_score, retention_score, speech_density,
│     duration_fit, cover_offset_ratio, pacing, hook_intensity
├── subtitle_policy: SubtitlePolicy  (style, market, emphasis_pass, subtitle_mode)
├── camera_strategy: CameraStrategy  (motion_aware_crop, reframe_mode, tracker)
├── audio_plan: AudioPlan            (voice_*, bgm_*, cta_audio)
└── overlays: list[dict]             (kind=hook|cta, text, ...)
```

Quy tắc baked-in:
- **Mọi field có default an toàn** — nạp payload cũ thiếu field là no-op, không lỗi
  (Contract #2). Chuỗi rỗng = "inherit", backend resolver là authority.
- **`from_json` phòng thủ tuyệt đối**: None/rỗng/JSON hỏng → trả `None`; key lạ bị
  bỏ; field thiếu về default; **không bao giờ raise** (tinh thần Contract #3).
- **`to_json` xác định** (sorted keys, compact) → blob lưu DB ổn định.

Persist trong cột `jobs.render_plan_json` (xem [DATABASE.md](DATABASE.md)). Khi
resume/retry, plan được nạp lại để bỏ qua call LLM (tiết kiệm latency + token).

## 6. Dispatcher & provider

`ai/llm/__init__.py::select_render_plan(provider, srt_content, output_count,
min_sec, max_sec, video_duration, api_key, model, language, editorial_hint,
target_duration, clip_lock, clip_exclude, target_platform, video_type,
hook_strength, ai_target_market, subtitle_emphasis, multi_variant,
structure_bias)`.

- Provider hỗ trợ: `gemini` | `openai` | `claude`.
- Provider mặc định server: `AI_PROVIDER_DEFAULT` (mặc định `gemini`).
- Resolve API key theo thứ tự: key trong payload → env fallback
  (`GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY`).
- `LLM_FALLBACK_ENABLED` cho phép thử provider khác khi provider chính lỗi.

## 7. Cache plan LLM

`pipeline_cache.py` (`_llm_plan_cache_key/get/put`): bỏ qua call API khi cùng nội
dung + cùng tham số đã render trước đó. Key gồm: hash SRT, output_count, min/max
sec (đã scale theo platform speed), platform, provider, model, editorial_hint,
target_duration, clip_lock/exclude, language, và các creator preference
(video_type, hook_strength, ai_target_market, subtitle_emphasis, multi_variant,
structure_bias). Đổi bất kỳ giá trị nào → cache miss.

## 8. Prompt & parser

- `prompts.py`: template + `check_srt_truncation()` cảnh báo khi transcript bị cắt
  (giới hạn `*_MAX_SRT_CHARS` theo provider). An toàn `.format()` là then chốt —
  ký tự `{}` trong nội dung phải được escape.
- `parser.py`: parse phản hồi thành RenderPlan/segment, phòng thủ trước JSON lệch.

## 9. Cờ điều khiển AI (env)

| Env | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `LLM_EMIT_RENDER_PLAN` | `1` | Bật AI emit RenderPlan đầy đủ. `0` = fallback payload-derived |
| `AI_PROVIDER_DEFAULT` | `gemini` | Provider cho job mới |
| `LLM_FALLBACK_ENABLED` | — | Cho phép fallback provider khi lỗi |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY` | — | Key env fallback |
| `GEMINI_DEFAULT_MODEL` / `GEMINI_THINKING_BUDGET` / `GEMINI_REQUEST_TIMEOUT` | — | Tinh chỉnh Gemini |
| `*_MAX_SRT_CHARS` | — | Giới hạn ký tự SRT gửi LLM theo provider |
| `LLM_WHISPER_MODEL` / `LLM_WHISPER_AUTO_SELECT` / `LLM_WHISPER_TIMEOUT_MULT` | — | Whisper trong nhánh LLM |
| `REWRITE_MAX_INPUT_CHARS` / `PROMPTS_MAX_SRT_CHARS` | — | Giới hạn input rewrite/prompt |

Danh sách env đầy đủ: [CONFIGURATION.md](CONFIGURATION.md).
