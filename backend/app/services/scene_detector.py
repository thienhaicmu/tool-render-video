from __future__ import annotations

import subprocess
from typing import List, Dict

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
    if _HAS_ADAPTIVE:
        try:
            scene_manager.add_detector(_AdaptiveDetector())
        except Exception:
            pass
    scene_manager.detect_scenes(video, frame_skip=frame_skip)

    scene_list = scene_manager.get_scene_list()
    if not scene_list:
        return []

    cut_scores = _compute_transition_scores(video_path, scene_list)

    return [
        {
            "start": start.get_seconds(),
            "end": end.get_seconds(),
            "transition_score": cut_scores[i] if i < len(cut_scores) else 1.0,
        }
        for i, (start, end) in enumerate(scene_list)
    ]
