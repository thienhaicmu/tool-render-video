"""
AI Caption Engine cho TikTok upload.

3 chế độ (fallback tự động):
  1. claude  — Claude API (cần ANTHROPIC_API_KEY)
  2. ollama  — Ollama local LLM (cần cài Ollama + model)
  3. template — Smart template từ transcript (luôn hoạt động, không cần gì)

Dùng:
    from app.services.caption_engine import generate_caption

    caption = generate_caption(
        srt_path="path/to/subtitle.srt",
        video_title="Rick Astley Never Gonna Give You Up",
        hashtags=["#fyp", "#viral"],
        mode="auto",   # auto | claude | ollama | template
    )
"""
from __future__ import annotations

import logging
import os
import re
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# SRT parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_srt(srt_path: str | Path) -> str:
    """Extract plain text from an SRT file (strips timing/index lines)."""
    try:
        content = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):          # index number
            continue
        if re.match(r"^\d{2}:\d{2}", line):   # timestamp
            continue
        # Strip ASS/SSA tags
        line = re.sub(r"\{[^}]*\}", "", line)
        if line:
            lines.append(line)

    return " ".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Hook patterns — viral TikTok openers
# ──────────────────────────────────────────────────────────────────────────────

_HOOK_TEMPLATES = [
    "POV: {hook} 👀",
    "Wait for it… {hook} 😱",
    "Nobody talks about this: {hook}",
    "The moment you realize {hook} 🤯",
    "{hook} (watch till end)",
    "This changed everything: {hook}",
    "I can't believe {hook} 😭",
    "{hook} #storytime",
]

_VIRAL_WORDS = {
    "incredible", "unbelievable", "crazy", "insane", "shocked", "surprised",
    "never", "always", "secret", "hidden", "rare", "first", "last", "only",
    "found", "discovered", "revealed", "exposed", "rich", "money", "won",
    "lost", "died", "saved", "stolen", "free", "million", "thousand",
}


def _score_sentence(sentence: str) -> float:
    """Score a sentence for viral potential (higher = better hook)."""
    s = sentence.lower()
    score = 0.0

    # Questions are great hooks
    if sentence.endswith("?"):
        score += 2.0

    # Exclamations
    if sentence.endswith("!"):
        score += 1.5

    # Viral keywords
    words = set(re.findall(r"\b\w+\b", s))
    score += len(words & _VIRAL_WORDS) * 1.2

    # Numbers (statistics, money)
    if re.search(r"\b\d[\d,.$%]+\b", sentence):
        score += 1.0

    # Optimal length: 6-15 words
    word_count = len(sentence.split())
    if 6 <= word_count <= 15:
        score += 1.0
    elif word_count < 4 or word_count > 25:
        score -= 1.0

    return score


def _extract_best_hook(transcript: str) -> str:
    """Pick the most viral sentence from transcript."""
    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", transcript)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    if not sentences:
        return ""

    # Score and sort
    scored = sorted(sentences, key=_score_sentence, reverse=True)
    return scored[0] if scored else sentences[0]


# ──────────────────────────────────────────────────────────────────────────────
# Mode 3: Smart Template (no AI required)
# ──────────────────────────────────────────────────────────────────────────────

def _generate_template(transcript: str, video_title: str, hashtags: list[str]) -> str:
    """
    Build a viral TikTok caption using transcript keywords + hook templates.
    No external dependencies needed.
    """
    import random

    hook_sentence = _extract_best_hook(transcript)

    if hook_sentence:
        # Truncate hook if too long
        if len(hook_sentence) > 80:
            hook_sentence = hook_sentence[:77] + "..."
        template = random.choice(_HOOK_TEMPLATES)
        # Lowercase hook when embedded mid-sentence
        hook_lower = hook_sentence[0].lower() + hook_sentence[1:] if len(hook_sentence) > 1 else hook_sentence
        caption_body = template.replace("{hook}", hook_lower)
    else:
        # Fallback: use video title as hook
        caption_body = f"You won't believe this 👀 {video_title}"

    # Append hashtags (max 8, TikTok limit ~2200 chars total)
    tag_str = " ".join(hashtags[:8]) if hashtags else ""
    caption = f"{caption_body}\n\n{tag_str}".strip()
    return caption[:2200]


# ──────────────────────────────────────────────────────────────────────────────
# Mode 2: Ollama (local LLM)
# ──────────────────────────────────────────────────────────────────────────────

_OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

_OLLAMA_PROMPT = """\
You are a TikTok content strategist. Based on the transcript below, write ONE viral TikTok caption.

Rules:
- Max 150 characters for the main caption text
- Start with a strong hook (question, shocking statement, or "POV:")
- Use 2-3 relevant emojis
- Do NOT include hashtags (they will be added separately)
- Write in the same language as the transcript
- Output ONLY the caption text, nothing else

Transcript (first 800 chars):
{transcript}

Video title: {title}

Caption:"""


def _generate_ollama(transcript: str, video_title: str, hashtags: list[str]) -> str:
    """Call local Ollama API to generate caption."""
    import urllib.request

    prompt = _OLLAMA_PROMPT.format(
        transcript=transcript[:800],
        title=video_title[:120],
    )

    payload = json.dumps({
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 120},
    }).encode()

    req = urllib.request.Request(
        f"{_OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    caption_body = data.get("response", "").strip()
    if not caption_body:
        raise RuntimeError("Ollama returned empty response")

    # Clean up any accidental hashtags from the model
    caption_body = re.sub(r"#\w+", "", caption_body).strip()

    tag_str = " ".join(hashtags[:8]) if hashtags else ""
    caption = f"{caption_body}\n\n{tag_str}".strip()
    return caption[:2200]


def _ollama_available() -> bool:
    """Check if Ollama is running locally."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{_OLLAMA_BASE_URL}/api/tags", timeout=2)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Mode 1: Claude API (Anthropic)
# ──────────────────────────────────────────────────────────────────────────────

_CLAUDE_PROMPT = """\
You are a viral TikTok content strategist.

Based on the transcript below, write ONE high-converting TikTok caption.

Rules:
- Max 150 characters for the caption body
- Open with a powerful hook: question, shocking fact, or "POV:"
- Include 2-3 relevant emojis naturally
- Do NOT include hashtags
- Write in the same language as the transcript
- Output ONLY the caption text — no explanation, no quotes

Transcript (first 1000 chars):
{transcript}

Video title: {title}"""


def _generate_claude(transcript: str, video_title: str, hashtags: list[str]) -> str:
    """Call Claude API to generate caption. Requires ANTHROPIC_API_KEY env var."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Fast + cheap for caption generation
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": _CLAUDE_PROMPT.format(
                transcript=transcript[:1000],
                title=video_title[:120],
            ),
        }],
    )

    caption_body = message.content[0].text.strip()
    caption_body = re.sub(r"#\w+", "", caption_body).strip()

    tag_str = " ".join(hashtags[:8]) if hashtags else ""
    caption = f"{caption_body}\n\n{tag_str}".strip()
    return caption[:2200]


def _claude_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_caption(
    srt_path: Optional[str | Path] = None,
    transcript_text: Optional[str] = None,
    video_title: str = "",
    hashtags: Optional[list[str]] = None,
    mode: str = "auto",
) -> str:
    """
    Generate a viral TikTok caption.

    Parameters
    ----------
    srt_path        : path to SRT subtitle file (used to extract transcript)
    transcript_text : raw transcript text (alternative to srt_path)
    video_title     : video title (fallback when transcript is empty)
    hashtags        : list of hashtag strings e.g. ["#fyp", "#viral"]
    mode            : "auto" | "claude" | "ollama" | "template"

    Returns
    -------
    str — caption ready to paste into TikTok (max 2200 chars)
    """
    hashtags = hashtags or []

    # Get transcript
    transcript = transcript_text or ""
    if not transcript and srt_path:
        transcript = _parse_srt(srt_path)

    title = (video_title or "").strip() or "New video"

    # --- Mode: auto (try best available) ---
    if mode == "auto":
        if _claude_available():
            mode = "claude"
        elif _ollama_available():
            mode = "ollama"
        else:
            mode = "template"

    # --- Mode: claude ---
    if mode == "claude":
        try:
            return _generate_claude(transcript, title, hashtags)
        except Exception as exc:
            logger.warning("Claude caption failed (%s), falling back to ollama/template", exc)
            if _ollama_available():
                mode = "ollama"
            else:
                mode = "template"

    # --- Mode: ollama ---
    if mode == "ollama":
        try:
            return _generate_ollama(transcript, title, hashtags)
        except Exception as exc:
            logger.warning("Ollama caption failed (%s), falling back to template", exc)
            mode = "template"

    # --- Mode: template (always works) ---
    return _generate_template(transcript, title, hashtags)
