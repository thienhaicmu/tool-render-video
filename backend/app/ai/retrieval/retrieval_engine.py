"""
retrieval_engine.py — Retrieval-based creator intelligence engine. Phase 41.

Retrieves creator intelligence patterns and safely influences rendering metadata.
Deterministic, local-only, no internet, no model training, no subprocess.
Never mutates payload. Never raises.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.retrieval.retrieval_schema import AICreatorRetrievalMatch, AICreatorRetrievalPack
from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe, sanitize_retrieval_match

logger = logging.getLogger("app.ai.retrieval.retrieval_engine")


def retrieve_creator_intelligence(
    edit_plan: Any,
    payload: Any = None,
    context: Any = None,
) -> AICreatorRetrievalPack:
    """Retrieve creator intelligence patterns from Phase 39/40 registry.

    Returns an AICreatorRetrievalPack. Never raises. Never mutates payload.
    Local pattern registry only — no internet, no model training.
    """
    try:
        logger.debug("ai_creator_retrieval_started")

        if edit_plan is None:
            return AICreatorRetrievalPack(
                available=False,
                warnings=["retrieval_skipped:no_edit_plan"],
            )

        # Collect signals from existing AI metadata
        signals = _collect_signals(edit_plan)

        # Load available patterns from Phase 40 registry
        available_patterns = _load_patterns_from_plan(edit_plan)

        if not available_patterns:
            logger.debug("ai_creator_retrieval_skipped: no_patterns_available")
            return AICreatorRetrievalPack(
                available=True,
                enabled=False,
                warnings=["retrieval_skipped:no_patterns_available"],
            )

        # Apply heuristics and build matches
        matches = _build_matches(signals, available_patterns)

        # Determine recommended creator style
        recommended_style = _recommend_creator_style(signals, matches)

        if matches:
            logger.info(
                "ai_creator_retrieval_completed matches=%d recommended_style=%s",
                len(matches), recommended_style,
            )
            for m in matches[:3]:
                logger.debug(
                    "ai_creator_retrieval_match id=%s type=%s score=%.2f",
                    m.match_id, m.pattern_type, m.retrieval_score,
                )

        return AICreatorRetrievalPack(
            available=True,
            enabled=len(matches) > 0,
            retrieval_mode="assistive_only",
            matches=matches,
            recommended_creator_style=recommended_style,
            warnings=[],
        )

    except Exception as exc:
        logger.debug("ai_creator_retrieval_error: %s", exc)
        return AICreatorRetrievalPack(
            available=False,
            enabled=False,
            warnings=[f"retrieval_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Signal collection — reads existing AI metadata from edit_plan
# ---------------------------------------------------------------------------

def _collect_signals(edit_plan: Any) -> dict:
    """Collect heuristic signals from available edit_plan metadata. Never raises."""
    signals: dict = {
        "pacing_style": "default",
        "energy_level": None,
        "creator_style": "",
        "subtitle_density": "normal",
        "hook_score": 0.0,
        "retention_risk": False,
        "retention_risk_types": [],
        "story_type": "",
        "has_beat": False,
        "emotion": "neutral",
    }
    try:
        # Pacing signals
        pacing = getattr(edit_plan, "pacing", None)
        if pacing is not None:
            signals["pacing_style"] = str(getattr(pacing, "pacing_style", "default") or "default")
            energy = getattr(pacing, "energy_level", None)
            if energy is not None:
                try:
                    signals["energy_level"] = float(energy)
                except (TypeError, ValueError):
                    pass
            signals["emotion"] = str(getattr(pacing, "emotion", "neutral") or "neutral")
            signals["has_beat"] = bool(getattr(pacing, "beat_available", False))

        # Creator style signals
        creator_style_dict = getattr(edit_plan, "creator_style", None)
        if isinstance(creator_style_dict, dict):
            detected = creator_style_dict.get("detected_style", "")
            if isinstance(detected, str) and detected:
                signals["creator_style"] = detected

        # Creator style adaptation
        creator_adapt = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(creator_adapt, dict) and not signals["creator_style"]:
            adapted = creator_adapt.get("target_style", "")
            if isinstance(adapted, str) and adapted:
                signals["creator_style"] = adapted

        # Subtitle density signals
        subtitle_exec = getattr(edit_plan, "subtitle_execution", None)
        if isinstance(subtitle_exec, dict):
            density = subtitle_exec.get("density", "normal")
            if isinstance(density, str) and density:
                signals["subtitle_density"] = density

        subtitle_apply = getattr(edit_plan, "subtitle_text_apply", None)
        if isinstance(subtitle_apply, dict):
            density = subtitle_apply.get("applied_density", "") or subtitle_apply.get("density", "")
            if isinstance(density, str) and density:
                signals["subtitle_density"] = density

        # Retention risk signals
        retention = getattr(edit_plan, "retention", None)
        if isinstance(retention, dict):
            risk_regions = retention.get("risk_regions", [])
            if isinstance(risk_regions, list) and risk_regions:
                signals["retention_risk"] = True
                for region in risk_regions:
                    if isinstance(region, dict):
                        risk_type = region.get("type", "")
                        if risk_type:
                            signals["retention_risk_types"].append(risk_type)
            hook_score = retention.get("hook_score", 0.0)
            try:
                signals["hook_score"] = float(hook_score)
            except (TypeError, ValueError):
                pass

        # Story type signals
        story = getattr(edit_plan, "story", None)
        if isinstance(story, dict):
            story_type = story.get("story_type", "") or story.get("narrative_type", "")
            if isinstance(story_type, str) and story_type:
                signals["story_type"] = story_type

        # Hook score from clip candidates
        clip_candidates = getattr(edit_plan, "clip_candidate_discovery", None)
        if isinstance(clip_candidates, dict) and signals["hook_score"] == 0.0:
            best_score = clip_candidates.get("best_score", 0.0)
            try:
                signals["hook_score"] = float(best_score)
            except (TypeError, ValueError):
                pass

    except Exception as exc:
        logger.debug("collect_signals_error: %s", exc)

    return signals


# ---------------------------------------------------------------------------
# Pattern loading — from Phase 40 edit_plan.creator_patterns
# ---------------------------------------------------------------------------

def _load_patterns_from_plan(edit_plan: Any) -> List[dict]:
    """Load available patterns from the Phase 40 registry via pattern_registry. Never raises."""
    try:
        from app.ai.knowledge.pattern_registry import (
            get_patterns_by_type,
            _PATTERN_CACHE,
            _resolve_base_path,
        )
        resolved = _resolve_base_path(None)
        cache_key = str(resolved)

        # Trigger registry load if not cached
        if cache_key not in _PATTERN_CACHE:
            from app.ai.knowledge.pattern_registry import load_pattern_registry
            load_pattern_registry()

        all_patterns = _PATTERN_CACHE.get(cache_key, [])
        return [p.to_dict() for p in all_patterns]

    except Exception as exc:
        logger.debug("load_patterns_from_plan_error: %s", exc)
        # Fallback: read from edit_plan dict representation
        try:
            creator_patterns = getattr(edit_plan, "creator_patterns", {})
            if isinstance(creator_patterns, dict):
                # Can't reconstruct individual patterns from registry summary dict
                return []
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Match building — heuristics applied to signals + available patterns
# ---------------------------------------------------------------------------

def _build_matches(signals: dict, available_patterns: List[dict]) -> List[AICreatorRetrievalMatch]:
    """Apply retrieval heuristics and build AICreatorRetrievalMatch objects. Never raises."""
    matches: List[AICreatorRetrievalMatch] = []
    try:
        pacing_style = signals.get("pacing_style", "default")
        energy_level = signals.get("energy_level")
        creator_style = signals.get("creator_style", "")
        subtitle_density = signals.get("subtitle_density", "normal")
        hook_score = signals.get("hook_score", 0.0)
        retention_risk = signals.get("retention_risk", False)
        retention_risk_types = signals.get("retention_risk_types", [])
        story_type = signals.get("story_type", "")
        has_beat = signals.get("has_beat", False)

        is_high_energy = (
            pacing_style in ("fast", "high_energy", "high_energy_shortform", "shortform")
            or (energy_level is not None and energy_level > 0.65)
        )
        is_podcast = (
            pacing_style in ("calm", "calm_storytelling", "podcast", "storytelling")
            or "podcast" in creator_style.lower()
            or story_type in ("narrative", "storytelling", "conversational")
        )
        has_strong_hook = hook_score > 0.70
        subtitle_overloaded = subtitle_density in ("dense", "overloaded", "high")
        has_retention_decay = retention_risk and any(
            t in ("silence_gap", "dead_air", "drop_off", "decay")
            for t in retention_risk_types
        )

        seen_ids: set = set()

        for pattern in available_patterns:
            if not isinstance(pattern, dict):
                continue
            pid = pattern.get("pattern_id", "")
            ptype = pattern.get("pattern_type", "")
            style = pattern.get("creator_style", "")
            confidence = float(pattern.get("confidence", 0.0))
            tags = pattern.get("tags", [])
            if not isinstance(tags, list):
                tags = []

            match = _try_match_pattern(
                pattern=pattern,
                pid=pid,
                ptype=ptype,
                style=style,
                confidence=confidence,
                tags=tags,
                creator_style=creator_style,
                is_high_energy=is_high_energy,
                is_podcast=is_podcast,
                has_strong_hook=has_strong_hook,
                subtitle_overloaded=subtitle_overloaded,
                has_retention_decay=has_retention_decay,
                has_beat=has_beat,
            )
            if match is not None and match.match_id not in seen_ids:
                seen_ids.add(match.match_id)
                matches.append(match)

        # Sort by retrieval_score descending, keep top 10
        matches.sort(key=lambda m: m.retrieval_score, reverse=True)
        return matches[:10]

    except Exception as exc:
        logger.debug("build_matches_error: %s", exc)
        return []


def _try_match_pattern(
    pattern: dict,
    pid: str,
    ptype: str,
    style: str,
    confidence: float,
    tags: List[str],
    creator_style: str,
    is_high_energy: bool,
    is_podcast: bool,
    has_strong_hook: bool,
    subtitle_overloaded: bool,
    has_retention_decay: bool,
    has_beat: bool,
) -> Optional[AICreatorRetrievalMatch]:
    """Evaluate one pattern and return a match if heuristics fire. Never raises."""
    try:
        retrieval_score = 0.0
        explanation: List[str] = []
        matched_tags: List[str] = []

        # --- Hook patterns ---
        if ptype == "hook":
            if has_strong_hook and any(t in tags for t in ("rapid", "question", "curiosity")):
                retrieval_score = min(95.0, confidence * 100 + 10)
                explanation.append("Strong hook score drives rapid/curiosity hook retrieval")
                matched_tags = [t for t in tags if t in ("hook", "rapid", "question", "curiosity")]
            elif has_strong_hook:
                retrieval_score = confidence * 80
                explanation.append("Strong hook score — hook pattern retrieved")
                matched_tags = [t for t in tags if t == "hook"]

        # --- Subtitle patterns ---
        elif ptype == "subtitle":
            if subtitle_overloaded and any(t in tags for t in ("compact", "viral")):
                retrieval_score = min(90.0, confidence * 100 + 5)
                explanation.append("Subtitle overload triggers compact subtitle pattern retrieval")
                matched_tags = [t for t in tags if t in ("subtitle", "compact", "viral")]
            elif is_podcast and any(t in tags for t in ("podcast", "readable", "conversational")):
                retrieval_score = min(85.0, confidence * 95)
                explanation.append("Podcast/storytelling content — readable subtitle pattern retrieved")
                matched_tags = [t for t in tags if t in ("subtitle", "podcast", "readable")]
            elif is_high_energy and any(t in tags for t in ("compact", "tiktok")):
                retrieval_score = confidence * 80
                explanation.append("High-energy shortform — compact subtitle retrieved")
                matched_tags = [t for t in tags if t in ("subtitle", "compact", "tiktok")]

        # --- Pacing patterns ---
        elif ptype == "pacing":
            if is_high_energy and any(t in tags for t in ("fast", "high_energy", "shortform")):
                retrieval_score = min(90.0, confidence * 100)
                explanation.append("High-energy shortform — fast pacing pattern retrieved")
                matched_tags = [t for t in tags if t in ("pacing", "fast", "high_energy", "shortform")]
            elif is_podcast and any(t in tags for t in ("calm", "storytelling", "conversational")):
                retrieval_score = min(85.0, confidence * 95)
                explanation.append("Podcast/storytelling — calm pacing pattern retrieved")
                matched_tags = [t for t in tags if t in ("pacing", "calm", "storytelling")]
            elif has_beat and any(t in tags for t in ("beat", "sync", "rhythm")):
                retrieval_score = confidence * 75
                explanation.append("Beat-available content — rhythm-pacing pattern retrieved")
                matched_tags = [t for t in tags if t in ("pacing", "beat", "sync")]

        # --- Camera patterns ---
        elif ptype == "camera":
            if is_high_energy and any(t in tags for t in ("dynamic", "tiktok", "shortform")):
                retrieval_score = min(88.0, confidence * 100)
                explanation.append("High-energy shortform — dynamic camera pattern retrieved")
                matched_tags = [t for t in tags if t in ("camera", "dynamic", "tiktok")]
            elif is_podcast and any(t in tags for t in ("static", "podcast", "cinematic")):
                retrieval_score = confidence * 80
                explanation.append("Podcast/storytelling — calm camera pattern retrieved")
                matched_tags = [t for t in tags if t in ("camera", "static", "podcast", "cinematic")]

        # --- Retention patterns ---
        elif ptype == "retention":
            if has_retention_decay and any(t in tags for t in ("loop", "reengagement", "payoff")):
                retrieval_score = min(92.0, confidence * 100 + 8)
                explanation.append("Retention decay detected — reengagement pattern retrieved")
                matched_tags = [t for t in tags if t in ("retention", "loop", "reengagement", "payoff")]
            elif not has_retention_decay and any(t in tags for t in ("retention", "payoff")):
                retrieval_score = confidence * 60
                explanation.append("Retention pattern available as enhancement")
                matched_tags = [t for t in tags if t in ("retention", "payoff")]

        # --- Creator style similarity ---
        if creator_style and style and (
            creator_style.lower() == style.lower()
            or creator_style.lower() in style.lower()
            or style.lower() in creator_style.lower()
        ):
            retrieval_score = min(100.0, retrieval_score + 8)
            explanation.append(f"Creator style similarity: {creator_style} ↔ {style}")

        if retrieval_score <= 0:
            return None

        # Build influence dicts from pattern data
        subtitle_influence = _extract_subtitle_influence(pattern)
        pacing_influence = _extract_pacing_influence(pattern)
        camera_influence = _extract_camera_influence(pattern)
        retention_influence = _extract_retention_influence(pattern)
        hook_influence = _extract_hook_influence(pattern)

        match_id = f"retrieval_{ptype}_{pid}"

        raw = {
            "match_id": match_id,
            "creator_style": style,
            "pattern_type": ptype,
            "confidence": confidence,
            "retrieval_score": round(retrieval_score, 4),
        }
        if not is_retrieval_match_safe(raw):
            return None

        return AICreatorRetrievalMatch(
            match_id=match_id,
            creator_style=style,
            pattern_type=ptype,
            confidence=confidence,
            retrieval_score=round(retrieval_score, 4),
            matched_tags=matched_tags,
            subtitle_influence=subtitle_influence,
            pacing_influence=pacing_influence,
            camera_influence=camera_influence,
            retention_influence=retention_influence,
            hook_influence=hook_influence,
            safe=True,
            warnings=[],
            explanation=explanation,
        )

    except Exception as exc:
        logger.debug("try_match_pattern_error pid=%s: %s", pid, exc)
        return None


# ---------------------------------------------------------------------------
# Influence extractors — safe, metadata-only
# ---------------------------------------------------------------------------

def _extract_subtitle_influence(pattern: dict) -> dict:
    """Extract subtitle influence from pattern. Safe metadata only. Never raises."""
    try:
        sub = pattern.get("subtitle_patterns", {})
        if not isinstance(sub, dict) or not sub:
            return {}
        allowed = {"density", "max_words_per_line", "keyword_emphasis", "capitalize_keywords", "style"}
        return {k: v for k, v in sub.items() if k in allowed}
    except Exception:
        return {}


def _extract_pacing_influence(pattern: dict) -> dict:
    """Extract pacing influence from pattern. Safe metadata only. Never raises."""
    try:
        pac = pattern.get("pacing_patterns", {})
        if not isinstance(pac, dict) or not pac:
            return {}
        allowed = {"cut_rate", "style", "energy_target", "rhythm", "transition_style"}
        return {k: v for k, v in pac.items() if k in allowed}
    except Exception:
        return {}


def _extract_camera_influence(pattern: dict) -> dict:
    """Extract camera influence from pattern. Safe metadata only. Never raises."""
    try:
        cam = pattern.get("camera_patterns", {})
        if not isinstance(cam, dict) or not cam:
            return {}
        allowed = {"behavior", "zoom_emphasis", "subject_lock", "motion_smoothing", "mode"}
        return {k: v for k, v in cam.items() if k in allowed}
    except Exception:
        return {}


def _extract_retention_influence(pattern: dict) -> dict:
    """Extract retention influence from pattern. Safe metadata only. Never raises."""
    try:
        ret = pattern.get("retention_patterns", {})
        if not isinstance(ret, dict) or not ret:
            return {}
        allowed = {"hook_style", "payoff_timing", "reengagement_cadence", "avoid_silence_gaps"}
        return {k: v for k, v in ret.items() if k in allowed}
    except Exception:
        return {}


def _extract_hook_influence(pattern: dict) -> dict:
    """Extract hook influence from pattern. Safe metadata only. Never raises."""
    try:
        hooks = pattern.get("hook_patterns", [])
        if not isinstance(hooks, list) or not hooks:
            return {}
        return {"patterns": [str(h) for h in hooks[:10]]}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Creator style recommendation
# ---------------------------------------------------------------------------

def _recommend_creator_style(signals: dict, matches: List[AICreatorRetrievalMatch]) -> str:
    """Recommend a creator style from matches and signals. Never raises."""
    try:
        # Prefer existing detected style
        existing = signals.get("creator_style", "")
        if existing:
            return existing

        # Use style from highest-scored match with a style set
        for m in matches:
            if m.creator_style:
                return m.creator_style

        return ""
    except Exception:
        return ""
