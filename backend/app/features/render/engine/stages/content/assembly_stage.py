"""
assembly_stage.py — join the rendered scene clips into the final video (CM-6
extract). A1 crossfade transitions (content-only assembler) with a fallback to
the plain shared concat, then CS-F background-music mix (ducked). Returns
``(final_out, res)`` where ``res`` carries the expected duration for QA. Raises
RuntimeError when the concat fails. Byte-for-byte the former inline block.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.stage import JobStage
from app.features.render.engine.pipeline.render_events import _job_log
from app.features.render.engine.stages.recap_assembler import concat_clips

logger = logging.getLogger("app.render.content")


def assemble_scenes(ctx, plan, payload, *, output_dir, output_stem, scene_clips, results, scenes, set_stage):
    """Assemble ``scene_clips`` → one video under ``output_dir``. Returns
    ``(final_out: Path, res: dict)``. Raises RuntimeError on concat failure."""
    job_id = ctx.job_id
    effective_channel = ctx.effective_channel
    width, height, fps = ctx.width, ctx.height, ctx.fps

    # 5. Assemble scenes → one video (reuse the recap assembler) -----------
    set_stage(JobStage.WRITING_REPORT, 88, "Assembling final video")
    final_out = output_dir / f"{output_stem}.mp4"
    _base = output_stem
    _n = 2
    while final_out.exists():
        final_out = output_dir / f"{_base} ({_n}).mp4"
        _n += 1
    # A1: join scenes with crossfade transitions per the AI's transition_hint.
    # Content-only assembler (never touches the shared concat_clips). Any
    # failure / disabled → fall back to the plain concat (hard cut).
    _res = None
    if os.getenv("CONTENT_TRANSITIONS", "1") == "1" and len(scene_clips) >= 2:
        try:
            from app.features.render.engine.stages.content_assembler import concat_with_transitions
            _ordered = sorted(results)
            # transition BEFORE each clip after the first = that scene's hint.
            _trans = [(getattr(scenes[idx - 1], "transition_hint", "") or "") for idx in _ordered[1:]]
            _res = concat_with_transitions(
                scene_clips, str(final_out), transitions=_trans,
                width=width, height=height, fps=fps,
            )
            if _res.get("ok"):
                _job_log(effective_channel, job_id,
                         f"Content: assembled with transitions ({_res.get('method')})")
            else:
                _res = None
        except Exception as _tx_exc:
            logger.warning("content: transition assembly failed (%s) — plain concat", _tx_exc)
            _res = None
    if not _res:
        _res = concat_clips(scene_clips, str(final_out), width=width, height=height, fps=fps)
    if not _res.get("ok"):
        raise RuntimeError("Content: assembly (concat) failed")

    # 5b. CS-F — mix background music (ducked under the narration) into the
    #     assembled video. Best-effort: a BGM failure keeps the non-BGM output
    #     (never fails the render). Runs BEFORE QA so the delivered file is
    #     validated with its final audio.
    _bgm = (getattr(payload, "content_bgm_path", "") or "").strip()
    # A2: no user BGM → auto-pick a track for the AI-planned mood from
    # BGM_DIR/{mood}/ (reuses the clips-path music library). Returns None when
    # the user hasn't added any music files → no BGM (unchanged behaviour).
    if not (_bgm and Path(_bgm).exists()) and os.getenv("CONTENT_AUTO_BGM", "1") == "1":
        try:
            from app.core.config import _pick_bgm_file
            _auto_bgm = _pick_bgm_file(getattr(plan, "bgm_mood", "") or "")
            if _auto_bgm:
                _bgm = _auto_bgm
                _job_log(effective_channel, job_id,
                         f"Content: auto BGM for mood '{plan.bgm_mood or 'default'}'")
        except Exception as _bgm_pick_exc:
            logger.warning("content: auto BGM pick failed (%s)", _bgm_pick_exc)
    if _bgm and Path(_bgm).exists():
        _bgm_tmp = str(final_out) + ".bgm.mp4"
        try:
            from app.features.render.engine.audio.mixer import mix_with_bgm
            mix_with_bgm(
                video_path=str(final_out), bgm_path=_bgm,
                output_path=_bgm_tmp, duck=True,
            )
            Path(_bgm_tmp).replace(final_out)
            _job_log(effective_channel, job_id, "Content: background music mixed (ducked)")
        except Exception as exc:
            logger.warning("content: BGM mix failed (non-fatal): %s", exc)
            try:
                Path(_bgm_tmp).unlink(missing_ok=True)
            except Exception:
                pass

    return final_out, _res
