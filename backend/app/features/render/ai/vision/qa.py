"""
qa.py — AI Vision QA for Story Mode generated assets (P3).

After a shot image is generated, a vision model (GPT-4o) checks it actually
matches what the shot needs: the right character(s), emotion, setting and shot
framing. A clear mismatch → reject, so the caller regenerates (bounded). This
catches the failure the technical qa_pipeline (Sacred Contract #8) cannot: a
valid-but-WRONG image (wrong character face, wrong mood).

Under ``features/render/ai/**`` → Sacred Contract #3 is ABSOLUTE: every path
catches all exceptions and returns a SAFE default. The default is FAIL-OPEN
(``ok=True``): a flaky / unavailable vision check must NEVER block a render — it
only ever REJECTS on an explicit NO. This is a supplement to, never a bypass of,
the technical QA gate.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.render.vision.qa")

# Master switch — a vision call per asset is extra cost/latency. Default OFF; the
# Story pipeline turns it on per render (STORY_VISION_QA=1). Fail-open regardless.
_QA_ON = os.getenv("STORY_VISION_QA", "0") == "1"


def is_enabled() -> bool:
    return _QA_ON


def _openai_client():
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI  # lazy — optional dep
        return OpenAI(api_key=key, timeout=60)
    except Exception as exc:
        logger.info("vision.qa: openai SDK unavailable (%s)", exc)
        return None


def _expected_description(shot, bible) -> str:
    """Build the human-readable expectation for the shot from its spec + Bible."""
    parts: list[str] = []
    st = (getattr(shot, "shot_type", "") or "").strip()
    if st:
        parts.append(f"a {st.replace('_', ' ')} shot")
    emo = (getattr(shot, "emotion", "") or "").strip()
    if emo and emo != "normal":
        parts.append(f"mood: {emo}")
    # Characters present, with their canonical look.
    chars = getattr(shot, "characters", None) or []
    if bible is not None:
        for cid in chars:
            c = bible.character(cid)
            if c is not None:
                desc = (getattr(c, "description", "") or getattr(c, "name", "") or "").strip()
                if desc:
                    parts.append(f"character: {desc}")
        env_ref = (getattr(shot, "environment_ref", "") or "").strip()
        if env_ref:
            e = bible.environment(env_ref)
            if e is not None and (getattr(e, "description", "") or "").strip():
                parts.append(f"setting: {e.description.strip()}")
    vp = (getattr(shot, "visual_prompt", "") or "").strip()
    if vp:
        parts.append(f"scene: {vp}")
    return "; ".join(parts) or "the described scene"


def qa_shot_image(image_path: str, shot, bible=None) -> dict:
    """Vision-check a generated shot image against its spec. Returns
    ``{"ok": bool, "verdict": str, "reason": str}``. FAIL-OPEN: ok=True on no key /
    no SDK / disabled / any error — only an explicit NO yields ok=False. Never
    raises."""
    result = {"ok": True, "verdict": "skipped", "reason": ""}
    try:
        if not _QA_ON:
            return result
        p = Path(image_path or "")
        if not (p.exists() and p.stat().st_size > 0):
            result["reason"] = "no image to check"
            return result
        client = _openai_client()
        if client is None:
            result["reason"] = "vision unavailable"
            return result
        model = (os.getenv("STORY_QA_MODEL", "gpt-4o").strip() or "gpt-4o")
        expected = _expected_description(shot, bible)
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        question = (
            "You are a strict art director. Does this image plausibly depict: "
            f"{expected}? Reply with 'YES' or 'NO' on the first line, then a short "
            "reason. Reject (NO) only for a clear mismatch (wrong character look, "
            "wrong mood, wrong setting)."
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
            max_tokens=200,
        )
        text = (resp.choices[0].message.content or "").strip()
        head = text.splitlines()[0].strip().upper() if text else ""
        ok = not head.startswith("NO")
        return {"ok": ok, "verdict": "pass" if ok else "reject", "reason": text[:300]}
    except Exception as exc:
        logger.info("vision.qa: check unavailable (%s) — accepting (fail-open)", exc)
        return {"ok": True, "verdict": "error", "reason": str(exc)[:200]}


__all__ = ["qa_shot_image", "is_enabled"]
