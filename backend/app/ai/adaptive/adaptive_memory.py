"""
adaptive_memory.py — Local adaptive creator profile persistence. Phase 42.

Rules:
- Deterministic only
- Never raises
- Local JSON persistence only (data/adaptive/creator_profiles/)
- Safe fallback if missing or corrupt
- No DB migration
- No internet access
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.ai.adaptive.adaptive_schema import AICreatorPreferenceProfile
from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile

logger = logging.getLogger("app.ai.adaptive.memory")

_PROFILE_DIR = Path("data/adaptive/creator_profiles")
_DEFAULT_PROFILE_ID = "default"
_CONFIDENCE_INCREMENT = 0.08
_CONFIDENCE_MAX = 1.0
_CONFIDENCE_MIN = 0.0


def _profile_path(profile_id: str = _DEFAULT_PROFILE_ID) -> Path:
    return _PROFILE_DIR / f"{profile_id}.json"


def build_default_creator_profile(profile_id: str = _DEFAULT_PROFILE_ID) -> AICreatorPreferenceProfile:
    """Return a blank creator preference profile with safe defaults. Never raises."""
    return AICreatorPreferenceProfile(profile_id=profile_id)


def load_creator_profile(profile_id: str = _DEFAULT_PROFILE_ID) -> AICreatorPreferenceProfile:
    """Load creator profile from local JSON. Falls back to default if missing or corrupt.

    Never raises. Logs structured events.
    """
    path = _profile_path(profile_id)
    try:
        if not path.exists():
            logger.info("ai_adaptive_profile_loaded profile_id=%s status=not_found_using_default", profile_id)
            return build_default_creator_profile(profile_id)

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)

        if not isinstance(data, dict):
            logger.info("ai_adaptive_profile_loaded profile_id=%s status=corrupt_using_default", profile_id)
            return build_default_creator_profile(profile_id)

        data = sanitize_adaptive_profile(data)

        profile = AICreatorPreferenceProfile(
            profile_id=str(data.get("profile_id", profile_id)),
            creator_style_preference=str(data.get("creator_style_preference", "")),
            preferred_subtitle_style=str(data.get("preferred_subtitle_style", "")),
            preferred_pacing_style=str(data.get("preferred_pacing_style", "")),
            preferred_camera_style=str(data.get("preferred_camera_style", "")),
            preferred_duration_range=str(data.get("preferred_duration_range", "")),
            preferred_variant_strategy=str(data.get("preferred_variant_strategy", "")),
            style_confidence=_clamp(data.get("style_confidence", 0.0)),
            subtitle_confidence=_clamp(data.get("subtitle_confidence", 0.0)),
            pacing_confidence=_clamp(data.get("pacing_confidence", 0.0)),
            camera_confidence=_clamp(data.get("camera_confidence", 0.0)),
            selection_history_count=max(0, int(data.get("selection_history_count", 0))),
            export_history_count=max(0, int(data.get("export_history_count", 0))),
            tags=list(data.get("tags", [])),
            warnings=list(data.get("warnings", [])),
        )

        logger.info(
            "ai_adaptive_profile_loaded profile_id=%s style=%s style_conf=%.2f",
            profile_id, profile.creator_style_preference, profile.style_confidence,
        )
        return profile

    except Exception as exc:
        logger.info(
            "ai_adaptive_profile_loaded profile_id=%s status=error_using_default error=%s",
            profile_id, type(exc).__name__,
        )
        return build_default_creator_profile(profile_id)


def save_creator_profile(profile: AICreatorPreferenceProfile) -> bool:
    """Persist profile to local JSON. Returns True on success. Never raises."""
    try:
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        path = _profile_path(profile.profile_id)
        data = sanitize_adaptive_profile(profile.to_dict())
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(
            "ai_adaptive_profile_updated profile_id=%s style=%s",
            profile.profile_id, profile.creator_style_preference,
        )
        return True
    except Exception as exc:
        logger.debug("adaptive_memory_save_error: %s", exc)
        return False


def update_creator_profile(
    profile: AICreatorPreferenceProfile,
    feedback: dict,
) -> AICreatorPreferenceProfile:
    """Apply feedback signals to profile and persist. Never raises.

    feedback keys (all optional):
        selected_creator_style   str  — creator style chosen this session
        selected_subtitle_style  str  — subtitle style chosen
        selected_pacing_style    str  — pacing style chosen
        selected_camera_style    str  — camera behavior chosen
        selected_duration_range  str  — duration range chosen
        selected_variant_strategy str — variant strategy chosen
        export_completed         bool — whether an export was completed
    """
    try:
        updated = AICreatorPreferenceProfile(
            profile_id=profile.profile_id,
            creator_style_preference=profile.creator_style_preference,
            preferred_subtitle_style=profile.preferred_subtitle_style,
            preferred_pacing_style=profile.preferred_pacing_style,
            preferred_camera_style=profile.preferred_camera_style,
            preferred_duration_range=profile.preferred_duration_range,
            preferred_variant_strategy=profile.preferred_variant_strategy,
            style_confidence=profile.style_confidence,
            subtitle_confidence=profile.subtitle_confidence,
            pacing_confidence=profile.pacing_confidence,
            camera_confidence=profile.camera_confidence,
            selection_history_count=profile.selection_history_count,
            export_history_count=profile.export_history_count,
            tags=list(profile.tags),
            warnings=[],
        )

        safe_feedback = sanitize_adaptive_profile(feedback) if isinstance(feedback, dict) else {}

        style = str(safe_feedback.get("selected_creator_style", "")).strip()
        if style:
            updated.creator_style_preference = style
            updated.style_confidence = _clamp(updated.style_confidence + _CONFIDENCE_INCREMENT)

        subtitle = str(safe_feedback.get("selected_subtitle_style", "")).strip()
        if subtitle:
            updated.preferred_subtitle_style = subtitle
            updated.subtitle_confidence = _clamp(updated.subtitle_confidence + _CONFIDENCE_INCREMENT)

        pacing = str(safe_feedback.get("selected_pacing_style", "")).strip()
        if pacing:
            updated.preferred_pacing_style = pacing
            updated.pacing_confidence = _clamp(updated.pacing_confidence + _CONFIDENCE_INCREMENT)

        camera = str(safe_feedback.get("selected_camera_style", "")).strip()
        if camera:
            updated.preferred_camera_style = camera
            updated.camera_confidence = _clamp(updated.camera_confidence + _CONFIDENCE_INCREMENT)

        duration = str(safe_feedback.get("selected_duration_range", "")).strip()
        if duration:
            updated.preferred_duration_range = duration

        variant = str(safe_feedback.get("selected_variant_strategy", "")).strip()
        if variant:
            updated.preferred_variant_strategy = variant

        updated.selection_history_count += 1

        if safe_feedback.get("export_completed"):
            updated.export_history_count += 1

        save_creator_profile(updated)
        return updated

    except Exception as exc:
        logger.debug("adaptive_memory_update_error: %s", exc)
        return profile


def _clamp(value) -> float:
    try:
        return max(_CONFIDENCE_MIN, min(_CONFIDENCE_MAX, float(value)))
    except Exception:
        return 0.0
