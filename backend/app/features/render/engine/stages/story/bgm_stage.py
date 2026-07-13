"""
bgm_stage.py — Story v2 background-music mix + delivered-transition helper
(extracted from story_pipeline_v2.py, A0 refactor — behaviour unchanged).

``_mix_scene_bgm`` builds the placed-BGM track (s4: intro/outro/under/none per
beat; STORY_BGM_PLACED=0 restores continuous mood-runs) and ducks it under the
narration, overwriting the final video in place BEFORE QA (so the delivered file is
validated with music). Best-effort — any failure yields a video WITHOUT music and
never fails the render (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log

logger = logging.getLogger("app.render.story")


def _delivered_transitions(cues: list, delivered_idx: list) -> list:
    """len-1 transition list aligned to the DELIVERED clips (skips failed cues): use
    the NEXT delivered cue's transition. Pure, never raises."""
    trans: list = []
    for i in range(len(delivered_idx) - 1):
        nxt = cues[delivered_idx[i + 1] - 1]
        trans.append(getattr(nxt, "transition", "") or "fade")
    return trans


def _mix_scene_bgm(job_id, effective_channel, plan, final_out, work_dir) -> None:
    """Dựng track nhạc nền per-scene (mood do AI plan) + duck dưới lời kể, ghi đè
    ``final_out`` tại chỗ. Best-effort — thiếu file nhạc / bất kỳ lỗi nào → giao video
    KHÔNG nhạc, không bao giờ fail render (Sacred Contract #3 spirit). Chạy TRƯỚC QA
    nên file giao được validate kèm nhạc (Sacred Contract #8)."""
    tmp = str(final_out) + ".bgm.mp4"
    try:
        total = float(getattr(plan.render, "total_sec", 0.0) or 0.0)
        from app.features.render.engine.audio.mixer import (
            build_placed_bgm_track, build_scene_bgm_track, mix_with_bgm,
        )
        bgm_dir = Path(work_dir) / "story_bgm"
        # s4 PLACED BGM (default): music sits at the AI-chosen spot in each beat
        # (intro/outro/under/none). STORY_BGM_PLACED=0 → legacy continuous mood-runs.
        if os.getenv("STORY_BGM_PLACED", "1") == "1":
            segments = plan.bgm_cues()
            if not segments:
                return
            track = build_placed_bgm_track(segments, total, str(bgm_dir / "bgm_timeline.wav"))
        else:
            segments = plan.bgm_scenes()
            if not segments:
                return
            track = build_scene_bgm_track(segments, total, str(bgm_dir / "bgm_timeline.wav"))
        if not track:
            _job_log(effective_channel, job_id,
                     "Story v2: no BGM (no music files for the planned moods — see BGM_DIR)")
            return
        # The track ALREADY carries each scene's gain (build_placed_bgm_track applies the
        # per-beat bgm_intensity → dB). Pass bgm_db_gain=0 so mix_with_bgm does NOT
        # attenuate a SECOND time (the old default -18 dB stacked on top → ~-36 dB,
        # near-inaudible). Duck GENTLY (ratio 2.5 vs the default 6) so the music stays
        # present under the near-continuous story narration. Both env-tunable.
        try:
            _bgm_gain = float(os.getenv("STORY_BGM_GAIN_DB", "0") or 0)
        except (TypeError, ValueError):
            _bgm_gain = 0.0
        _duck = os.getenv("STORY_BGM_DUCK_PARAMS",
                          "sidechaincompress=threshold=0.05:ratio=2.5:attack=25:release=500")
        mix_with_bgm(video_path=str(final_out), bgm_path=track, output_path=tmp, duck=True,
                     bgm_db_gain=_bgm_gain, duck_params=_duck)
        Path(tmp).replace(final_out)
        moods = sorted({(seg[0] or "default") for seg in segments})
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="story.bgm.ready",
            level="INFO", message=f"Background music mixed ({len(segments)} scene(s))",
            step="render.story", context={"scenes": len(segments), "moods": moods},
        )
        _job_log(effective_channel, job_id,
                 f"Story v2: BGM mixed ({len(segments)} scene(s), moods={moods})")
    except Exception as exc:
        logger.warning("story v2: BGM mix failed (non-fatal): %s", exc)
        try:
            if Path(tmp).exists():
                Path(tmp).unlink()
        except Exception:
            pass


__all__ = ["_delivered_transitions", "_mix_scene_bgm"]
