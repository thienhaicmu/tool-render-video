from __future__ import annotations

import subprocess
from typing import List, Dict

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector


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
    scene_manager.detect_scenes(video, frame_skip=frame_skip)

    scene_list = scene_manager.get_scene_list()
    if not scene_list:
        return []

    return [
        {
            "start": start.get_seconds(),
            "end": end.get_seconds(),
            "transition_score": 1.0,
        }
        for start, end in scene_list
    ]
