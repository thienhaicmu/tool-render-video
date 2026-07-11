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


def _match_library_background(plan, visual):
    """Phase A — offline library-first: resolve a stock BACKGROUND for a CHARACTER-LESS
    Visual (establishing shot) before paying for AI. Returns an on-disk path or None.
    Never raises.

    Same precedence as svg_compose._bg_layer (single policy): the AI-chosen
    ``setting.asset`` slug (exact, library-pick) → a fuzzy ``scene_kind``/name match. Only
    for a Visual with NO character_ids — the image cue render does not overlay characters,
    so a plain library background would drop them; those keep AI gen. This is the gated
    (STORY_LIBRARY_FIRST) early-exit for the PAID gpt-image flow; the SVG path resolves the
    same precedence inline in svg_compose (unconditional, since library ≥ procedural)."""
    try:
        if getattr(visual, "character_ids", None):
            return None
        s = plan.setting(getattr(visual, "setting_id", "") or "")
        from app.db.story_asset_repo import get_by_slug, match_asset
        asset = ((getattr(s, "asset", "") or "").strip()) if s else ""
        if asset:                                        # AI-chosen library-pick (exact) wins
            p = get_by_slug(asset, "background")
            if p:
                return p
        name = ((getattr(s, "scene_kind", "") or getattr(s, "name", "")) if s else "").strip()
        if not name:
            return None
        return match_asset("background", name=name,
                           region=(getattr(plan, "region", "") or ""),
                           genre=(getattr(plan, "genre_key", "") or ""))
    except Exception:
        return None


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

    # AL3 library-first: a Visual whose image is ALREADY set to an existing file (a
    # library background assigned in Review, carried in the plan override) is NOT
    # regenerated — skip it, no AI call. Keeps render.visual_assets as-is.
    def _ready(vid: str) -> bool:
        p = plan.render.visual_assets.get(vid) or ""
        try:
            return bool(p) and Path(p).exists() and Path(p).stat().st_size > 0
        except Exception:
            return False
    gen_visuals = [v for v in plan.visuals if not _ready(v.id)]

    # Phase A — offline library-first: auto-match a stock BACKGROUND for character-less
    # Visuals before paying for AI. Gated by STORY_LIBRARY_FIRST (off by default →
    # byte-identical). A matched visual is filled + dropped from gen_visuals (skip AI).
    if os.getenv("STORY_LIBRARY_FIRST", "0") == "1":
        _matched: list = []
        for v in list(gen_visuals):
            p = _match_library_background(plan, v)
            if p:
                plan.render.visual_assets[v.id] = p
                _matched.append(v.id)
        if _matched:
            gen_visuals = [v for v in gen_visuals if v.id not in _matched]
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            for vid in _matched:
                try:
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="story.visual.matched", level="INFO",
                        message=f"Key-visual {vid} matched from library (no AI)",
                        step="render.story",
                        context={"visual_id": vid, "done": len(plan.render.visual_assets), "total": total})
                except Exception:
                    pass

    # Hard cost cap (premium only): STORY_MAX_PREMIUM_IMAGES > 0 limits how many
    # key-visuals are gpt-image-generated; the rest fall back to a solid background.
    # 0 = unlimited (default — no behaviour change). Bounds runaway spend on a long story.
    if provider == "gpt_image":
        try:
            _cap = int(os.getenv("STORY_MAX_PREMIUM_IMAGES", "0") or 0)
        except (TypeError, ValueError):
            _cap = 0
        if _cap > 0 and len(gen_visuals) > _cap:
            _capped = [v.id for v in gen_visuals[_cap:]]
            gen_visuals = gen_visuals[:_cap]
            fallbacks.extend(_capped)
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.visual.capped", level="WARNING",
                    message=(f"Premium image cap reached ({_cap}) — {len(_capped)} visual(s) "
                             f"use a solid background."),
                    step="render.story", context={"cap": _cap, "capped": _capped})
            except Exception:
                pass

    # Phase B/C — procedural SVG image path. Active when provider=="svg" (the FE default
    # since Phase C) OR env STORY_SVG_GEN=1 (global override). Composes background +
    # characters into a wide PNG offline ($0). On failure it degrades: provider=="svg" ->
    # solid fallback; env-gate mode -> falls through to AI (gpt-image), never worse than before.
    _svg_mode = (provider == "svg") or (os.getenv("STORY_SVG_GEN", "0") == "1")
    # N4 overlay: key-visual is BACKGROUND-ONLY and the speaking character is composited
    # per-beat at cue render (emotion-aware). SVG mode + STORY_CHAR_OVERLAY only.
    _overlay = _svg_mode and (os.getenv("STORY_CHAR_OVERLAY", "0") == "1")

    def _gen_one(v):
        # WORKER thread: pure image gen (network/file I/O). No DB, no plan mutation —
        # only reads plan.render.refs. Returns (visual_id, path|None). Never raises.
        try:
            out = out_dir / f"{v.id}.png"
            if _svg_mode:
                try:
                    from app.features.render.engine.visual.svg_compose import compose_visual
                    from app.features.render.engine.visual.svg_raster import save_svg_png
                    _svg = compose_visual(plan, v, img_w, img_h, chars=not _overlay)
                    _p = save_svg_png(_svg, str(out), img_w, img_h, opaque_bg="#101820") if _svg else None
                except Exception:
                    _p = None
                if _p:
                    return v.id, _p
                if provider == "svg":
                    return v.id, None                    # strict svg -> solid fallback (no AI)
                # env-gate trial: fall through to AI below
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


def _generate_character_masters(plan, art_style: str, *, job_id: str, effective_channel: str) -> None:
    """Fill ``plan.render.masters[speaker_id]`` with a cutout-ready transparent CHARACTER
    MASTER PNG for every speaker the timeline overlays (a beat with char_anchor != 'none';
    A3). Best-effort — a master that can't be generated (no key / error) simply leaves
    that character with NO overlay (the cue renders video-only). One master per character,
    content-addressed + reused (a Review preview is reused). Never raises."""
    try:
        used: list[str] = []
        seen: set[str] = set()
        for b in plan.timeline:
            sp = (getattr(b, "speaker_id", "") or "").strip()
            if sp and (getattr(b, "char_anchor", "none") or "none") != "none" and sp not in seen:
                seen.add(sp); used.append(sp)
        if not used:
            return
        from app.features.render.engine.visual.story_reference_sheet import generate_character_master
        library_first = os.getenv("STORY_LIBRARY_FIRST", "0") == "1"
        for cid in used:
            if plan.render.masters.get(cid):
                continue
            c = plan.character(cid)
            if c is None:
                continue
            # AL5 library-first (opt-in): reuse a matching offline library character
            # (transparent master) by name before paying for AI gen — free + consistent
            # for recurring named characters. Default off → byte-identical (path stays None).
            path = None
            if library_first:
                try:
                    from app.db.story_asset_repo import match_asset
                    path = match_asset("character", getattr(c, "name", "") or "",
                                       transparent_only=True)
                except Exception:
                    path = None
            if not path:
                path = generate_character_master(c, art_style=art_style)
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


_LIB_EMOTIONS = ("happy", "angry", "sad", "surprised")   # emotion variants that exist in the library
_LIB_POSES = ("wave", "cheer", "point", "hip")           # pose variants that exist in the library


def _generate_overlay_masters(plan, out_dir, *, job_id: str, effective_channel: str) -> None:
    """N4 — fill ``plan.render.masters['cid:emotion']`` with a transparent per-(speaker,
    emotion) master for the image-overlay path. A library-picked character (character.asset)
    uses its ``{asset}_{emotion}`` variant (else the base asset); a procedural character is
    svg_char-generated with that emotion. Only speakers on a beat drive this. Best-effort —
    a missing master simply means that beat renders background-only. Never raises.
    Self-gated by STORY_CHAR_OVERLAY (default off) so a stray call is a no-op."""
    if os.getenv("STORY_CHAR_OVERLAY", "0") != "1":
        return
    try:
        used: dict[str, set] = {}                            # cid → {(emotion, pose), ...}
        for b in plan.timeline:
            sp = (getattr(b, "speaker_id", "") or "").strip()
            if sp:
                used.setdefault(sp, set()).add((
                    (getattr(b, "emotion", "normal") or "normal").strip().lower(),
                    (getattr(b, "pose", "stand") or "stand").strip().lower()))
        if not used:
            return
        from app.features.render.engine.visual.svg_char import build_char, emotion_expr
        from app.features.render.engine.visual.svg_raster import save_svg_png
        from app.features.render.engine.visual.svg_presets import preset
        from app.db.story_asset_repo import get_by_slug
        region = (getattr(plan, "region", "") or "")
        genre = (getattr(plan, "genre_key", "") or "")
        _out = Path(out_dir)
        for cid, pairs in used.items():
            c = plan.character(cid)
            if c is None:
                continue
            asset = (getattr(c, "asset", "") or "").strip()
            for emo, pose in pairs:
                key = f"{cid}:{emo}:{pose}"
                if plan.render.masters.get(key):
                    continue
                path = None
                if asset:                                   # library: pose variant → emotion variant → base
                    vp = pose if pose in _LIB_POSES else ""
                    ve = emo if emo in _LIB_EMOTIONS else ""
                    path = (get_by_slug(f"{asset}_{vp}", "character") if vp else None) \
                        or (get_by_slug(f"{asset}_{ve}", "character") if ve else None) \
                        or get_by_slug(asset, "character")
                if not path:                                # procedural chibi with this emotion + pose
                    opts = preset(getattr(c, "archetype", "") or "", region, genre, getattr(c, "gender", "") or "")
                    opts["expr"] = emotion_expr(emo)
                    opts["pose"] = pose
                    path = save_svg_png(build_char(opts), str(_out / f"master_{cid}_{emo}_{pose}.png"), 1024, 1536)
                if not path:
                    continue
                plan.render.masters[key] = path
        try:
            update_story_plan(job_id, plan.to_json())
        except Exception:
            pass
    except Exception as exc:
        logger.warning("story v2: overlay masters failed (non-fatal): %s", exc)


__all__ = ["_worker_count", "_generate_images", "_generate_reference_sheets",
           "_generate_env_reference_sheets", "_generate_character_masters",
           "_generate_overlay_masters"]
