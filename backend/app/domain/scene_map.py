"""
scene_map.py — deterministic shot-boundary map of the source video.

Architecture-review Batch D-2-thin (2026-06-30). Promotes what
``engine/pipeline/scene_detector.py`` already produces (PySceneDetect +
TransNetV2 shot list) into a named domain object that:

  - Is versioned (``SCENE_MAP_SCHEMA_VERSION``) so future shape changes load
    legacy blobs defensively.
  - Persists to ``jobs.scene_map_json`` (migration 0014).
  - Will be consumed by D-2-snap (pass-3 LLM snaps each chosen scene to the
    nearest shot boundary) and D-2-motion (motion crop builds its subject
    path from the persisted shot list instead of re-detecting).

Pure dataclass — no FFmpeg, no SDK imports, no I/O beyond JSON
(de)serialisation. Sacred Contract guards baked in:

  - Every field has a safe default; loading a legacy / partial blob never
    errors (Sacred Contract #3 spirit).
  - ``to_json`` is deterministic (sorted keys, compact separators) so the
    persisted blob is stable across rebuilds.
  - ``from_json`` is strictly defensive — unknown keys dropped, malformed
    values fall back to defaults, never raises.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Bumped when the wire shape of SceneMap changes. v1 = inaugural Batch D-2-thin.
SCENE_MAP_SCHEMA_VERSION = 1


@dataclass
class Shot:
    """One shot boundary from the detector.

    ``transition_score`` is the detector's confidence in the cut at
    ``start``: higher = sharper visual transition. ``0.0`` is the safe
    default when a detector did not report a score (e.g. the implicit
    final shot of the video).
    """
    start: float = 0.0
    end: float = 0.0
    transition_score: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class SceneMap:
    """The full shot-boundary map of a source video.

    ``shots`` is chronological and non-overlapping. ``source_fps`` and
    ``total_duration_sec`` are recorded so consumers can sanity-check the
    persisted blob against the current video state without re-probing.
    """
    schema_version: int = SCENE_MAP_SCHEMA_VERSION
    shots: list[Shot] = field(default_factory=list)
    source_fps: float = 0.0
    total_duration_sec: float = 0.0

    # ── Convenience ──────────────────────────────────────────────────────

    def shot_count(self) -> int:
        return len(self.shots)

    def is_empty(self) -> bool:
        return not self.shots

    def find_shot_containing(self, t: float) -> Optional[Shot]:
        """Return the shot whose time window contains ``t``, or None.

        Linear scan — list is typically <500 shots. The future D-2-snap
        reconciler uses this to snap pass-3 LLM picks to shot boundaries.
        """
        try:
            t = float(t)
        except (TypeError, ValueError):
            return None
        if t < 0:
            return None
        for shot in self.shots:
            if shot.start <= t <= shot.end:
                return shot
        return None

    def nearest_boundary(self, t: float) -> float:
        """Return the closest shot boundary (start or end) to ``t``. Returns
        ``t`` unchanged when the map is empty so callers can use this
        unconditionally without an empty-check."""
        try:
            t = float(t)
        except (TypeError, ValueError):
            return 0.0
        if not self.shots:
            return t
        best = t
        best_d = float("inf")
        for shot in self.shots:
            for boundary in (shot.start, shot.end):
                d = abs(boundary - t)
                if d < best_d:
                    best, best_d = boundary, d
        return best

    def slice(self, start_sec: float, end_sec: float) -> list[tuple[float, float]]:
        """Return shot ranges overlapping the ``[start_sec, end_sec]`` window,
        clipped to window edges. Output matches the contract of
        ``_detect_scene_ranges_in_clip`` in ``motion/pixel_diff.py``:
        chronological, non-overlapping ``(scene_start, scene_end)`` tuples
        in source-global seconds.

        D-2-motion Phase 1 deliverable (D1.2). The D-2-motion Phase 3 swap
        feeds the result of this method to ``build_subject_path``'s
        ``_scene_ranges`` parameter as a drop-in replacement for the
        pixel-diff detector.

        Rules:
          - Empty map → empty list (caller falls back to legacy detector).
          - Invalid window (end <= start, NaN, etc.) → empty list.
          - Shots fully outside the window → dropped.
          - Shots partially overlapping → clipped to window edges.
          - Output is always non-overlapping and chronological.

        Defensive: returns ``[]`` on any failure. Never raises
        (Sacred Contract #3 spirit)."""
        try:
            try:
                s = float(start_sec)
                e = float(end_sec)
            except (TypeError, ValueError):
                return []
            if not (e > s) or not self.shots:
                return []
            out: list[tuple[float, float]] = []
            for shot in self.shots:
                # Drop shots entirely outside the window.
                if shot.end <= s or shot.start >= e:
                    continue
                # Clip to window edges.
                clipped_start = max(shot.start, s)
                clipped_end = min(shot.end, e)
                # Drop zero-duration clips (boundary touches edge).
                if clipped_end > clipped_start:
                    out.append((clipped_start, clipped_end))
            return out
        except Exception:
            return []

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe nested dict — drop-in for result_json / events / UI."""
        return asdict(self)

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: "str | bytes | None") -> Optional["SceneMap"]:
        """Defensive deserialise. None on None/empty/unparseable input;
        unknown keys dropped; missing keys fall back to defaults. Never raises."""
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
    def _from_dict(cls, data: dict[str, Any]) -> "SceneMap":
        shots: list[Shot] = []
        raw_shots = data.get("shots")
        if isinstance(raw_shots, list):
            for entry in raw_shots:
                shot = _coerce_shot(entry)
                if shot is not None:
                    shots.append(shot)
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCENE_MAP_SCHEMA_VERSION),
            shots=shots,
            source_fps=_coerce_float(data.get("source_fps"), 0.0),
            total_duration_sec=_coerce_float(data.get("total_duration_sec"), 0.0),
        )


# ── Internal helpers ─────────────────────────────────────────────────────────


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


def _coerce_shot(v: Any) -> Optional[Shot]:
    """One Shot from a Shot instance / dict. None if empty or malformed.

    Accepts dicts with the natural ``start``/``end``/``transition_score``
    keys; legacy detector blobs that use ``cut_at`` (single timestamp)
    are NOT supported — the detector module always emits the range shape.
    """
    if isinstance(v, Shot):
        # Drop trivially-empty entries to keep round-trip clean.
        return v if (v.end > v.start) else None
    if isinstance(v, dict):
        start = _coerce_float(v.get("start"), 0.0)
        end = _coerce_float(v.get("end"), 0.0)
        if end <= start:
            return None
        return Shot(
            start=start,
            end=end,
            transition_score=_coerce_float(v.get("transition_score"), 0.0),
        )
    return None


def scene_map_from_detector_result(
    raw_shots: list[dict],
    source_fps: float = 0.0,
    total_duration_sec: float = 0.0,
) -> SceneMap:
    """Build a SceneMap from the raw ``detect_scenes()`` return shape
    (``list[{"start": float, "end": float, "transition_score": float}]``).

    Used by the Comprehension-style stage runner so the dataclass
    conversion lives in one place. Defensive: unknown / malformed shots
    are dropped. Never raises."""
    shots: list[Shot] = []
    if isinstance(raw_shots, list):
        for entry in raw_shots:
            shot = _coerce_shot(entry)
            if shot is not None:
                shots.append(shot)
    return SceneMap(
        shots=shots,
        source_fps=_coerce_float(source_fps, 0.0),
        total_duration_sec=_coerce_float(total_duration_sec, 0.0),
    )
