from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import List, Dict

logger = logging.getLogger(__name__)

import cv2
import numpy as np
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

try:
    from scenedetect.detectors import AdaptiveDetector as _AdaptiveDetector
    _HAS_ADAPTIVE = True
except ImportError:
    _HAS_ADAPTIVE = False


def _get_video_fps(video_path: str) -> float:
    """Read FPS via ffprobe; fall back to 30.0 on any error."""
    try:
        from app.services.bin_paths import get_ffprobe_bin
        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        if "/" in out:
            a, b = out.split("/")
            return float(a) / float(b) if float(b) else 30.0
        return float(out) if out else 30.0
    except Exception:
        return 30.0


def _auto_frame_skip(fps: float) -> int:
    """
    Choose how many frames to skip between analyzed frames.

    Target: analyze ~8-10 fps regardless of source FPS.
    This gives ~3-5x speed-up on 30fps and ~6x on 60fps video
    while keeping scene-cut detection accurate (cuts are abrupt,
    so a few frames of temporal uncertainty doesn't matter).

    frame_skip=N means scenedetect reads every (N+1)th frame.
    """
    target_analyze_fps = 8.0
    skip = max(0, int(fps / target_analyze_fps) - 1)
    # Cap at 7 (analyze every 8th frame) to avoid missing very short scenes
    return min(skip, 7)


def _compute_transition_scores(video_path: str, scene_list: list) -> List[float]:
    """Sample pixel delta at each scene cut boundary to produce a real transition_score.

    Returns one score per scene in [0.1, 1.0].  The first scene always gets 1.0
    because there is no preceding cut.  Scores reflect how hard the visual cut was —
    higher = more abrupt visual change.
    """
    if not scene_list:
        return []
    scores: List[float] = [1.0]  # scene 0 has no preceding cut
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return [1.0] * len(scene_list)
        for start, _end in scene_list[1:]:
            cut_frame = max(0, start.get_frames() - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, cut_frame)
            ok1, f1 = cap.read()
            ok2, f2 = cap.read()
            if ok1 and ok2 and f1 is not None and f2 is not None:
                s1 = cv2.resize(f1, (64, 36), interpolation=cv2.INTER_AREA)
                s2 = cv2.resize(f2, (64, 36), interpolation=cv2.INTER_AREA)
                diff = float(np.mean(np.abs(s1.astype(np.float32) - s2.astype(np.float32))))
                # Abrupt cuts typically produce diff 30–80; normalise to [0.1, 1.0]
                scores.append(min(1.0, max(0.1, diff / 55.0)))
            else:
                scores.append(0.5)
        cap.release()
    except Exception:
        while len(scores) < len(scene_list):
            scores.append(1.0)
    return scores


def _compute_silence_features(video_path: str, scenes: list) -> list:
    """Enrich scene dicts with silence-based scoring signal via FFmpeg silencedetect.

    Adds ``silence_score`` [-8, 20] per scene — purely additive to scene_quality:
      pre_pause_bonus (+8 max):  silence ending ≤0.5s before scene start → hook entry
      rhythm_bonus    (+10 max): 1–3 natural pauses (0.3–1.2s) within scene
      trailing_bonus  (+4 max):  scene ends in silence → natural cut point
      dead_air_penalty (-8 max): total silence >35% of scene → dead air

    Returns unmodified scenes on any failure (silence_score defaults to 0.0 downstream).
    Skipped when SILENCE_SCORING_ENABLED=0.
    """
    if not scenes or os.environ.get("SILENCE_SCORING_ENABLED", "1") != "1":
        return scenes
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        cmd = [
            get_ffmpeg_bin(), "-hide_banner",
            "-i", video_path,
            "-vn",
            "-af", "silencedetect=noise=-40dB:d=0.3",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        stderr = result.stderr

        raw_starts = re.findall(r"silence_start:\s*([\d.]+)", stderr)
        raw_ends   = re.findall(r"silence_end:\s*([\d.]+)", stderr)
        if not raw_starts:
            return scenes

        silence_ivs: List[tuple] = []
        for i, s_str in enumerate(raw_starts):
            s = float(s_str)
            e = float(raw_ends[i]) if i < len(raw_ends) else s + 0.3
            silence_ivs.append((s, e, e - s))

        enriched: List[Dict] = []
        for sc in scenes:
            sc_s = float(sc["start"])
            sc_e = float(sc["end"])
            sc_dur = max(sc_e - sc_s, 0.001)

            # Pre-scene pause: silence ending within 0.5s before scene start.
            pre_dur = max(
                (d for s, e, d in silence_ivs if e <= sc_s and e >= sc_s - 0.5 and 0.3 <= d <= 1.5),
                default=0.0,
            )
            pre_pause_bonus = min(8.0, pre_dur * 6.0)

            # Rhythm pauses: natural 0.3–1.2s pauses fully within the scene.
            rhythm = [d for s, e, d in silence_ivs if s >= sc_s and e <= sc_e and 0.3 <= d <= 1.2]
            n_r = len(rhythm)
            if n_r == 0:
                rhythm_bonus = 0.0
            elif n_r <= 3:
                rhythm_bonus = min(10.0, n_r * 4.0)
            else:
                rhythm_bonus = max(0.0, 10.0 - (n_r - 3) * 2.0)

            # Trailing silence: scene ends in silence.
            trailing = any(s <= sc_e - 0.3 and e >= sc_e for s, e, d in silence_ivs)
            trailing_bonus = 4.0 if trailing else 0.0

            # Dead air: total overlapping silence > 35% of scene.
            total_sil = sum(
                min(e, sc_e) - max(s, sc_s)
                for s, e, d in silence_ivs
                if e > sc_s and s < sc_e
            )
            sil_ratio = total_sil / sc_dur
            dead_air_penalty = min(8.0, max(0.0, (sil_ratio - 0.35) * 32.0))

            silence_score = max(-8.0, min(20.0,
                pre_pause_bonus + rhythm_bonus + trailing_bonus - dead_air_penalty
            ))
            enriched.append({**sc, "silence_score": round(silence_score, 3)})

        logger.info(
            "silence_features_computed scenes=%d silence_intervals=%d",
            len(scenes), len(silence_ivs),
        )
        return enriched
    except Exception as _exc:
        logger.debug("silence_features_failed: %s", _exc)
        return scenes


def detect_scenes(
    video_path: str,
    threshold: float = 28.0,
    frame_skip: int | None = None,
) -> List[Dict]:
    """
    Detect scene boundaries in *video_path*.

    Parameters
    ----------
    video_path  : path to the input video
    threshold   : ContentDetector sensitivity (lower = more scenes)
    frame_skip  : frames to skip between analyses; None = auto-tune from FPS.
                  Pass 0 to disable skipping (original behaviour).

    Returns
    -------
    list of {"start": float, "end": float, "transition_score": float}
    """
    if frame_skip is None:
        fps = _get_video_fps(video_path)
        frame_skip = _auto_frame_skip(fps)

    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))

    _adaptive_active = False
    if _HAS_ADAPTIVE and os.environ.get("SCENE_ADAPTIVE_ENABLED", "1") == "1":
        try:
            scene_manager.add_detector(_AdaptiveDetector(
                adaptive_threshold=3.0,
                min_content_val=15.0,
            ))
            _adaptive_active = True
            logger.info("scene_adaptive_detector_active threshold=3.0 min_content_val=15.0")
        except Exception as _adaptive_exc:
            logger.warning("scene_adaptive_add_failed: %s", _adaptive_exc)

    scene_manager.detect_scenes(video, frame_skip=frame_skip)

    scene_list = scene_manager.get_scene_list()
    logger.info(
        "scene_detection_complete scene_count=%d adaptive=%s frame_skip=%d",
        len(scene_list), _adaptive_active, frame_skip,
    )
    if not scene_list:
        return []

    cut_scores = _compute_transition_scores(video_path, scene_list)

    _results = [
        {
            "start": start.get_seconds(),
            "end": end.get_seconds(),
            "transition_score": cut_scores[i] if i < len(cut_scores) else 1.0,
        }
        for i, (start, end) in enumerate(scene_list)
    ]

    _results = _compute_silence_features(video_path, _results)
    _silence_active = any("silence_score" in sc for sc in _results)
    logger.info("scene_enrichment_complete silence_data=%s", _silence_active)

    if os.getenv("RENDER_DEBUG_LOG", "0") == "1":
        for i, sc in enumerate(_results):
            logger.debug(
                "scene_boundary idx=%d start=%.3f end=%.3f transition_score=%.3f",
                i, sc["start"], sc["end"], sc["transition_score"],
            )
    return _results
