"""
creator_context.py — CreatorContext dataclass.

Captures the channel/persona signals the AI Director needs to bias
clip selection per creator — the *input* the AI considers before
emitting a plan.

Vision:
    Local Video File
       → Transcript
       → **CreatorContextBuilder** ← reads this dataclass via creator_repo
       → AI Director (Gemini/Claude/OpenAI)
       → RenderPlan
       → Render Engine

Sacred Contract guards baked in:
- Every field has a safe default. A blank CreatorContext is the
  "no preferences set" state — no editorial hint.
- to_json / from_json are deterministic + defensive (unknown keys
  dropped, never raise). Same pattern as RenderPlan.
- to_prompt_hint() renders a plain string passed as the
  `editorial_hint` parameter to the LLM prompt builder. No new
  template variables, no risk of the {end}/{start} class of bug.

The dataclass is the *contract* — populated by user settings (singleton
creator_prefs row in DB). Multi-creator (per channel_code) is a future
extension; today it lives as a nested JSON blob inside the existing
creator_prefs.prefs_json column, so no schema migration is required.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional


SCHEMA_VERSION = 1


@dataclass
class CreatorContext:
    """Channel / persona signals the AI Director should bias on.

    Empty defaults mean "no preference"; the prompt-hint serialiser
    omits empty values entirely, so a default-constructed instance
    produces no editorial guidance.
    """
    schema_version: int = SCHEMA_VERSION
    creator_id: str = ""               # opaque ID used by future multi-creator routing
    channel_name: str = ""             # display name for logs / UI
    brand_voice: str = ""              # viral|educational|entertaining|authentic|""
    target_audience: str = ""          # us|eu|jp|vn|global|""
    content_pillars: list[str] = field(default_factory=list)
    market: str = ""                   # same vocabulary as RenderPlan.subtitle_policy.market
    language: str = ""                 # BCP-47 hint, e.g. "vi", "en"
    notes: str = ""                    # free-form creator-supplied editorial brief

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes | None) -> Optional["CreatorContext"]:
        """Defensive deserialise.

        Returns None when raw is None / empty / unparseable JSON.
        Unknown keys are silently dropped; missing keys fall back to
        defaults; wrong primitive types coerce to defaults. Never raises.
        """
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "CreatorContext":
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            raw_val = data[f.name]
            default_val = f.default if f.default is not _MISSING else None
            # Annotation type may be a stringified PEP 563 form; resolve
            # via the default value's type when possible.
            annot = type(default_val) if default_val is not None else None
            if f.name == "content_pillars":
                kwargs[f.name] = _coerce_str_list(raw_val)
            elif annot is int:
                try:
                    kwargs[f.name] = int(raw_val)
                except (TypeError, ValueError):
                    kwargs[f.name] = int(default_val or 0)
            elif annot is bool:
                kwargs[f.name] = bool(raw_val)
            else:
                # Default to string coercion (creator_id, names, voice, etc.).
                kwargs[f.name] = str(raw_val) if raw_val is not None else (default_val or "")
        return cls(**kwargs)

    # ── Empty-state probe ────────────────────────────────────────────────

    def is_empty(self) -> bool:
        """True when no field carries real editorial information.

        A default-constructed instance reports True. Used by callers to
        decide whether to feed the AI an editorial hint at all — when
        empty, the hint is omitted entirely."""
        return not any(
            [
                self.creator_id.strip(),
                self.channel_name.strip(),
                self.brand_voice.strip(),
                self.target_audience.strip(),
                self.market.strip(),
                self.language.strip(),
                self.notes.strip(),
                self.content_pillars,
            ]
        )

    # ── Prompt-hint rendering ────────────────────────────────────────────

    def to_prompt_hint(self) -> str:
        """Render a plain editorial-hint string for the LLM prompt.

        Empty context returns "" (no-op). Otherwise emits a compact
        human-readable hint the LLM can read directly. Order is stable
        (deterministic).
        """
        if self.is_empty():
            return ""
        lines: list[str] = []
        if self.channel_name.strip():
            lines.append(f"Channel: {self.channel_name.strip()}")
        if self.brand_voice.strip():
            lines.append(f"Brand voice: {self.brand_voice.strip()}")
        if self.target_audience.strip() or self.market.strip():
            audience = self.target_audience.strip() or self.market.strip()
            lines.append(f"Target audience: {audience}")
        if self.language.strip():
            lines.append(f"Language: {self.language.strip()}")
        if self.content_pillars:
            pillars = ", ".join(p for p in self.content_pillars if p)
            if pillars:
                lines.append(f"Content pillars: {pillars}")
        if self.notes.strip():
            lines.append(f"Editorial brief: {self.notes.strip()}")
        return " | ".join(lines)


# ── Internal helpers ─────────────────────────────────────────────────────


def _coerce_str_list(value: Any) -> list[str]:
    """Accept either a list[str] or a CSV-ish string. Drop empties."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


# Sentinel for missing default (dataclasses.MISSING is the public name in
# modern Python but importing it as `_MISSING` keeps the rest of the
# module readable).
import dataclasses as _dc  # noqa: E402
_MISSING = _dc.MISSING
