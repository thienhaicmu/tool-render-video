# AI Integration

## Overview

Two LLM calls per render job when `LLM_EMIT_RENDER_PLAN=1` (default ON):

| Call | Function | Returns | Used for |
|------|----------|---------|---------|
| Call 1 | `select_segments()` | `list[LLMSegment]` | Initial segment selection |
| Call 2 | `select_render_plan()` | `RenderPlan` | Full render config |

When Call 2 returns a valid `RenderPlan`, `_scored_from_render_plan()` converts it to `scored[]`, **overwriting** the Call 1 result. Call 1 serves as fallback when Call 2 fails.

Transcription (Whisper) is NOT an LLM call — it runs locally offline.

---

## Module Structure

```
backend/app/features/render/ai/
└── llm/
    ├── __init__.py        Dispatcher (select_segments, select_render_plan)
    ├── parser.py          Response parsing (LLMSegment, RenderPlan parsing)
    ├── prompts.py         Prompt builders (build_segment_prompt, build_render_plan_prompt)
    └── providers/
        ├── gemini.py      Google Gemini implementation
        ├── openai.py      OpenAI GPT implementation
        └── claude.py      Anthropic Claude implementation

backend/app/ai/llm/__init__.py   Compat shim — re-exports from features/render/ai/llm/
```

---

## Providers

### Google Gemini (`providers/gemini.py`)

| Parameter | Value |
|-----------|-------|
| Default model | `gemini-2.5-flash` |
| Model override | `AI_CLOUD_MODEL` env var |
| Max SRT chars | 60,000 (`GEMINI_MAX_SRT_CHARS`) |
| Request timeout | 120s (`GEMINI_REQUEST_TIMEOUT`) |
| API key | `GEMINI_API_KEY` env var or `payload.gemini_api_key` |
| Library | `google.genai.Client` |

### OpenAI (`providers/openai.py`)

| Parameter | Value |
|-----------|-------|
| Default model | `gpt-4o-mini` |
| Max SRT chars | 30,000 (`OPENAI_MAX_SRT_CHARS`) |
| API key | `OPENAI_API_KEY` env var |
| Library | `openai.OpenAI` |

### Anthropic Claude (`providers/claude.py`)

| Parameter | Value |
|-----------|-------|
| Default model | `claude-3-5-sonnet-20241022` |
| Max SRT chars | 50,000 (`CLAUDE_MAX_SRT_CHARS`) |
| API key | `CLAUDE_API_KEY` env var |
| Library | `anthropic.Anthropic` |

---

## Call 1 — Segment Selection

**Prompt builder:** `build_segment_prompt()` in `prompts.py`

**Input:** SRT file content (timestamps converted to `[83.5 - 123.1]` format, saving ~50% tokens), `output_count`, `min_sec`, `max_sec`, `video_duration`.

**Expected output:**
```json
{
  "segments": [
    {
      "start": 83.5,
      "end": 123.1,
      "viral_score": 85,
      "hook_score": 72,
      "retention_score": 68,
      "content_type": "interview",
      "hook_type": "question",
      "subtitle_style": "viral",
      "speech_density": 0.8,
      "duration_fit_score": 0.9,
      "ai_subtitle_style": "viral",
      "cover_hint_ratio": 0.3
    }
  ]
}
```

**Parser:** `parse_segment_response()` in `parser.py` — defensive, never raises. Handles markdown fences, wrapped JSON objects, and raw arrays.

**`LLMSegment` dataclass fields:**
- `start`, `end` — seconds (float)
- `viral_score`, `hook_score`, `retention_score` — 0-100
- `content_type` — `"interview"` / `"vlog"` / `"tutorial"` / `"montage"`
- `hook_type` — `"question"` / `"reveal"` / `"contrast"` / `"humor"`
- `subtitle_style` — `"viral"` / `"clean"` / `"story"` / `"gaming"` / `""`
- `speech_density` — 0.0-1.0
- `duration_fit_score` — 0.0-1.0
- `cover_hint_ratio` — 0.0-1.0 (thumbnail time offset advisory)
- `title`, `reason` — strings

---

## Call 2 — RenderPlan Emission

**Prompt builder:** `build_render_plan_prompt()` in `prompts.py`

**Expected output:**
```json
{
  "clips": [...],
  "subtitle_policy": {...},
  "camera_strategy": {...},
  "audio_plan": {...},
  "output_config": {...},
  "overlays": []
}
```

**Parser:** `parse_render_plan_response()` in `parser.py` → `RenderPlan.from_json()` in `domain/render_plan.py`. Both defensive, never raise.

---

## RenderPlan Domain Object

**File:** `backend/app/domain/render_plan.py`

### RenderPlan

```python
@dataclass
class RenderPlan:
    schema_version: int = 1
    clips: list[ClipPlan] = []
    subtitle_policy: SubtitlePolicy = SubtitlePolicy()
    camera_strategy: CameraStrategy = CameraStrategy()
    audio_plan: AudioPlan = AudioPlan()
    output_config: OutputConfig = OutputConfig()
    overlays: list[dict] = []
    creator_context_id: str = ""
```

### ClipPlan

| Field | Type | Consumer |
|-------|------|---------|
| `start` | float | `part_cut.py` — segment start time (seconds) |
| `end` | float | `part_cut.py` — segment end time (seconds) |
| `rank` | int | `pipeline_ranking.py:_resolve_rank_from_plan()` |
| `score` | float | `_scored_from_render_plan()` → `viral_score` if missing |
| `viral_score` | float | `_scored_from_render_plan()` → output scoring |
| `hook_score` | float | `_scored_from_render_plan()` → output scoring |
| `retention_score` | float | `_scored_from_render_plan()` → output scoring |
| `title` | str | `pipeline_finalize.py` → `result_json` |
| `reason` | str | `pipeline_finalize.py` → `result_json` |
| `subtitle_style` | str | `part_asset_planner.py` → subtitle style tier 2 |
| `content_type` | str | `pipeline_ranking.py` → ranking reason |
| `hook_type` | str | `pipeline_ranking.py` → ranking reason |
| `speech_density` | float | `_scored_from_render_plan()` → ranking weight |
| `duration_fit` | float | `_scored_from_render_plan()` → ranking weight |
| `cover_offset_ratio` | float | `_scored_from_render_plan()` → `cover_hint_ratio` in seg dict |
| `clip_name` | str | `_scored_from_render_plan()` → internal name |

### SubtitlePolicy

| Field | Type | Consumer |
|-------|------|---------|
| `style` | str | `part_asset_planner.py` — global style override (tier 1) |
| `market` | str | `part_asset_planner.py` — market / locale override |
| `emphasis_pass` | bool | `part_asset_planner.py` — extra emphasis effects |
| `line_break_rule` | str | `part_asset_planner.py` — market-specific line breaking |

### CameraStrategy

| Field | Type | Consumer |
|-------|------|---------|
| `motion_aware_crop` | bool | `part_render_setup.py` — override `payload.motion_aware_crop` |
| `reframe_mode` | str | `part_render_setup.py` — `"center"` / `"track"` / `"fixed"` |
| `tracker` | str | `part_render_setup.py` — `"bytetrack"` / `"trackerless"` / `"legacy"` |

### AudioPlan

| Field | Type | Consumer |
|-------|------|---------|
| `voice_enabled` | bool | `part_voice_mix.py` — override `payload.voice_enabled` |
| `voice_provider` | str | `part_voice_mix.py` — `"xtts"` / `"edge"` |
| `bgm_enabled` | bool | `part_voice_mix.py` — background music |
| `cta_audio` | str | `part_voice_mix.py` — CTA audio file path |

### OutputConfig

| Field | Type | Consumer |
|-------|------|---------|
| `codec` | str | `part_render_encode.py` — `"h264"` / `"h265"` |
| `preset` | str | `part_render_encode.py` — FFmpeg preset |
| `crf` | int | `part_render_encode.py` — quality (0-51) |
| `fps` | int | `part_render_encode.py` — frame rate |
| `width`, `height` | int | `part_render_encode.py` — resolution |

---

## Subtitle Style Resolution (5-Tier)

In `part_asset_planner.py`, the final subtitle style is resolved in priority order:

```
Tier 1 (highest): RenderPlan.subtitle_policy.style          (global override)
Tier 2:           seg["subtitle_style"] from ClipPlan        (per-clip AI choice)
Tier 3:           seg["ai_subtitle_style"] from Call 1        (legacy segment field)
Tier 4:           payload.subtitle_style                      (user choice)
Tier 5:           platform bias + content_type default        (heuristic fallback)
```

---

## Output Ranking Weights

In `pipeline_ranking.py`:

```
output_rank_score =
    viral_score      × 0.35
  + hook_score       × 0.20
  + retention_score  × 0.20
  + speech_density   × 0.10
  + market_score     × 0.10
  + duration_fit     × 0.05
```

AI ranks from `ClipPlan.rank` take precedence over score-based sort when `LLM_EMIT_RENDER_PLAN=1`.

---

## Sacred Contract #3 — AI Never Crashes Render

Every public function in `features/render/ai/**` and `ai/**` must:

```python
def select_render_plan(...) -> Optional[RenderPlan]:
    try:
        # ... AI call ...
        return RenderPlan(...)
    except Exception:
        logger.warning("...")
        return None  # ALWAYS return None, NEVER raise
```

Returning `None` causes the orchestrator to use fallback behavior. Raising an exception terminates the active render job with no recovery path.

---

## Lazy Optional Dependencies

AI providers must not crash FastAPI startup if optional libraries are absent:

```python
# Correct pattern
try:
    import google.genai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

def select_render_plan(...):
    if not _GENAI_AVAILABLE:
        return None
    ...
```

AI extras live in `requirements-ai.txt`, NOT `requirements.txt`.
