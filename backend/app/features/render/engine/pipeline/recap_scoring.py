"""
recap_scoring.py — the PURE RecapPlan → `scored` projection.

Extracted from recap_pipeline.py (2026-07-07) so lightweight consumers can
project a persisted RecapPlan without importing the whole render engine.

recap_pipeline.py pulls the full render stack at import time (llm_pipeline →
whisper, pipeline_render_loop → part_renderer → motion/crop → cv2, …). The
recap-plan polling route only needs this pure flattening logic — importing it
from recap_pipeline dragged those multi-hundred-MB deps onto the route-import
path, so on any install missing an engine dep the /jobs/{id}/recap-plan endpoint
silently failed (its broad try/except returned {available: False}).

This module depends ONLY on the RecapPlan dataclass shape (duck-typed via the
passed object) + stdlib, so a route can import it with no engine deps. It is
re-exported from recap_pipeline for backward compatibility, so existing callers
(``from …recap_pipeline import _scored_from_recap_plan``) are unchanged.
"""
from __future__ import annotations


def _scored_from_recap_plan(recap_plan) -> list[dict]:
    """Flatten RecapPlan episodes→acts→scenes into the chronological `scored`
    shape the render loop / part_renderer expects. Neutral scores (recap order
    is chronological, not viral-ranked). `episode_index` + `act_index` ride
    along so the finalize step can group scenes back into episodes (→ one output
    each) and acts (→ title cards). R6: `audio_mode` tells part_voice_mix whether
    to narrate or let the source audio play raw."""
    out: list[dict] = []
    _global_act = 0     # monotonically-increasing act id for title-card grouping
    for ep_i, ep in enumerate(recap_plan.episodes):
        n_acts = len(ep.acts)
        _prev_intent = ""   # N5: continuity resets at each episode boundary
        for act_local, act in enumerate(ep.acts):
            for scene in act.scenes:
                start = float(scene.start)
                end = float(scene.end)
                if end <= start:
                    continue
                _mode = "original" if (getattr(scene, "audio_mode", "narrate") == "original") else "narrate"
                # R3 + N5: compose the per-scene DIRECTOR'S INTENT — act position +
                # previous scene's intent + this scene's intent — so the narrator
                # tells ONE continuous story that flows scene→scene.
                _intent = (scene.narration_intent or "").strip()
                _act_tag = f"Act {act_local + 1}/{n_acts}"
                if act.title:
                    _act_tag += f" — {act.title}"
                if act.beat:
                    _act_tag += f" ({act.beat})"
                _ep_tag = f"Ep {ep_i + 1}/{len(recap_plan.episodes)}"
                _hint_parts = [f"[Recap {_ep_tag} · {_act_tag}]"]
                if _prev_intent:
                    _hint_parts.append(f"Previously: {_prev_intent}.")
                if _intent:
                    _hint_parts.append(f"Now: {_intent}")
                _editorial = " ".join(_hint_parts).strip() if (_intent or act.title or _prev_intent) else ""
                if _intent:
                    _prev_intent = _intent
                out.append({
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "viral_score": 50.0,
                    "hook_score": 50.0,
                    "motion_score": 50.0,
                    "diversity_score": 50.0,
                    "retention_score": 50.0,
                    "audio_energy": 50.0,
                    "clip_name": (scene.title or f"scene_{len(out)+1}"),
                    "ai_title": scene.title or "",
                    "ai_reason": scene.narration_intent or "",
                    "narration_intent": _intent,
                    "editorial_hint": _editorial,
                    # AI-authored recap narration. Empty for "original" scenes —
                    # part_voice_mix then skips voice and keeps the source audio.
                    "narration_text": (scene.narration or "").strip(),
                    "audio_mode": _mode,
                    "source": "recap",
                    "content_type_hint": "",
                    "is_climax": bool(scene.is_climax),
                    "episode_index": ep_i,
                    "episode_title": ep.title or "",
                    "act_index": _global_act,
                    "act_title": act.title or "",
                    "act_beat": act.beat or "",
                })
            _global_act += 1
    return out
