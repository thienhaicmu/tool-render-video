Tốt. Tôi đã có đủ thông tin. Bây giờ viết plan chi tiết.

---

# IMPLEMENTATION PLAN — AI Rewrite Subtitle for TTS Narration

**Feature:** `voice_source = "ai_rewrite"`
**Pattern:** Option A per-provider symmetric — clone `select_render_plan` LLM Call 1 organization (prompts + parser + dispatcher + 3 providers + cache + retry + metrics).
**Build target:** Pipeline ko-thay-đổi cho LLM Call 1; nhánh mới chỉ chạy trong `part_voice_mix.py`.
**Estimated LOC delta:** ~600 LOC backend + ~50 LOC frontend + ~400 LOC tests.

---

## Section 1: Risk classification + gate enforcement

### 1.1 Risk tier per file

| File | Risk Tier | Notes |
|---|---|---|
| `backend/app/features/render/ai/llm/rewrite_prompts.py` (NEW) | **LOW** | Pure function, isolated |
| `backend/app/features/render/ai/llm/rewrite_parser.py` (NEW) | **LOW** | Pure function, defensive |
| `backend/app/features/render/ai/llm/rewrite.py` (NEW) | **LOW** | Dispatcher, mirrors existing `__init__.py` |
| `backend/app/features/render/ai/llm/providers/gemini.py` (EDIT) | **MEDIUM** | Adds new public function; existing code untouched |
| `backend/app/features/render/ai/llm/providers/openai.py` (EDIT) | **MEDIUM** | Idem |
| `backend/app/features/render/ai/llm/providers/claude.py` (EDIT) | **MEDIUM** | Idem |
| `backend/app/models/render.py` (EDIT) | **HIGH** | Field + validator; chạm Sacred #2 nếu sai default |
| `backend/app/models/render_public.py` (EDIT) | **HIGH** | FE_FACING_FIELDS pin; cần update test count |
| `backend/app/models/render_field_groups.py` (EDIT) | **MEDIUM** | Partition test sẽ vỡ nếu thiếu field |
| `backend/app/features/render/engine/stages/part_voice_mix.py` (EDIT) | **HIGH** | Sacred #3 + #6 contracts; chạm pipeline live |
| `backend/app/services/metrics.py` (EDIT) | **LOW** | Pure additive histograms |
| `frontend/src/features/clip-studio/render/steps/StepConfigure.tsx` (EDIT) | **LOW** | UI seg option + conditional textarea |
| `frontend/src/features/clip-studio/render/i18n.ts` (EDIT) | **LOW** | Add 3 keys × 2 langs |
| `frontend/src/types/api.ts` (EDIT) | **MEDIUM** | Union type extension; tied to FE_FACING_FIELDS test |
| `frontend/src/features/clip-studio/render/types.ts` (EDIT) | **LOW** | Cfg type extension |
| `frontend/src/features/clip-studio/render/RenderWorkflow.tsx` (EDIT) | **LOW** | buildPayload: thêm `rewrite_tone` field |

### 1.2 Required approval flow

- HIGH-tier edit (render.py, render_public.py, part_voice_mix.py) **phải có lead review** trước commit.
- MEDIUM-tier có thể self-review nếu test coverage đủ.

### 1.3 Pre-implementation baseline

```powershell
# Đếm test pass baseline trước edit:
cd d:\tool-render-video\backend
python -m pytest tests/ --tb=no -q 2>&1 | Select-String -Pattern "passed|failed|error" | Select-Object -Last 5

# Ghi lại con số (kỳ vọng XXX passed, 0 failed). Plan post-edit:
# = baseline_passed + 4 test file mới × ~6-10 tests = +30-40 tests
```

---

## Section 2: Sacred Contracts compliance checklist

| Contract | Status | Evidence |
|---|---|---|
| **#1 — DB schema immutability** | UNTOUCHED | Không migration, không bảng mới |
| **#2 — Default behavior unchanged** | COMPLIES | `voice_source` default vẫn `"manual"`; `rewrite_tone` default `""`; nhánh mới chỉ chạy khi user explicitly chọn `"ai_rewrite"` |
| **#3 — AI return-None contract** | COMPLIES | `rewrite_subtitle()` returns `Optional[str]`; mọi exception → None (try/except wrap); `part_voice_mix.py` nhánh mới có fallback to original text khi None |
| **#4 — Pipeline ordering** | UNTOUCHED | Không sửa pipeline_config / stage order |
| **#5 — Permissive parser** | COMPLIES | `parse_rewrite_response` defensive (strip fences, strip prose, never raises) |
| **#6 — `_emit_render_event` keyword-only** | COMPLIES | Nhánh mới giữ pattern `_emit_render_event(channel_code=..., job_id=..., event=..., level=..., ...)` |
| **#7 — Sole DB writer** | UNTOUCHED | Không gọi `upsert_job_part` hay DB writes mới |
| **#8 — Cancel-token check** | COMPLIES | Reuse existing `ctx.cancel_registry.is_cancelled` check trước TTS call (same pattern as subtitle branch line 245-246) |

---

## Section 3: File-by-file change spec (in dependency DAG order)

### 3.1 NEW: `d:\tool-render-video\backend\app\features\render\ai\llm\rewrite_prompts.py`

**Purpose:** Build `(system, user)` prompt cho rewrite call.

**Module surface:**

```python
"""rewrite_prompts.py — Prompt template for AI subtitle rewrite for TTS.

Mirrors prompts.py organization but for a different LLM call: rewrite
the per-part transcript text into TTS-friendly narration that fits a
target duration in seconds. Used by app.features.render.ai.llm.rewrite.
"""
from __future__ import annotations
import os as _os

# Word-per-minute rate per language (avg adult narrator pace).
# Used to compute word budget = (target_duration_sec / 60) * wpm.
# Conservative (10% under typical) so TTS doesn't over-run.
_WPM_BY_LANG: dict[str, int] = {
    "vi-VN": 140,   # Vietnamese — syllable-heavy, slower
    "en-US": 150,   # American English
    "en-GB": 145,   # British English
    "ja-JP": 200,   # Japanese mora count
    "ko-KR": 180,   # Korean
}
_DEFAULT_WPM = 150  # fallback for unrecognised language

# Hard cap on input transcript chars sent to the LLM (rewrite call).
# Per-part SRTs are short (~15-90 sec → ~50-500 chars), so cap at 4000
# to cover the long tail and reject pathologically long inputs.
MAX_REWRITE_INPUT_CHARS = int(_os.getenv("REWRITE_MAX_INPUT_CHARS", "4000"))


def _compute_word_budget(target_duration_sec: float, target_language: str) -> int:
    """Return target word count from duration + language WPM table.
    Floors at 3 words (TTS sanity); ceils at 800 (sanity)."""
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    budget = int((max(1.0, target_duration_sec) / 60.0) * wpm)
    return max(3, min(800, budget))


_SYSTEM_REWRITE = (
    "You are a TTS narration script writer. Rewrite the input transcript "
    "to be spoken aloud as a voice-over that fits a TARGET DURATION. "
    "Output ONLY the rewritten text — no prose wrappers, no markdown, no "
    "code fences, no explanation. Preserve the meaning; tighten or expand "
    "the wording so a natural narrator finishes within the target time."
)

_USER_TEMPLATE_REWRITE = """Rewrite the transcript below into a TTS-ready narration.

TARGET DURATION: {target_duration_sec:.1f} seconds
TARGET LANGUAGE: {target_language}
TARGET WORD COUNT: about {word_budget} words (a natural narrator at {wpm} wpm fills the duration)
TONE: {tone_clause}

RULES:
  1. Output a single block of plain text. NO bullet lines, NO numbered lists.
  2. NO JSON, NO markdown, NO code fences.
  3. Preserve every key fact and named entity from the source.
  4. Match the target language exactly — do not translate if same language, do translate if different.
  5. Keep the speakable structure: full sentences, natural pauses, no unpronounceable symbols.
  6. NEVER exceed {hard_cap_words} words (= 2× word budget). Cut filler before exceeding.

SOURCE TRANSCRIPT:
{text}

Rewritten narration ({target_language}):"""


def build_rewrite_prompt(
    text: str,
    target_duration_sec: float,
    target_language: str,
    tone: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the rewrite LLM call.

    Inputs are truncated to MAX_REWRITE_INPUT_CHARS so a pathological
    long input doesn't blow the prompt budget. ``tone`` is a free-form
    creator hint ("playful", "dramatic", "informative") rendered into
    the TONE line — empty string defaults to "natural / informative".

    Format safety: the template uses {} placeholders exclusively
    (no literal braces inside the body), so .format() substitution is
    direct — no brace-doubling needed. Tests pin that the format call
    accepts the exact placeholder set without KeyError.
    """
    cleaned = (text or "").strip()
    if len(cleaned) > MAX_REWRITE_INPUT_CHARS:
        cleaned = cleaned[:MAX_REWRITE_INPUT_CHARS] + " [truncated]"
    word_budget = _compute_word_budget(target_duration_sec, target_language)
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    tone_clause = (tone or "").strip() or "natural / informative"
    user = _USER_TEMPLATE_REWRITE.format(
        target_duration_sec=float(target_duration_sec),
        target_language=target_language,
        word_budget=word_budget,
        wpm=wpm,
        tone_clause=tone_clause,
        hard_cap_words=word_budget * 2,
        text=cleaned,
    )
    return _SYSTEM_REWRITE, user
```

**Key contracts:**
- `build_rewrite_prompt(text, target_duration_sec, target_language, tone) -> tuple[str, str]`
- `_compute_word_budget(target_duration_sec, target_language) -> int`
- `MAX_REWRITE_INPUT_CHARS = 4000` (env-overridable)

**Error handling pattern (Sacred #3):** Function never raises (no exception path inside `.format` since all keys present and inputs are strings/floats). Caller wraps in try/except anyway.

---

### 3.2 NEW: `d:\tool-render-video\backend\app\features\render\ai\llm\rewrite_parser.py`

**Module surface:**

```python
"""rewrite_parser.py — Parse rewrite LLM response into a plain narration string.

Defensive: never raises, returns None on any failure. Caller treats None
as signal to fall back to original transcript text (Sacred Contract #3).
"""
from __future__ import annotations
import logging
import re
from typing import Optional

logger = logging.getLogger("app.render.llm_rewrite_parser")

# Strip leading ``` or ```text fences and trailing fences.
_FENCE_RE = re.compile(r"^\s*```(?:[a-z]+)?\s*\n?|\n?\s*```\s*$", re.IGNORECASE)
# Strip common prose wrappers the LLM sometimes prepends.
_PROSE_PREFIX_RE = re.compile(
    r"^\s*(here is|here's|sure[,!:]?|certainly[,!:]?|rewritten narration[:\s]*|narration[:\s]*)",
    re.IGNORECASE,
)


def parse_rewrite_response(
    raw: str,
    target_duration_sec: float,
    word_budget: int,
) -> Optional[str]:
    """Parse the LLM's rewrite response into a clean narration string.

    Defensive rules applied in order:
      1. Coerce input to str; strip whitespace.
      2. Strip ```...``` code fences (leading + trailing).
      3. Strip common prose prefixes ("Here is the rewritten ...").
      4. Reject empty / whitespace-only output.
      5. Reject output exceeding 2× word_budget (sanity check — model
         ignored the hard cap rule; safer to fall back).
      6. Collapse runs of internal whitespace to single space.

    Returns ``None`` on any failure (Sacred Contract #3). On success
    returns the cleaned narration text ready for ``generate_narration_audio``.
    """
    try:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        # Strip code fences (start + end).
        text = _FENCE_RE.sub("", text).strip()
        text = _FENCE_RE.sub("", text).strip()  # in case both ends fenced
        # Strip prose prefix (one pass — only the first occurrence).
        text = _PROSE_PREFIX_RE.sub("", text, count=1).strip()
        if not text:
            logger.warning("rewrite_parser: empty after fence/prose strip")
            return None
        # Sanity check: word count vs 2× budget.
        word_count = len(text.split())
        if word_count > max(20, word_budget * 2):
            logger.warning(
                "rewrite_parser: rejected — %d words > 2× budget (%d). Preview: %r",
                word_count, word_budget, text[:200],
            )
            return None
        # Collapse internal whitespace.
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as exc:
        logger.warning("rewrite_parser: unexpected error — %s", exc, exc_info=True)
        return None
```

**Error handling pattern (Sacred #3):** Outer try/except → None. All branches return None on failure.

---

### 3.3 NEW: `d:\tool-render-video\backend\app\features\render\ai\llm\rewrite.py`

**Public dispatcher — mirrors `__init__.py:select_render_plan`.**

```python
"""rewrite — multi-provider LLM dispatch for TTS subtitle rewrite.

Routes rewrite_subtitle() to the right provider implementation by name.
Each provider module exposes rewrite_subtitle(...) returning Optional[str].

Supported providers: gemini, openai, claude (mirrors __init__.py).
"""
from __future__ import annotations
import logging
import os
import time as _time
from typing import Optional

logger = logging.getLogger("app.render.llm.rewrite")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"
_LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "1") == "1"


def _get_provider_rewrite_impl(provider_name: str):
    """Return the rewrite_subtitle callable for the named provider."""
    if provider_name == "gemini":
        from app.features.render.ai.llm.providers.gemini import rewrite_subtitle as _impl
    elif provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import rewrite_subtitle as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import rewrite_subtitle as _impl
    else:
        logger.warning(
            "rewrite: provider %r not in %s — falling back to gemini",
            provider_name, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import rewrite_subtitle as _impl
    return _impl


def rewrite_subtitle(
    *,
    provider: str = DEFAULT_PROVIDER,
    text: str,
    target_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[str]:
    """Dispatch subtitle-rewrite to the named LLM provider.

    Returns the rewritten narration string, or None on any failure.
    Sacred Contract #3 — provider modules catch all exceptions; this
    function adds the fallback chain wrapper.

    When LLM_FALLBACK_ENABLED=1 and primary returns None, the
    remaining SUPPORTED_PROVIDERS are tried in order until one
    succeeds (matches behaviour of select_render_plan dispatcher).
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        logger.warning("rewrite: provider %r unsupported — using gemini", provider)
        primary = "gemini"
    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]
    kwargs = dict(
        text=text,
        target_duration_sec=target_duration_sec,
        target_language=target_language,
        tone=tone,
        api_key=api_key,
        model=model,
    )
    for _p in chain:
        _impl = _get_provider_rewrite_impl(_p)
        _t0 = _time.perf_counter()
        result = _impl(**kwargs)
        _status = "success" if result else "empty"
        try:
            from app.services.metrics import (
                LLM_REWRITE_CALLS, LLM_REWRITE_LATENCY, LLM_REWRITE_CHAR_DELTA,
            )
            LLM_REWRITE_CALLS.labels(provider=_p, status=_status).inc()
            LLM_REWRITE_LATENCY.labels(provider=_p).observe(_time.perf_counter() - _t0)
            if result:
                delta = len(result) - len(text or "")
                LLM_REWRITE_CHAR_DELTA.labels(provider=_p).observe(delta)
        except Exception:
            pass
        if result:
            if _p != primary:
                logger.info(
                    "rewrite: fallback succeeded provider=%s (primary=%s None)", _p, primary,
                )
            return result
        logger.warning("rewrite: provider=%s returned None", _p)
    return None
```

**Error handling:** Each provider call is already wrapped (Sacred #3); dispatcher itself never raises (the broad try/except on metrics is conservative).

---

### 3.4 EDIT: `d:\tool-render-video\backend\app\features\render\ai\llm\providers\gemini.py`

**Insertion point:** Append after the existing `_call_gemini` function (currently ends at line 249). Add ~80 LOC at end of file (no edits to existing functions).

**New imports (add at line 19, after `from app.domain.render_plan import RenderPlan`):**

```python
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
```

**New module-level constant (add near line 35 with other `_MAX_*`):**

```python
# Rewrite call uses smaller token budget — narration is short.
_REWRITE_MAX_TOKENS = 2048
```

**New functions (append at EOF, line 250+):**

```python
def rewrite_subtitle(
    text: str,
    target_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[str]:
    """Rewrite per-part transcript into TTS narration sized for target_duration_sec.

    Returns None on any failure (Sacred Contract #3). Uses cache +
    retry pattern identical to select_render_plan.
    """
    try:
        return _run_rewrite(
            text=text,
            target_duration_sec=target_duration_sec,
            target_language=target_language,
            tone=tone,
            api_key=api_key,
            model=model,
        )
    except Exception as exc:
        logger.warning("gemini_client: rewrite_subtitle unexpected error — %s", exc, exc_info=True)
        return None


def _run_rewrite(
    text: str,
    target_duration_sec: float,
    target_language: str,
    tone: str,
    api_key: str,
    model: Optional[str],
) -> Optional[str]:
    if not _GENAI_SDK:
        logger.warning("gemini_client: google-genai SDK not installed (rewrite path)")
        return None
    if not api_key:
        logger.warning("gemini_client: no api_key supplied (rewrite path)")
        return None
    if not text or not text.strip():
        logger.warning("gemini_client: empty text (rewrite path)")
        return None
    system_prompt, user_prompt = build_rewrite_prompt(
        text=text,
        target_duration_sec=target_duration_sec,
        target_language=target_language,
        tone=tone,
    )
    resolved_model = model or _DEFAULT_MODEL
    word_budget = _compute_word_budget(target_duration_sec, target_language)
    logger.info(
        "gemini_client: calling rewrite model=%s dur=%.1fs lang=%s tone=%r text_chars=%d budget=%d",
        resolved_model, target_duration_sec, target_language, tone, len(text), word_budget,
    )
    raw = _call_gemini_rewrite(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("gemini_client: empty rewrite response (model=%s)", resolved_model)
        return None
    parsed = parse_rewrite_response(raw, target_duration_sec, word_budget)
    if parsed is not None:
        logger.info(
            "gemini_client: rewrite OK model=%s in_chars=%d out_chars=%d",
            resolved_model, len(text), len(parsed),
        )
    return parsed


def _call_gemini_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Gemini call for rewrite — raises on SDK error. Uses text/plain
    (not JSON) since rewrite output is plain narration."""
    client = _genai.Client(
        api_key=api_key,
        http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000},
    )
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "text/plain",  # NOT json_object — rewrite is plain text
            "temperature": _TEMPERATURE,
            "max_output_tokens": _REWRITE_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_rewrite(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Rewrite call with cache + one-attempt retry. Cache key namespaced by
    provider=gemini-rewrite to avoid collision with select_render_plan cache."""
    cached = llm_cache_get("gemini-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="gemini-rewrite",
    )
    if result is not None:
        llm_cache_put("gemini-rewrite", model, system_prompt, user_prompt, result)
    return result
```

**Cache namespace decision:** Pass `"gemini-rewrite"` (not `"gemini"`) to `llm_cache_get/put` so rewrite responses don't collide with select_render_plan responses on the same prompt hash. Verified: `_build_key()` at `cache.py:56-69` hashes provider as a string — any unique value works.

**Error handling (Sacred #3):** Outer `try/except` in `rewrite_subtitle` returns None on any unexpected error. `_call_with_retry` already swallows SDK exceptions.

---

### 3.5 EDIT: `d:\tool-render-video\backend\app\features\render\ai\llm\providers\openai.py`

**Identical structure to 3.4.** Insertion point: append after `_call_openai` (line 217). Add same imports at top.

**Key differences from Gemini:**

```python
def _call_openai_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single OpenAI Chat Completions call for rewrite — raises on SDK error.
    NOTE: no response_format={'type': 'json_object'} — rewrite is plain text."""
    client = _openai.OpenAI(api_key=api_key, timeout=30)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2048,
        temperature=_TEMPERATURE,
        # NO response_format — rewrite returns plain narration text
    )
    return resp.choices[0].message.content


def _call_openai_rewrite(api_key, model, system_prompt, user_prompt):
    cached = llm_cache_get("openai-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_openai_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="openai-rewrite",
    )
    if result is not None:
        llm_cache_put("openai-rewrite", model, system_prompt, user_prompt, result)
    return result
```

`rewrite_subtitle` + `_run_rewrite` functions byte-identical to 3.4 except SDK calls go through `_call_openai_rewrite`.

---

### 3.6 EDIT: `d:\tool-render-video\backend\app\features\render\ai\llm\providers\claude.py`

**Identical structure to 3.4.** Insertion point: append after `_call_claude` (line 225).

**Key differences from Gemini:**

```python
def _call_claude_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Anthropic Messages call for rewrite — raises on SDK error."""
    client = _AnthClient(api_key=api_key, timeout=30)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if not resp.content:
        return None
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "\n".join(parts) if parts else None


def _call_claude_rewrite(api_key, model, system_prompt, user_prompt):
    cached = llm_cache_get("claude-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("claude_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_claude_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="claude-rewrite",
    )
    if result is not None:
        llm_cache_put("claude-rewrite", model, system_prompt, user_prompt, result)
    return result
```

---

### 3.7 EDIT: `d:\tool-render-video\backend\app\models\render.py`

**Two surgical edits.**

**Edit A — Add `rewrite_tone` field after line 205 (between `voice_id` and `subtitle_translate_enabled`):**

Before (lines 203-206):
```python
    voice_text: Optional[str] = None
    voice_source: str = "manual"
    voice_id: Optional[str] = None
    subtitle_translate_enabled: bool = False
```

After (lines 203-207):
```python
    voice_text: Optional[str] = None
    voice_source: str = "manual"
    voice_id: Optional[str] = None
    # AI rewrite (voice_source=="ai_rewrite") — creator-supplied tone hint
    # for the rewrite LLM call. Empty string = "natural / informative" default.
    rewrite_tone: str = ""
    subtitle_translate_enabled: bool = False
```

**Edit B — Update validator at line 512:**

Before (line 512-515):
```python
        if self.voice_source not in {"manual", "subtitle", "translated_subtitle"}:
            raise ValueError("voice_source must be 'manual', 'subtitle', or 'translated_subtitle'")
        if self.voice_source == "manual" and not (self.voice_text or "").strip():
            raise ValueError("voice_text is required when voice_enabled=true and voice_source=manual")
```

After:
```python
        if self.voice_source not in {"manual", "subtitle", "translated_subtitle", "ai_rewrite"}:
            raise ValueError("voice_source must be 'manual', 'subtitle', 'translated_subtitle', or 'ai_rewrite'")
        if self.voice_source == "manual" and not (self.voice_text or "").strip():
            raise ValueError("voice_text is required when voice_enabled=true and voice_source=manual")
```

**Sacred #2 compliance:** `rewrite_tone` defaults to `""` — replayed historical payloads without this field deserialize cleanly (extra="ignore"/Optional handling). `voice_source` allowlist expanded, not narrowed.

---

### 3.8 EDIT: `d:\tool-render-video\backend\app\models\render_public.py`

**Edit at line 92-94 (Voice block in FE_FACING_FIELDS):**

Before:
```python
    # Voice
    "voice_enabled", "voice_language", "voice_gender", "voice_source",
    "voice_text", "tts_engine", "voice_mix_mode",
```

After:
```python
    # Voice
    "voice_enabled", "voice_language", "voice_gender", "voice_source",
    "voice_text", "tts_engine", "voice_mix_mode",
    # AI rewrite (voice_source=="ai_rewrite") — creator-supplied tone hint.
    "rewrite_tone",
```

**Test impact:** `test_render_request_public_surface.py:test_public_field_count_pinned` currently asserts `len(FE_FACING_FIELDS) == 72`. Must update to `73` and `len(BE_ONLY_FIELDS) == 79` and total `153`. Same file's `test_fe_facing_set_matches_typescript_interface` will fail until FE adds `rewrite_tone` to the TS interface — handled in Step 3.13.

---

### 3.9 EDIT: `d:\tool-render-video\backend\app\models\render_field_groups.py`

**Edit at line 77 (voice group):**

Before:
```python
    "voice": frozenset({
        "voice_enabled", "voice_language", "voice_gender", "voice_rate",
        "voice_mix_mode", "voice_text", "voice_source", "voice_id",
        "narration_style",
    }),
```

After:
```python
    "voice": frozenset({
        "voice_enabled", "voice_language", "voice_gender", "voice_rate",
        "voice_mix_mode", "voice_text", "voice_source", "voice_id",
        "narration_style", "rewrite_tone",
    }),
```

**Test impact:** `test_render_field_groups.py:test_every_render_request_field_is_grouped` will fail if `rewrite_tone` is added to RenderRequest but not to a group. This edit fixes that.

---

### 3.10 EDIT: `d:\tool-render-video\backend\app\features\render\engine\stages\part_voice_mix.py`

**Insertion point:** Add new `elif` branch at line 316 (after the `translated_subtitle` branch's closing `)` at line 425, before the `_final_voice_path = ...` line at 426).

Reading: existing branches end at `voice_subtitle_source_missing` emit at line 417-425. The mixer-aggregation line is at 426:
```
_final_voice_path = ctx.voice_audio_path or _part_subtitle_voice_path
```

Insert the new branch between line 425 and 426 (i.e., as a 3rd `elif` of the voice-source selector at lines 226, 316).

**New imports (add at line 92 area near other `from app.features.render.ai...` imports — but note this file has none of those today; add at line 91 after existing block):**

```python
from app.features.render.ai.llm.rewrite import rewrite_subtitle as _llm_rewrite_subtitle
```

**New branch (insert before line 426, after the `translated_subtitle` branch closes at line 425):**

```python
    elif (
        _effective_voice_enabled
        and getattr(ctx.payload, "voice_source", "manual") == "ai_rewrite"
        and ctx.voice_audio_path is None
    ):
        # AI rewrite path — rewrite the per-part transcript into TTS-sized
        # narration using the same provider+model selected for select_render_plan.
        # Sacred Contract #3: any failure → fall back to the original transcript text.
        _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _part_srt_inmem_text: str | None = None
        if _part_srt is None and ctx.full_srt_available:
            try:
                _part_srt_inmem_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                _part_srt = ctx.full_srt
            except Exception:
                _part_srt = None
        if _part_srt:
            _orig_text = _part_srt_inmem_text if _part_srt_inmem_text is not None else extract_text_from_srt(str(_part_srt))
            if _orig_text.strip():
                _target_dur = max(1.0, float(seg["end"]) - float(seg["start"]))
                # Resolve provider + key from payload (same wiring as LLM Call 1).
                _provider = (getattr(ctx.payload, "ai_provider", "") or "gemini").strip().lower()
                _model = getattr(ctx.payload, "llm_model", None)
                _api_key_attr = {"gemini": "gemini_api_key", "openai": "openai_api_key", "claude": "claude_api_key"}.get(_provider, "gemini_api_key")
                _api_key = getattr(ctx.payload, _api_key_attr, "") or ""
                _tone = (getattr(ctx.payload, "rewrite_tone", "") or "").strip()
                _voice_lang = ctx.payload.voice_language
                _job_log(ctx.effective_channel, ctx.job_id, f"voice.ai_rewrite_started part_no={idx} provider={_provider} target_dur={_target_dur:.1f}s", kind="debug")
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="voice_ai_rewrite_started",
                    level="INFO",
                    message=f"AI rewriting narration (part {idx})",
                    step="voice.tts",
                    context={"part_no": idx, "provider": _provider, "target_duration_sec": _target_dur},
                )
                _rewritten = _llm_rewrite_subtitle(
                    provider=_provider,
                    text=_orig_text,
                    target_duration_sec=_target_dur,
                    target_language=_voice_lang,
                    tone=_tone,
                    api_key=_api_key,
                    model=_model,
                )
                if _rewritten:
                    _part_narration_text = _rewritten
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_ai_rewrite_completed",
                        level="INFO",
                        message=f"AI rewrite OK (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "in_chars": len(_orig_text), "out_chars": len(_rewritten)},
                    )
                else:
                    _part_narration_text = _orig_text
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice.ai_rewrite_fallback part_no={idx} — using original text", kind="warning")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_ai_rewrite_fallback",
                        level="WARNING",
                        message=f"AI rewrite returned None — using original transcript (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "reason": "llm_returned_none"},
                    )
                ctx.voice_part_tts_attempts.append(idx)
                _part_mp3 = str(TEMP_DIR / ctx.job_id / "voice" / f"part_{idx:03d}.mp3")
                if ctx.cancel_registry.is_cancelled(ctx.job_id):
                    raise ctx.cancel_registry.JobCancelledError()
                try:
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from rewrite (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "language": _voice_lang, "source": "ai_rewrite"},
                    )
                    _part_subtitle_voice_path = generate_narration_audio(
                        text=_part_narration_text,
                        language=_voice_lang,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=_resolve_voice_provider_from_plan(
                            ctx, getattr(ctx.payload, "tts_engine", "edge")
                        ),
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_completed",
                        level="INFO",
                        message=f"AI voice from rewrite generated (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="ai_rewrite",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_ai_rewrite_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (ai_rewrite, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} source text empty; narration skipped", kind="warning")
        else:
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_subtitle_source_missing part_no={idx} source=ai_rewrite; narration skipped", kind="warning")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"AI rewrite source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "ai_rewrite"},
            )
```

**ctx state mutations (aligned with subtitle branch):**
1. `ctx.voice_part_tts_attempts.append(idx)` — same as subtitle branch line 243.
2. `_part_subtitle_voice_path` local variable populated (consumed by line 426 mixer).
3. NO mutation to `ctx.voice_audio_path` (that's manual-source only).
4. `_part_mp3` file written to `TEMP_DIR / job_id / voice / part_{idx:03d}.mp3` (cleaned at line 488).

**Sacred #6 compliance:** All `_emit_render_event` calls use keyword-only (verified above). 4 new event types emitted: `voice_ai_rewrite_started`, `voice_ai_rewrite_completed`, `voice_ai_rewrite_fallback`, `voice_ai_rewrite_tts_failed` (the last reuses existing `voice_failed` event name to keep VOICE001 dashboard intact).

**Sacred #8 compliance:** Cancel check at the same spot as subtitle branch (right before `generate_narration_audio`).

---

### 3.11 EDIT: `d:\tool-render-video\backend\app\services\metrics.py`

**Add 3 metrics. Insert at line 167 (after `LLM_SEGMENTS_SELECTED` definition, before the `RENDER_ENGINE_EDITORIAL_OVERRIDES`).**

```python
    LLM_REWRITE_CALLS = Counter(
        "llm_rewrite_calls_total",
        "LLM rewrite-subtitle calls by provider and outcome",
        ["provider", "status"],   # status: success | empty
        registry=REGISTRY,
    )
    LLM_REWRITE_LATENCY = Histogram(
        "llm_rewrite_seconds",
        "Latency of rewrite-subtitle LLM call per provider",
        ["provider"],
        buckets=(0.2, 0.5, 1, 2, 5, 10, 30, 60),
        registry=REGISTRY,
    )
    LLM_REWRITE_CHAR_DELTA = Histogram(
        "llm_rewrite_char_delta",
        "Character-count delta (rewritten - original) per rewrite call",
        ["provider"],
        buckets=(-1000, -500, -200, -100, -50, 0, 50, 100, 200, 500, 1000),
        registry=REGISTRY,
    )
```

**Add the NoOp fallbacks at line 240 area (in the `else:` branch matching the 3 NoOpMetric assignments):**

```python
    LLM_REWRITE_CALLS = _NoOpMetric()         # type: ignore[assignment]
    LLM_REWRITE_LATENCY = _NoOpMetric()       # type: ignore[assignment]
    LLM_REWRITE_CHAR_DELTA = _NoOpMetric()    # type: ignore[assignment]
```

---

### 3.12 EDIT: `d:\tool-render-video\frontend\src\features\clip-studio\render\steps\StepConfigure.tsx`

**Edit at line 1058-1061:**

Before:
```tsx
                {([
                  { v: 'subtitle'            as const, l: t.cfgVoiceSrcAuto,   d: t.cfgVoiceSrcAutoDesc   },
                  { v: 'translated_subtitle' as const, l: t.cfgVoiceSrcTrans,  d: t.cfgVoiceSrcTransDesc  },
                  { v: 'manual'              as const, l: t.cfgVoiceSrcManual, d: t.cfgVoiceSrcManualDesc },
                ]).map(({ v, l, d }) => (
```

After:
```tsx
                {([
                  { v: 'subtitle'            as const, l: t.cfgVoiceSrcAuto,    d: t.cfgVoiceSrcAutoDesc    },
                  { v: 'translated_subtitle' as const, l: t.cfgVoiceSrcTrans,   d: t.cfgVoiceSrcTransDesc   },
                  { v: 'ai_rewrite'          as const, l: t.cfgVoiceSrcRewrite, d: t.cfgVoiceSrcRewriteDesc },
                  { v: 'manual'              as const, l: t.cfgVoiceSrcManual,  d: t.cfgVoiceSrcManualDesc  },
                ]).map(({ v, l, d }) => (
```

**Add conditional textarea after line 1081 (after the existing `manual` block, before closing `</div>` at line 1082):**

```tsx
              {cfg.voiceSource === 'ai_rewrite' && (
                <div style={{ marginTop: '8px' }}>
                  <input
                    type="text"
                    className="dir-in"
                    placeholder={t.cfgRewriteToneHint}
                    value={cfg.rewriteTone || ''}
                    onChange={(e) => setCfgKey('rewriteTone', e.target.value)}
                    style={{ width: '100%', fontFamily: 'var(--fb)', fontSize: '12px' }}
                  />
                </div>
              )}
```

---

### 3.13 EDIT: `d:\tool-render-video\frontend\src\features\clip-studio\render\i18n.ts`

**Add 3 keys × 2 langs.**

**English block (after line 70, with the other `cfgVoiceSrc*`):**
```ts
    cfgVoiceSrcRewrite: 'AI rewrite for narration',
    cfgVoiceSrcRewriteDesc: 'Rewrite transcript with AI to fit voiceover duration',
    cfgRewriteToneHint: 'Optional tone (e.g. dramatic, playful, informative)',
```

**Vietnamese block (after line 191):**
```ts
    cfgVoiceSrcRewrite: 'AI viết lại cho TTS',
    cfgVoiceSrcRewriteDesc: 'Dùng AI viết lại transcript khớp thời lượng narration',
    cfgRewriteToneHint: 'Tone tuỳ chọn (ví dụ: kịch tính, vui nhộn, thông tin)',
```

---

### 3.14 EDIT: `d:\tool-render-video\frontend\src\types\api.ts`

**Two edits.**

**Edit A — Extend `voice_source` union (line 141):**

Before:
```ts
  voice_source?: 'manual' | 'subtitle' | 'translated_subtitle'
```

After:
```ts
  voice_source?: 'manual' | 'subtitle' | 'translated_subtitle' | 'ai_rewrite'
```

**Edit B — Add `rewrite_tone` field after line 144 (after `voice_mix_mode`):**

```ts
  voice_mix_mode?: 'replace_original' | 'keep_original_low'
  rewrite_tone?: string
```

---

### 3.15 EDIT: `d:\tool-render-video\frontend\src\features\clip-studio\render\types.ts`

**Add `rewriteTone: string` to the cfg type. Find the type containing `voiceSource` (line ~54 per RenderWorkflow.tsx grep). Add `rewriteTone: ''` to default cfg + `rewriteTone: string` to the type.**

(Plan note: exact insertion depends on the `RenderConfig` interface shape — verify before edit; pattern: same place as `voiceText`.)

---

### 3.16 EDIT: `d:\tool-render-video\frontend\src\features\clip-studio\render\RenderWorkflow.tsx`

**Add `rewrite_tone` to `buildPayload` after line 505:**

```ts
      voice_source:        cfg.narrEnabled ? cfg.voiceSource : undefined,
      voice_text:          cfg.narrEnabled && cfg.voiceSource === 'manual' ? cfg.voiceText : undefined,
      rewrite_tone:        cfg.narrEnabled && cfg.voiceSource === 'ai_rewrite' ? (cfg.rewriteTone || '') : undefined,
```

---

## Section 4: Test plan

### 4.1 NEW: `d:\tool-render-video\backend\tests\test_llm_rewrite_parser.py`

```python
"""Tests for parse_rewrite_response — defensive parser for rewrite output."""
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response

def test_happy_path_plain_text():
    # Arrange
    raw = "Đây là narration đã được rewrite cho TTS."
    # Act
    out = parse_rewrite_response(raw, target_duration_sec=10.0, word_budget=20)
    # Assert
    assert out == "Đây là narration đã được rewrite cho TTS."

def test_strip_code_fences_triple_backtick():
    raw = "```\nHello narration here.\n```"
    assert parse_rewrite_response(raw, 5.0, 10) == "Hello narration here."

def test_strip_code_fences_with_lang_marker():
    raw = "```text\nHello narration.\n```"
    assert parse_rewrite_response(raw, 5.0, 10) == "Hello narration."

def test_strip_prose_prefix_here_is():
    raw = "Here is the rewritten narration: This is the actual content."
    assert parse_rewrite_response(raw, 5.0, 20) == "This is the actual content."

def test_reject_empty_string():
    assert parse_rewrite_response("", 5.0, 10) is None
    assert parse_rewrite_response("   \n  ", 5.0, 10) is None

def test_reject_whitespace_only_after_strip():
    raw = "```\n   \n```"
    assert parse_rewrite_response(raw, 5.0, 10) is None

def test_reject_over_2x_budget():
    # Generate 50 words but budget = 10 → 2x cap = 20. Must reject.
    raw = " ".join(["word"] * 50)
    assert parse_rewrite_response(raw, 5.0, word_budget=10) is None

def test_none_input_returns_none():
    assert parse_rewrite_response(None, 5.0, 10) is None  # type: ignore[arg-type]

def test_internal_whitespace_collapsed():
    raw = "Hello    world\n\n\nfoo"
    assert parse_rewrite_response(raw, 5.0, 20) == "Hello world foo"

def test_minimum_budget_floor():
    # word_budget=3, 2x cap=20 (the max(20, ...) floor), so 15 words OK.
    raw = " ".join(["w"] * 15)
    out = parse_rewrite_response(raw, 1.0, word_budget=3)
    assert out == " ".join(["w"] * 15)
```

**AAA scenarios + mocks:** No mocks needed — pure function tests.

### 4.2 NEW: `d:\tool-render-video\backend\tests\test_llm_rewrite_dispatcher.py`

```python
"""Tests for rewrite_subtitle dispatcher — provider routing + fallback chain."""
import pytest
from unittest.mock import patch

_KW = dict(
    text="Hello world",
    target_duration_sec=10.0,
    target_language="en-US",
    tone="",
    api_key="fake",
    model=None,
)

def test_dispatch_to_named_provider(monkeypatch):
    # Arrange
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: "REWRITTEN-GEMINI",
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    # Act
    out = rewrite_subtitle(provider="gemini", **_KW)
    # Assert
    assert out == "REWRITTEN-GEMINI"

def test_unknown_provider_falls_to_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: "REWRITTEN",
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    assert rewrite_subtitle(provider="bogus", **_KW) == "REWRITTEN"

def test_fallback_chain_enabled(monkeypatch):
    # Arrange — primary returns None, fallback succeeds
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", True)
    call_log = []
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: (call_log.append("gemini"), None)[1],
    )
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.openai.rewrite_subtitle",
        lambda **kw: (call_log.append("openai"), "OK")[1],
    )
    # Act
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    # Assert
    assert out == "OK"
    assert call_log == ["gemini", "openai"]

def test_fallback_disabled_returns_primary_only(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", False)
    call_log = []
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: (call_log.append("gemini"), None)[1],
    )
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.openai.rewrite_subtitle",
        lambda **kw: (call_log.append("openai"), "OK")[1],
    )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None
    assert call_log == ["gemini"]

def test_provider_raises_returns_none(monkeypatch):
    # Sacred #3 — provider exception must not propagate
    def _boom(**kw): raise RuntimeError("SDK exploded")
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        _boom,
    )
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", False)
    # The provider wrapper IS expected to catch — but if it leaks, dispatcher would crash.
    # Verify it returns None instead of raising:
    # NOTE: this exercises the wrapper-level try/except; if the dispatcher doesn't
    # have one, this test will document the gap. Adjust to wrap dispatcher if needed.
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None
```

### 4.3 NEW: `d:\tool-render-video\backend\tests\test_llm_rewrite_prompts.py`

```python
"""Tests for build_rewrite_prompt — word-budget math + format safety."""
from app.features.render.ai.llm.rewrite_prompts import (
    build_rewrite_prompt,
    _compute_word_budget,
    MAX_REWRITE_INPUT_CHARS,
)

def test_word_budget_vietnamese_30sec():
    # vi-VN @ 140 wpm × 30/60 = 70
    assert _compute_word_budget(30.0, "vi-VN") == 70

def test_word_budget_english_30sec():
    # en-US @ 150 wpm × 30/60 = 75
    assert _compute_word_budget(30.0, "en-US") == 75

def test_word_budget_japanese_60sec():
    # ja-JP @ 200 wpm × 1 = 200
    assert _compute_word_budget(60.0, "ja-JP") == 200

def test_word_budget_korean_15sec():
    # ko-KR @ 180 × 0.25 = 45
    assert _compute_word_budget(15.0, "ko-KR") == 45

def test_word_budget_english_gb_45sec():
    # en-GB @ 145 × 0.75 = 108.75 → 108
    assert _compute_word_budget(45.0, "en-GB") == 108

def test_word_budget_unknown_lang_default():
    # default = 150 wpm
    assert _compute_word_budget(60.0, "xx-XX") == 150

def test_word_budget_minimum_floor():
    assert _compute_word_budget(0.0, "en-US") >= 3

def test_word_budget_ceiling():
    assert _compute_word_budget(99999.0, "en-US") <= 800

def test_prompt_returns_tuple_str_str():
    sys, usr = build_rewrite_prompt("Hello world.", 10.0, "en-US")
    assert isinstance(sys, str) and isinstance(usr, str)
    assert len(sys) > 0 and len(usr) > 0

def test_prompt_contains_target_duration():
    _, usr = build_rewrite_prompt("Hello.", 42.0, "en-US")
    assert "42.0" in usr

def test_prompt_truncates_long_input():
    big = "x" * (MAX_REWRITE_INPUT_CHARS + 500)
    _, usr = build_rewrite_prompt(big, 10.0, "en-US")
    assert "[truncated]" in usr
    # Source body must be at most MAX_REWRITE_INPUT_CHARS + truncation marker length
    # (sanity — not exact byte count)
    assert len(usr) < MAX_REWRITE_INPUT_CHARS + 500

def test_prompt_default_tone_substituted():
    _, usr = build_rewrite_prompt("Hi.", 5.0, "en-US", tone="")
    assert "natural / informative" in usr

def test_prompt_custom_tone_substituted():
    _, usr = build_rewrite_prompt("Hi.", 5.0, "en-US", tone="dramatic")
    assert "dramatic" in usr

def test_prompt_no_format_keyerror():
    # Format-safety regression guard — calling .format with the canonical
    # placeholder set must not raise. Any literal brace inside the template
    # would surface as a KeyError here.
    try:
        build_rewrite_prompt("Hello.", 10.0, "vi-VN", tone="x")
    except KeyError as exc:
        raise AssertionError(f"Template has literal brace: {exc}")
```

### 4.4 NEW: `d:\tool-render-video\backend\tests\test_part_voice_mix_ai_rewrite.py`

```python
"""Integration tests for the ai_rewrite branch in run_part_voice_mix."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Builds a minimal PartRenderContext + payload + srt_part for the branch.
# Heavy mocks: generate_narration_audio, _llm_rewrite_subtitle, mix_narration_audio.

@pytest.fixture
def _ctx_and_paths(tmp_path):
    """Arrange a PartRenderContext with voice_source='ai_rewrite'."""
    # ... (helper builds tmp srt_part file, ctx with cancel_registry, payload mock)
    pass  # see test body below for shape

def test_ai_rewrite_uses_rewritten_text_when_llm_returns_string(monkeypatch, tmp_path):
    # Arrange: srt_part with sample text; LLM returns "REWRITTEN".
    captured_text = {}
    def _fake_tts(**kw):
        captured_text["text"] = kw["text"]
        return str(tmp_path / "voice.mp3")
    def _fake_rewrite(**kw): return "REWRITTEN narration."
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix.generate_narration_audio",
        _fake_tts,
    )
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        _fake_rewrite,
    )
    # Act
    # ... call run_part_voice_mix with crafted ctx (voice_source='ai_rewrite', voice_enabled=True)
    # Assert
    assert captured_text["text"] == "REWRITTEN narration."

def test_ai_rewrite_falls_back_to_original_when_llm_returns_none(monkeypatch, tmp_path):
    # Arrange
    captured = {}
    def _fake_tts(**kw):
        captured["text"] = kw["text"]
        return str(tmp_path / "voice.mp3")
    def _fake_rewrite(**kw): return None
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix.generate_narration_audio",
        _fake_tts,
    )
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        _fake_rewrite,
    )
    # Act
    # ... run
    # Assert — TTS got the ORIGINAL transcript text (not rewritten)
    assert captured["text"] == "<original transcript text from srt_part>"

def test_ai_rewrite_appends_to_voice_part_tts_attempts(monkeypatch, tmp_path):
    # Arrange + Act
    # Assert
    # ctx.voice_part_tts_attempts contains idx

def test_ai_rewrite_emits_started_and_completed_events(monkeypatch, tmp_path):
    events = []
    def _spy(**kw): events.append(kw["event"])
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._emit_render_event",
        _spy,
    )
    # ... act
    assert "voice_ai_rewrite_started" in events
    assert "voice_ai_rewrite_completed" in events
    assert "voice_tts_started" in events
    assert "voice_tts_completed" in events

def test_ai_rewrite_emits_fallback_event_when_llm_returns_none(monkeypatch, tmp_path):
    events = []
    def _spy(**kw): events.append(kw["event"])
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._emit_render_event",
        _spy,
    )
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        lambda **kw: None,
    )
    # ... act
    assert "voice_ai_rewrite_fallback" in events

def test_ai_rewrite_provider_resolved_from_ai_provider_field(monkeypatch, tmp_path):
    """Mock ctx.payload.ai_provider='claude' → rewrite_subtitle called with provider='claude'."""
    captured = {}
    def _spy(**kw):
        captured["provider"] = kw.get("provider")
        return "OUTPUT"
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        _spy,
    )
    # ... act with payload.ai_provider='claude' and claude_api_key='secret'
    assert captured["provider"] == "claude"

def test_ai_rewrite_skipped_when_voice_disabled(monkeypatch, tmp_path):
    # ctx.payload.voice_enabled=False → branch never enters → rewrite_subtitle NOT called
    called = {"count": 0}
    def _spy(**kw):
        called["count"] += 1
        return "X"
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        _spy,
    )
    # ... act with voice_enabled=False
    assert called["count"] == 0

def test_ai_rewrite_target_duration_from_seg(monkeypatch, tmp_path):
    """seg = {'start': 10, 'end': 25} → target_duration_sec passed = 15.0."""
    captured = {}
    def _spy(**kw):
        captured["dur"] = kw["target_duration_sec"]
        return "OUT"
    monkeypatch.setattr(
        "app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle",
        _spy,
    )
    # ... act
    assert captured["dur"] == 15.0
```

**Mock points (consistent across the suite):**
- `app.features.render.engine.stages.part_voice_mix._llm_rewrite_subtitle` → returns string or None.
- `app.features.render.engine.stages.part_voice_mix.generate_narration_audio` → returns fake path.
- `app.features.render.engine.stages.part_voice_mix.mix_narration_audio` → no-op.
- `app.features.render.engine.stages.part_voice_mix._emit_render_event` → spy.

### 4.5 EDIT: `d:\tool-render-video\backend\tests\test_render_request_public_surface.py`

**Edit test_public_field_count_pinned at line 116-133 — bump pinned counts:**

Before:
```python
    assert len(FE_FACING_FIELDS) == 72, f"FE_FACING_FIELDS = {len(FE_FACING_FIELDS)}"
    assert len(BE_ONLY_FIELDS)   == 80, f"BE_ONLY_FIELDS = {len(BE_ONLY_FIELDS)}"
    assert len(RenderRequest.model_fields) == 152, ...
```

After:
```python
    assert len(FE_FACING_FIELDS) == 73, f"FE_FACING_FIELDS = {len(FE_FACING_FIELDS)}"
    assert len(BE_ONLY_FIELDS)   == 80, f"BE_ONLY_FIELDS = {len(BE_ONLY_FIELDS)}"
    assert len(RenderRequest.model_fields) == 153, ...
```

**Add new test for rewrite_tone default + voice_source allowlist:**

```python
def test_render_request_has_rewrite_tone_default_empty():
    from app.models.render import RenderRequest
    rr = RenderRequest()
    assert rr.rewrite_tone == ""

def test_voice_source_allowlist_accepts_ai_rewrite():
    from app.models.render import RenderRequest
    rr = RenderRequest(voice_enabled=True, voice_source="ai_rewrite")
    assert rr.voice_source == "ai_rewrite"

def test_render_request_public_has_rewrite_tone():
    from app.models.render_public import RenderRequestPublic
    obj = RenderRequestPublic(rewrite_tone="dramatic")
    assert obj.model_dump()["rewrite_tone"] == "dramatic"
```

### 4.6 EDIT: `d:\tool-render-video\backend\tests\test_render_field_groups.py`

No edit needed if `rewrite_tone` is correctly added to `voice` group in Step 3.9 — existing partition/disjoint tests will automatically validate.

### 4.7 Regression smoke

- All existing tests in `backend/tests/` must still pass. Most-relevant:
  - `test_render_request_public_surface.py` — count pin updated in 4.5.
  - `test_render_field_groups.py` — `voice` group updated in 3.9.
  - `test_llm_fallback.py`, `test_llm_metrics.py` — untouched contracts.
  - `test_render_request_strict_vs_lenient.py` — verify extra="forbid" still works post-add.

---

## Section 5: Migration order (DAG)

```
LEVEL 0 (no deps — can implement in parallel):
  ├─ 3.1  rewrite_prompts.py         (NEW)
  ├─ 3.2  rewrite_parser.py          (NEW)
  ├─ 3.11 metrics.py                 (EDIT — add 3 histograms)
  └─ 3.7  render.py                  (EDIT — add field + validator)

LEVEL 1 (depends on Level 0):
  ├─ 3.4  providers/gemini.py        (depends on 3.1, 3.2)
  ├─ 3.5  providers/openai.py        (depends on 3.1, 3.2)
  ├─ 3.6  providers/claude.py        (depends on 3.1, 3.2)
  ├─ 3.8  render_public.py           (depends on 3.7)
  └─ 3.9  render_field_groups.py     (depends on 3.7)

LEVEL 2 (depends on Level 1):
  ├─ 3.3  rewrite.py dispatcher      (depends on 3.4, 3.5, 3.6)
  └─ 4.5  test_render_request_public_surface.py update (depends on 3.7, 3.8)

LEVEL 3 (depends on Level 2):
  └─ 3.10 part_voice_mix.py          (depends on 3.3, 3.7, 3.11)

LEVEL 4 (depends on Level 3 — backend complete):
  ├─ Tests 4.1-4.4 (NEW)
  └─ Test 4.7 smoke

LEVEL 5 (frontend — parallel to backend tests, depends only on 3.7's wire shape):
  ├─ 3.14 api.ts                     (depends on wire shape in 3.7)
  ├─ 3.15 types.ts
  ├─ 3.16 RenderWorkflow.tsx         (depends on 3.15)
  ├─ 3.13 i18n.ts
  └─ 3.12 StepConfigure.tsx          (depends on 3.13, 3.15)
```

**Critical path:** 3.1/3.2 → 3.4/3.5/3.6 → 3.3 → 3.10. Tests can be written in parallel with implementation (TDD).

---

## Section 6: Test commands (PowerShell)

```powershell
# 6.1 — Baseline (BEFORE any edit)
cd d:\tool-render-video\backend
python -m pytest tests/ --tb=no -q 2>&1 | Select-Object -Last 10
# Record: "XXX passed in Y.Ys"

# 6.2 — Module compile checks (after each NEW file)
python -c "import app.features.render.ai.llm.rewrite_prompts; print('OK')"
python -c "import app.features.render.ai.llm.rewrite_parser; print('OK')"
python -c "import app.features.render.ai.llm.rewrite; print('OK')"

# 6.3 — Focused tests (after each test file written)
python -m pytest tests/test_llm_rewrite_parser.py -v
python -m pytest tests/test_llm_rewrite_prompts.py -v
python -m pytest tests/test_llm_rewrite_dispatcher.py -v
python -m pytest tests/test_part_voice_mix_ai_rewrite.py -v

# 6.4 — Regression on modified surfaces
python -m pytest tests/test_render_request_public_surface.py tests/test_render_field_groups.py tests/test_llm_fallback.py tests/test_llm_metrics.py -v

# 6.5 — Full backend
python -m pytest tests/ --tb=short
# Expected: baseline_passed + ~30-40 new tests, 0 failed

# 6.6 — Frontend typecheck + build
cd d:\tool-render-video\frontend
npm run type-check
npm run build

# 6.7 — Manual smoke (post-implementation)
# 1. Start backend + frontend (existing run scripts)
# 2. Open Clip Studio, upload a 60s test video
# 3. In Configure step: NARR tab → enable voice → select "AI rewrite for narration"
# 4. Enter tone "dramatic"
# 5. Start render. Watch logs for:
#      voice.ai_rewrite_started part_no=1 provider=gemini target_dur=...
#      gemini_client: calling rewrite model=... 
#      gemini_client: rewrite OK in_chars=... out_chars=...
#      voice_ai_rewrite_completed
#      voice_tts_started ... source=ai_rewrite
# 6. Verify final mp4 has narration; verify narration matches rewritten text shape (not raw transcript)
```

---

## Section 7: Rollback recipe per file

**No database migrations → rollback is purely code-level.**

| File | Rollback command |
|---|---|
| `rewrite_prompts.py` (NEW) | `git rm backend/app/features/render/ai/llm/rewrite_prompts.py` |
| `rewrite_parser.py` (NEW) | `git rm backend/app/features/render/ai/llm/rewrite_parser.py` |
| `rewrite.py` (NEW) | `git rm backend/app/features/render/ai/llm/rewrite.py` |
| `providers/gemini.py` | `git checkout HEAD~ -- backend/app/features/render/ai/llm/providers/gemini.py` (or surgical delete: lines 250-EOF) |
| `providers/openai.py` | Idem |
| `providers/claude.py` | Idem |
| `render.py` | `git checkout HEAD~ -- backend/app/models/render.py` (drops field + validator change) |
| `render_public.py` | `git checkout HEAD~ -- backend/app/models/render_public.py` |
| `render_field_groups.py` | `git checkout HEAD~ -- backend/app/models/render_field_groups.py` |
| `part_voice_mix.py` | `git checkout HEAD~ -- backend/app/features/render/engine/stages/part_voice_mix.py` |
| `metrics.py` | `git checkout HEAD~ -- backend/app/services/metrics.py` |
| Frontend files | `git checkout HEAD~ -- frontend/src/...` |
| Tests | `git rm backend/tests/test_llm_rewrite_*.py backend/tests/test_part_voice_mix_ai_rewrite.py` |

**Existing payloads safety:** After rollback, any RenderRequest payload sent during the feature window with `voice_source="ai_rewrite"` will fail validation (allowlist no longer contains it). Acceptable: only beta testers will have used the value; users see clean 422 error and re-select another source.

**Cache cleanup post-rollback (optional):** `rm -rf %APP_DATA_DIR%/cache/llm/*` to drop cached rewrite responses keyed under `gemini-rewrite|openai-rewrite|claude-rewrite`.

---

## Section 8: Open implementation questions

1. **UI copy:** The English label `"AI rewrite for narration"` and Vietnamese `"AI viết lại cho TTS"` are first drafts — confirm with PM. Description text similar.
2. **Tone placeholder:** `cfgRewriteToneHint = "Optional tone (e.g. dramatic, playful, informative)"`. Confirm if PM wants preset tone chips instead of free-text input.
3. **Model selection:** Plan reuses `payload.llm_model`. Confirm: do we want the FE to support a separate `rewrite_model` field? Current design says NO (per architect: same model as Call 1).
4. **Cache key namespace:** `"gemini-rewrite"` vs adding a new `purpose` field to `_build_key()`. Current design says namespace via provider string (simpler, no signature change). Confirm acceptable.
5. **Word-budget table:** WPM values for vi/en/ja/ko are heuristics from web sources. If you have empirical data from your existing TTS engine, swap in real numbers.
6. **`rewrite_tone` truthy semantics:** Empty string `""` = use default tone clause. `None` would crash `.strip()` — guarded with `or ""`. Confirm: should `whitespace-only` tone count as empty? Plan says YES (`tone.strip() or default`).
7. **Hard cap word count:** Currently `2 × word_budget`. If LLMs frequently overshoot (which would trigger fallback to original), consider raising to `3 ×` or removing the sanity check. Defer to first telemetry results.

---

## Section 9: Definition of Done checklist

- [ ] All NEW files exist and `python -c "import <module>"` succeeds for each
- [ ] All EDIT files match spec (verified via `git diff`)
- [ ] `python -m py_compile` passes all 6 modified backend .py files
- [ ] Baseline pytest count: recorded BEFORE; post-edit count = baseline + ~30 new tests passing, 0 failures
- [ ] `test_render_request_public_surface.py::test_public_field_count_pinned` passes with new counts (73/80/153)
- [ ] `test_render_request_public_surface.py::test_fe_facing_set_matches_typescript_interface` passes (FE + BE in sync)
- [ ] `test_render_field_groups.py::test_every_render_request_field_is_grouped` passes (rewrite_tone in voice group)
- [ ] Frontend `npm run type-check` passes (no `voice_source` union mismatch)
- [ ] Frontend `npm run build` passes
- [ ] Manual smoke (Section 6.7) shows:
  - [ ] UI shows "AI rewrite for narration" option
  - [ ] Tone textarea appears when selected
  - [ ] Backend logs `voice.ai_rewrite_started`, `voice_ai_rewrite_completed`, `voice_tts_started ... source=ai_rewrite`
  - [ ] Final mp4 has narration audio (not silence)
  - [ ] Narration text in logs differs from raw transcript text
- [ ] Prometheus endpoint exposes `llm_rewrite_calls_total`, `llm_rewrite_seconds`, `llm_rewrite_char_delta` (verify via `curl localhost:8000/metrics | grep rewrite`)
- [ ] Sacred Contract #3 verified: induce provider exception (bad api_key) → render completes with fallback to original text (warning event emitted)

---

## Section 10: Tóm tắt tiếng Việt

- **Tính năng:** Thêm option `voice_source = "ai_rewrite"` cho phép AI viết lại transcript của từng clip thành script narration đúng độ dài clip rồi đưa qua TTS — tránh tình trạng TTS bị overshoot/undershoot khi đọc nguyên transcript.
- **Kiến trúc:** Clone y hệt cách `select_render_plan` đã làm — tạo cặp prompts + parser + dispatcher + 3 provider functions (gemini/openai/claude) song song với LLM Call 1, KHÔNG đụng vào Call 1. Chỉ thêm nhánh mới trong `part_voice_mix.py` khi `voice_source=="ai_rewrite"`.
- **Sacred Contracts:** Tất cả 8 contract đều OK — không sửa DB schema, default behavior giữ nguyên (`voice_source` default vẫn `"manual"`), Sacred #3 (return None) wire end-to-end, Sacred #6 (`_emit_render_event` keyword-only) tuân thủ trong 4 event mới.
- **Files mới:** 4 file backend (`rewrite_prompts.py`, `rewrite_parser.py`, `rewrite.py`, + 3 nhánh trong existing providers), 1 field mới (`rewrite_tone`) trong RenderRequest, 3 Prometheus histograms mới, 4 test file mới.
- **Frontend:** Thêm option 4 vào SOURCE seg trong NARR tab + textarea tone tuỳ chọn + 3 i18n keys × 2 langs + extend `voice_source` union + thêm `rewrite_tone?: string`.
- **Migration order:** Level 0 (4 file độc lập) → Level 1 (3 providers + render_public + field_groups) → Level 2 (dispatcher + test update) → Level 3 (part_voice_mix) → Level 4 (tests + smoke). FE có thể song song sau khi `render.py` wire xong.
- **Rollback:** Pure code rollback (`git checkout HEAD~ -- <file>` hoặc `git rm` cho file mới); không có migration nào để revert.

---

### Critical Files for Implementation

- `d:\tool-render-video\backend\app\features\render\engine\stages\part_voice_mix.py`
- `d:\tool-render-video\backend\app\features\render\ai\llm\providers\gemini.py`
- `d:\tool-render-video\backend\app\models\render.py`
- `d:\tool-render-video\backend\app\models\render_public.py`
- `d:\tool-render-video\frontend\src\features\clip-studio\render\steps\StepConfigure.tsx`