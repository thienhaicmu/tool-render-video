"""
visuals_stage.py — Story v2 visual-asset generation (extracted from
story_pipeline_v2.py, A0 refactor — behaviour unchanged).

Holds the per-render VISUAL asset generation the orchestrator drives before the cue
render: key-visual images (one per Visual), character reference sheets (Q3) and
environment reference sheets (G6). Grouped here so the orchestrator stays lean and
the character-master / overlay work (later phases) has a natural home.

All functions are best-effort (Sacred Contract #3 spirit): a per-visual failure
degrades to a solid-background fallback, a reference-sheet hiccup is non-fatal —
neither aborts the render.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.db.jobs_repo import update_story_plan
from app.features.render.engine.visual.story_image import generate_visual_image
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
                     *, job_id: str, effective_channel: str, provider: str = "gpt_image") -> list:
    """Generate one image per Visual → plan.render.visual_assets[vid]. Returns the
    list of visual_ids that FELL BACK (no image). Never raises per-visual.

    Images land in a PERSISTENT dir (``out_dir`` under CACHE_DIR, not the temp
    shots dir) so they survive the finalize cleanup and the live-monitor thumbnail
    endpoint can serve them during AND after the render. The plan is persisted +
    a ``story.visual.ready`` event emitted after EACH image so the FE reveals the
    visuals one by one (best-effort — a persist/emit hiccup never fails a visual)."""
    fallbacks: list = []
    total = plan.image_count()
    seed = int(plan.seed or 0)

    def _gen_one(v):
        # WORKER thread: pure image gen (network/file I/O). No DB, no plan mutation —
        # only reads plan.render.refs. Returns (visual_id, path|None). Never raises.
        try:
            out = out_dir / f"{v.id}.png"
            _rids = list(getattr(v, "character_ids", []) or [])
            _sid = (getattr(v, "setting_id", "") or "").strip()
            if _sid:
                _rids.append(_sid)                       # G6: environment ref too
            refs = {rid: plan.render.refs[rid] for rid in _rids if rid in plan.render.refs}
            return v.id, generate_visual_image(v, refs, art_style, img_w, img_h, str(out),
                                               seed=seed, provider=provider)
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

    workers = _worker_count("STORY_IMAGE_WORKERS", 3, total)
    if workers <= 1:
        for v in plan.visuals:
            vid, p = _gen_one(v)
            _collect(vid, p)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_gen_one, v): v.id for v in plan.visuals}
            for f in as_completed(futs):
                try:
                    vid, p = f.result()
                except Exception:
                    vid, p = futs[f], None
                _collect(vid, p)
    return fallbacks


def _generate_reference_sheets(plan, art_style: str, *, job_id: str,
                               effective_channel: str, provider: str) -> None:
    """Fill ``plan.render.refs[char_id]`` with a canonical reference-sheet path for
    every character present in the visuals, so gpt-image-1's image-edit keeps that
    character consistent across shots (Q3).

    ONLY for provider='gpt_image' (Pollinations is a URL API — it can't condition on a
    reference image, so free renders skip this and pay nothing extra). Env-gated by
    STORY_REFERENCE_SHEETS (default on). A series-pinned sheet is reused; a freshly
    generated one is pinned for later chapters. Best-effort — never raises."""
    if provider != "gpt_image" or os.getenv("STORY_REFERENCE_SHEETS", "1") != "1":
        return
    try:
        used: list[str] = []
        seen: set[str] = set()
        for v in plan.visuals:
            for cid in (getattr(v, "character_ids", None) or []):
                if cid and cid not in seen:
                    seen.add(cid); used.append(cid)
        if not used:
            return
        from app.features.render.engine.visual.story_reference_sheet import (
            generate_character_reference_sheet,
        )
        series_id = (getattr(plan, "series_id", "") or "").strip()
        for cid in used:
            if plan.render.refs.get(cid):
                continue
            c = plan.character(cid)
            if c is None:
                continue
            path = None
            if series_id:                      # reuse a sheet pinned by an earlier chapter
                try:
                    from app.db import story_repo
                    row = story_repo.get_character(cid)
                    rp = (row.get("reference_image_path") or "").strip() if row else ""
                    if rp and Path(rp).exists() and Path(rp).stat().st_size > 0:
                        path = rp
                except Exception:
                    path = None
            if not path:
                path = generate_character_reference_sheet(c, art_style=art_style)
                if path and series_id:         # pin for later chapters
                    try:
                        from app.db import story_repo
                        story_repo.upsert_character(
                            cid, series_id=series_id, name=c.name,
                            canonical_desc=c.canonical_desc, reference_image_path=path)
                    except Exception:
                        pass
            if not path:
                continue
            plan.render.refs[cid] = path
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.refsheet.ready", level="INFO",
                    message=f"Reference sheet ready for {c.name or cid}",
                    step="render.story", context={"character_id": cid, "refs": len(plan.render.refs)},
                )
            except Exception:
                pass
    except Exception as exc:
        logger.warning("story v2: reference sheets failed (non-fatal): %s", exc)


def _generate_env_reference_sheets(plan, art_style: str, *, job_id: str,
                                   effective_channel: str, provider: str) -> None:
    """Fill ``plan.render.refs[setting_id]`` with a canonical ENVIRONMENT reference
    sheet for each setting used by the visuals, so gpt-image-1's image-edit keeps the
    LOCATION consistent across shots + chapters (G6).

    ONLY for provider='gpt_image' AND a series (series_id set) — a one-off chapter
    can't reuse the sheet across chapters, so it pays nothing. OPT-IN via
    STORY_ENV_REFERENCE_SHEETS (default OFF): it adds a gpt-image-1 generation per
    setting AND an extra input image to every visual's image-edit, and its quality
    benefit is unproven — enable it only for a consistency-critical series. A
    series-pinned sheet is reused; a freshly generated one is pinned. Never raises."""
    series_id = (getattr(plan, "series_id", "") or "").strip()
    if (provider != "gpt_image" or not series_id
            or os.getenv("STORY_ENV_REFERENCE_SHEETS", "0") != "1"):
        return
    try:
        used: list[str] = []
        seen: set[str] = set()
        for v in plan.visuals:
            sid = (getattr(v, "setting_id", "") or "").strip()
            if sid and sid not in seen:
                seen.add(sid); used.append(sid)
        if not used:
            return
        from app.features.render.engine.visual.story_reference_sheet import (
            generate_environment_reference_sheet,
        )
        from app.db import story_repo
        for sid in used:
            if plan.render.refs.get(sid):
                continue
            s = plan.setting(sid)
            if s is None:
                continue
            path = None
            try:                                   # reuse a sheet pinned by an earlier chapter
                row = story_repo.get_environment(sid)
                rp = (row.get("reference_image_path") or "").strip() if row else ""
                if rp and Path(rp).exists() and Path(rp).stat().st_size > 0:
                    path = rp
            except Exception:
                path = None
            if not path:
                path = generate_environment_reference_sheet(s, art_style=art_style)
                if path:                           # pin for later chapters
                    try:
                        story_repo.upsert_environment(
                            sid, series_id=series_id, name=s.name,
                            canonical_desc=s.canonical_desc, reference_image_path=path)
                    except Exception:
                        pass
            if not path:
                continue
            plan.render.refs[sid] = path
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.envref.ready", level="INFO",
                    message=f"Environment reference ready for {s.name or sid}",
                    step="render.story", context={"setting_id": sid, "refs": len(plan.render.refs)})
            except Exception:
                pass
    except Exception as exc:
        logger.warning("story v2: env reference sheets failed (non-fatal): %s", exc)


__all__ = ["_worker_count", "_generate_images",
           "_generate_reference_sheets", "_generate_env_reference_sheets"]
