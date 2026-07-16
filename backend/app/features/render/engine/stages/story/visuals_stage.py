"""
visuals_stage.py — Story v2 visual-asset generation (SVG-only).

Holds the per-render VISUAL asset generation the orchestrator drives before the cue
render: procedural SVG key-visuals (one per Visual) and the per-(speaker, emotion,
pose) transparent overlay masters. Story Mode is SVG-only — everything here is offline
and $0 (the paid gpt-image / free Pollinations key-visual + reference-sheet paths were
removed).

All functions are best-effort (Sacred Contract #3 spirit): a per-visual failure
degrades to a solid-background fallback, a master hiccup simply means that beat renders
background-only — neither aborts the render.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.db.jobs_repo import update_story_plan
from app.features.render.engine.pipeline.render_events import _emit_render_event

logger = logging.getLogger("app.render.story")


def _worker_count(env_name: str, default: int, n_items: int) -> int:
    """Bounded worker count for a parallel phase: env override, capped at the item
    count, floored at 1. ``=1`` restores the serial path (byte-identical rollback)."""
    try:
        w = int(os.getenv(env_name, str(default)) or default)
    except (TypeError, ValueError):
        w = default
    return max(1, min(w, max(1, int(n_items or 1))))


def _generate_images(plan, out_dir: Path, art_style: str, img_w: int, img_h: int,
                     *, job_id: str, effective_channel: str, provider: str = "svg") -> list:
    """Compose one procedural SVG image per Visual → plan.render.visual_assets[vid].
    Returns the list of visual_ids that FELL BACK (no image). Never raises per-visual.

    Images land in a PERSISTENT dir (``out_dir`` under CACHE_DIR, not the temp shots dir)
    so they survive the finalize cleanup and the live-monitor thumbnail endpoint can serve
    them during AND after the render. The plan is persisted + a ``story.visual.ready``
    event emitted after EACH image so the FE reveals the visuals one by one (best-effort).

    ``provider`` is accepted for call-site compatibility but Story Mode is SVG-only."""
    fallbacks: list = []
    total = plan.image_count()

    # A Visual whose image is ALREADY an existing file (a library background assigned in
    # Review, carried in the plan override) is NOT regenerated — skip it.
    def _ready(vid: str) -> bool:
        p = plan.render.visual_assets.get(vid) or ""
        try:
            return bool(p) and Path(p).exists() and Path(p).stat().st_size > 0
        except Exception:
            return False
    gen_visuals = [v for v in plan.visuals if not _ready(v.id)]

    # N4 overlay: the key-visual is composed BACKGROUND-ONLY and the speaking character is
    # composited per-beat at cue render (emotion + pose aware). DEFAULT ON — the per-beat
    # emotion/pose the AI emits only shows via the overlay. Opt out with STORY_CHAR_OVERLAY=0
    # (→ characters baked static into the key-visual).
    _overlay = os.getenv("STORY_CHAR_OVERLAY", "1") != "0"

    def _gen_one(v):
        # WORKER thread: pure SVG compose + raster (file I/O). No DB, no plan mutation.
        # Returns (visual_id, path|None). Never raises.
        try:
            out = out_dir / f"{v.id}.png"
            from app.features.render.engine.visual.svg_compose import compose_visual
            from app.features.render.engine.visual.svg_raster import save_svg_png
            _svg = compose_visual(plan, v, img_w, img_h, chars=not _overlay)
            _p = save_svg_png(_svg, str(out), img_w, img_h, opaque_bg="#101820") if _svg else None
            return v.id, _p
        except Exception:
            return v.id, None

    def _collect(vid, p):
        # MAIN thread only: mutate plan + persist + emit (serial → no lock needed).
        if p:
            plan.render.visual_assets[vid] = p
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.visual.ready", level="INFO",
                    message=f"Key-visual {vid} ready ({len(plan.render.visual_assets)}/{total})",
                    step="render.story",
                    context={"visual_id": vid, "done": len(plan.render.visual_assets), "total": total},
                )
            except Exception:
                pass
        else:
            fallbacks.append(vid)

    workers = _worker_count("STORY_IMAGE_WORKERS", 3, len(gen_visuals))
    if workers <= 1:
        for v in gen_visuals:
            vid, p = _gen_one(v)
            _collect(vid, p)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_gen_one, v): v.id for v in gen_visuals}
            for f in as_completed(futs):
                try:
                    vid, p = f.result()
                except Exception:
                    vid, p = futs[f], None
                _collect(vid, p)
    return fallbacks


def _generate_character_masters(plan, art_style: str, *, job_id: str, effective_channel: str) -> None:
    """Fill ``plan.render.masters[speaker_id]`` with a procedural SVG transparent CHARACTER
    MASTER for every speaker the timeline overlays (a beat with char_anchor != 'none';
    A3 — the base-video overlay target). Best-effort — a master that can't be composed
    simply leaves that character with NO overlay. One master per character, content-
    addressed + reused. Never raises."""
    try:
        used: list[str] = []
        seen: set[str] = set()
        for b in plan.timeline:
            sp = (getattr(b, "speaker_id", "") or "").strip()
            if sp and (getattr(b, "char_anchor", "none") or "none") != "none" and sp not in seen:
                seen.add(sp); used.append(sp)
        if not used:
            return
        for cid in used:
            if plan.render.masters.get(cid):
                continue
            c = plan.character(cid)
            if c is None:
                continue
            # V3: the approved identity master → else the deterministic V3 renderer.
            try:
                from app.features.render.engine.visual.library_v3 import (
                    render_planner_character_png, resolve_character_preview,
                )
                from app.features.render.engine.visual.library_v3.style_aliases import normalize_v3_style
                from app.core.config import APP_DATA_DIR
                path = resolve_character_preview(
                    getattr(c, "visual_identity_id", "") or "", framing="full_body")
                if not path:
                    path = render_planner_character_png(
                        c, Path(APP_DATA_DIR) / "content_assets" / f"v3_master_{cid}.png",
                        style_id=normalize_v3_style(art_style))
            except Exception:
                path = None
            if not path:
                continue
            plan.render.masters[cid] = path
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.master.ready", level="INFO",
                    message=f"Character master ready for {c.name or cid}",
                    step="render.story", context={"character_id": cid, "masters": len(plan.render.masters)})
            except Exception:
                pass
    except Exception as exc:
        logger.warning("story v2: character masters failed (non-fatal): %s", exc)


def _generate_overlay_masters(plan, out_dir, *, job_id: str, effective_channel: str) -> None:
    """N4 — fill ``plan.render.masters['cid:emotion:pose']`` with a transparent per-(speaker,
    emotion, pose) master for the overlay path: the V3 identity master, else the
    deterministic V3 procedural renderer with that emotion + pose. Only speakers on a
    beat drive this. Best-effort — a missing master simply means that beat renders
    background-only. Never raises. Self-gated by STORY_CHAR_OVERLAY (default ON —
    opt out with =0)."""
    if os.getenv("STORY_CHAR_OVERLAY", "1") == "0":
        return
    try:
        used: dict[str, set] = {}                            # cid → {(emotion, pose), ...}
        for b in plan.timeline:
            # P3 — iterate the beat's LINES (effective_lines() = the multi-line dialogue,
            # or the single legacy line) so every on-screen speaker/emotion/pose gets a master.
            for ln in b.effective_lines():
                sp = (getattr(ln, "speaker_id", "") or "").strip()
                if sp:
                    used.setdefault(sp, set()).add((
                        (getattr(ln, "emotion", "normal") or "normal").strip().lower(),
                        (getattr(ln, "pose", "stand") or "stand").strip().lower()))
        if not used:
            return
        from app.features.render.engine.visual.library_v3 import (
            render_planner_character_png, resolve_character_preview,
        )
        from app.features.render.engine.visual.library_v3.style_aliases import normalize_v3_style
        _out = Path(out_dir)
        _style_id = normalize_v3_style(getattr(plan, "art_style", "") or "")
        for cid, pairs in used.items():
            c = plan.character(cid)
            if c is None:
                continue
            path = resolve_character_preview(
                getattr(c, "visual_identity_id", "") or "", framing="full_body")
            for emo, pose in pairs:
                key = f"{cid}:{emo}:{pose}"
                if not plan.render.masters.get(key):
                    _path = path or render_planner_character_png(
                        c, _out / f"master_{cid}_{emo}_{pose}.png",
                        emotion=emo, pose=pose, style_id=_style_id)
                    if _path:
                        plan.render.masters[key] = _path
        try:
            update_story_plan(job_id, plan.to_json())
        except Exception:
            pass
    except Exception as exc:
        logger.warning("story v2: overlay masters failed (non-fatal): %s", exc)


__all__ = ["_worker_count", "_generate_images", "_generate_character_masters",
           "_generate_overlay_masters"]
