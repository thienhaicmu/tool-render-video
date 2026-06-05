"""
render_plan.py — Unified RenderPlan dataclass + sub-dataclasses.

Pure domain object: no FFmpeg logic, no file I/O, no subprocess calls,
no LLM SDK imports. JSON (de)serialisation is the only stdlib touch.

Vision (Sprint 2 — RenderPlan skeleton):
    Local Video File
       → Transcript
       → Creator Context Builder
       → AI Director (Gemini/Claude/OpenAI)
       → **RenderPlan**  ← this file pins the dataclass for that handoff
       → Render Engine (pure executor)

In Sprint 2 the AI still emits `LLMSegment` and a builder shim
(`orchestration/render_plan_builder.py`) adapts the segment list +
scattered backend decisions into a RenderPlan. In Sprint 4 the AI
provider will emit RenderPlan directly and the builder shim goes away.

Sacred Contract guards baked into the schema:
- Every field has a safe default. Loading a legacy payload that omits
  any new field is a no-op — never an error (Contract #2).
- `from_json` is strictly defensive: unknown fields are dropped,
  malformed values fall back to defaults, never raises (Contract #3
  spirit — used by AI / orchestration paths that must not crash the
  render job).
- `to_json` produces deterministic output (sorted keys, no whitespace),
  so the persisted blob is stable across rebuilds.

Schema is versioned via `RenderPlan.schema_version`. Bump on breaking
shape change and adapt `from_json` accordingly. Sprint 2 ships v1.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional


SCHEMA_VERSION = 1


@dataclass
class ClipPlan:
    """One clip selected for rendering.

    Mirrors the LLM segment-selection output plus a stable rank. Sprint 2
    builder fills rank from the post-LLM ranking pass; Sprint 4 the AI
    will provide rank directly.
    """
    start: float = 0.0
    end: float = 0.0
    rank: int = 0
    score: float = 0.0
    clip_name: str = ""
    title: str = ""
    reason: str = ""
    # Extended segment metadata mirrored from LLMSegment for forward-compat.
    hook_type: str = ""           # question|reveal|contrast|humor|emotion|statement
    content_type: str = ""        # interview|vlog|tutorial|commentary|montage|gaming
    subtitle_style: str = ""      # viral|clean|story|gaming|"" = inherit (Sprint 7.6 FULL)
    viral_score: float = 0.0
    hook_score: float = 0.0
    retention_score: float = 0.0
    speech_density: float = 0.0
    duration_fit: float = 0.0
    cover_offset_ratio: float = 0.0


@dataclass
class SubtitlePolicy:
    """Subtitle styling decision.

    Empty string on any field means 'inherit' — Sprint 2 keeps the existing
    backend resolver (part_asset_planner.py) as the authority; Sprint 4
    will move that decision up into the AI layer.
    """
    style: str = ""               # viral|clean|story|gaming|"" = inherit
    market: str = ""              # us|eu|jp|vn|global|"" = inherit
    emphasis_pass: bool = False
    line_break_rule: str = ""     # "" = market default


@dataclass
class CameraStrategy:
    """Camera / motion-crop / reframe decisions."""
    motion_aware_crop: bool = False
    reframe_mode: str = ""        # center|track|fixed|"" = inherit
    tracker: str = ""             # bytetrack|trackerless|legacy|"" = auto


@dataclass
class AudioPlan:
    """Voice / BGM / CTA-audio configuration."""
    voice_enabled: bool = False
    voice_provider: str = ""      # "" = inherit (xtts default)
    bgm_enabled: bool = False
    cta_audio: str = ""           # path or "" = none


@dataclass
class OutputConfig:
    """Encode / output parameters. Zero or empty means 'inherit from payload'."""
    codec: str = ""
    preset: str = ""
    crf: int = 0
    fps: int = 0
    width: int = 0
    height: int = 0


@dataclass
class RenderPlan:
    """Unified RenderPlan handed from AI Director → Render Engine."""
    schema_version: int = SCHEMA_VERSION
    clips: list[ClipPlan] = field(default_factory=list)
    subtitle_policy: SubtitlePolicy = field(default_factory=SubtitlePolicy)
    camera_strategy: CameraStrategy = field(default_factory=CameraStrategy)
    audio_plan: AudioPlan = field(default_factory=AudioPlan)
    output_config: OutputConfig = field(default_factory=OutputConfig)
    overlays: list[dict] = field(default_factory=list)
    creator_context_id: str = ""

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes | None) -> Optional["RenderPlan"]:
        """Defensive deserialise.

        Returns None when raw is None / empty / unparseable JSON. Unknown
        keys are silently dropped; missing keys fall back to defaults;
        wrong-shape sub-blocks fall back to their default sub-dataclass.
        Never raises.
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
    def _from_dict(cls, data: dict[str, Any]) -> "RenderPlan":
        sv = _coerce_int(data.get("schema_version"), SCHEMA_VERSION)

        raw_clips = data.get("clips")
        clips: list[ClipPlan] = []
        if isinstance(raw_clips, list):
            for entry in raw_clips:
                if isinstance(entry, dict):
                    clips.append(_filter_dataclass(ClipPlan, entry))

        raw_overlays = data.get("overlays")
        overlays: list[dict] = []
        if isinstance(raw_overlays, list):
            for entry in raw_overlays:
                if isinstance(entry, dict):
                    overlays.append(dict(entry))

        return cls(
            schema_version=sv,
            clips=clips,
            subtitle_policy=_filter_dataclass(SubtitlePolicy, data.get("subtitle_policy")),
            camera_strategy=_filter_dataclass(CameraStrategy, data.get("camera_strategy")),
            audio_plan=_filter_dataclass(AudioPlan, data.get("audio_plan")),
            output_config=_filter_dataclass(OutputConfig, data.get("output_config")),
            overlays=overlays,
            creator_context_id=str(data.get("creator_context_id") or ""),
        )


# ── Internal helpers ─────────────────────────────────────────────────────


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off", ""):
            return False
    return default


def _filter_dataclass(cls, data: Any):
    """Build a dataclass instance from a dict — drop unknown keys, coerce
    primitives to the declared type, keep defaults for missing or
    malformed fields. Returns a fresh default instance when data is not
    a dict.
    """
    if not isinstance(data, dict):
        return cls()
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        raw_val = data[f.name]
        # Coerce primitives based on declared annotation
        annot = f.type if isinstance(f.type, type) else None
        # f.type may be a string (PEP 563 / from __future__ import annotations);
        # in that case fall back to the default-instance type.
        default_val = f.default if f.default is not _MISSING else None
        if annot is None and default_val is not None:
            annot = type(default_val)
        if annot is bool:
            kwargs[f.name] = _coerce_bool(raw_val, bool(default_val))
        elif annot is int:
            kwargs[f.name] = _coerce_int(raw_val, int(default_val or 0))
        elif annot is float:
            kwargs[f.name] = _coerce_float(raw_val, float(default_val or 0.0))
        elif annot is str:
            kwargs[f.name] = str(raw_val) if raw_val is not None else (default_val or "")
        else:
            kwargs[f.name] = raw_val
    return cls(**kwargs)


# Sentinel for missing default (dataclasses.MISSING is not a stable public
# API name, so we capture it once here).
import dataclasses as _dc  # noqa: E402
_MISSING = _dc.MISSING
