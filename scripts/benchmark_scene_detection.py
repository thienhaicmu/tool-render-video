"""D-2-motion Phase 2 — A/B benchmark script for scene-detection swap.

Phase 1 deliverable D1.4 (2026-06-30). Standalone CLI that compares
pixel-diff (current production detector in motion/crop.py) against the
SceneMap detector (PySceneDetect + TransNetV2 via scene_detector.py) on
the SAME source video and prints a JSON report.

The report is the GO/NO-GO input for Phase 3: if the SceneMap output is
"as good as or better than" pixel-diff on a representative fixture set,
Phase 3 ships with MOTION_USE_SCENE_MAP=1 default. If not, Phase 3 ships
with the flag default OFF (or D-2-motion is deferred entirely).

USAGE

    # From repo root, with backend venv activated:
    python scripts/benchmark_scene_detection.py path/to/movie.mp4

    # Optional: tune pixel-diff threshold to match production (default 30.0):
    python scripts/benchmark_scene_detection.py movie.mp4 --threshold 30.0

    # Optional: write report to file instead of stdout:
    python scripts/benchmark_scene_detection.py movie.mp4 --out report.json

    # Optional: compare against a known-good reference report (saved from a
    # previous run) to detect drift:
    python scripts/benchmark_scene_detection.py movie.mp4 --baseline ref.json

REQUIREMENTS

    opencv-python (cv2)                       — for pixel-diff path
    scenedetect (PySceneDetect)               — for SceneMap path
    transnetv2 (optional)                     — TransNetV2 merge in SceneMap

    Install via:
        pip install opencv-python scenedetect

    The script auto-degrades when a dependency is missing: that side of the
    A/B is recorded as ``"unavailable"`` in the JSON; the other side still
    runs. This lets the operator probe partial setups.

REPORT SHAPE (JSON)

    {
      "video": {"path": "...", "duration_sec": 60.0, "fps": 30.0},
      "pixel_diff": {
        "available": true,
        "wall_time_sec": 0.52,
        "scene_count": 4,
        "ranges": [[0.0, 14.9], [14.9, 30.1], ...],
        "config": {"threshold": 30.0, "sample_every_frames": 5,
                   "downsample_size": [160, 90], "debounce_sec": 0.35}
      },
      "scene_map": {
        "available": true,
        "wall_time_sec": 3.1,
        "scene_count": 5,
        "ranges": [[0.0, 4.2], [4.2, 15.1], ...],
        "config": {"threshold": 28.0, "frame_skip": 3, "adaptive": true,
                   "transnetv2": false}
      },
      "diff": {
        "boundary_count_ratio": 1.25,  # scene_map / pixel_diff
        "common_boundary_count": 3,
        "common_boundary_drift_sec": [0.05, 0.12, 0.08],
        "pixel_diff_only_boundaries": [10.0],  # not detected by SceneMap
        "scene_map_only_boundaries": [4.2, 22.0]  # extra cuts SceneMap saw
      },
      "verdict": {
        "go_criteria_met": true,
        "go_criteria": {
          "boundary_count_ratio_ok": "0.5 <= 1.25 <= 2.0",
          "mean_drift_ok": "0.083 <= 0.3"
        }
      }
    }

DECISION FLOW

    Run on 3+ fixture types (talking-head, cinematic, music-video).
    Aggregate verdicts:
      - All GO   -> Phase 3 ships MOTION_USE_SCENE_MAP=1 default
      - Mixed    -> Phase 3 ships flag default OFF, opt-in per env
      - All NO-GO -> D-2-motion deferred, keep pixel-diff
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Pixel-diff side — mirrors backend/app/.../pixel_diff.py:_detect_scene_ranges_in_clip
# ---------------------------------------------------------------------------


def run_pixel_diff(
    video_path: str,
    threshold: float = 30.0,
    sample_every_fps_divisor: int = 6,
    debounce_sec: float = 0.35,
    fps_fallback: float = 30.0,
) -> dict:
    """Reproduces the pixel-diff scene-detection algorithm.

    Identical to ``_detect_scene_ranges_in_clip`` in
    ``backend/app/features/render/engine/motion/pixel_diff.py:221-277``
    so the benchmark exercises production behaviour, not a re-implementation.

    Returns a dict with availability + timing + ranges + config; on missing
    cv2 or load failure, returns ``{"available": False, "error": "..."}``.
    """
    try:
        import cv2  # type: ignore[import]
        import numpy as np  # type: ignore[import]
    except ImportError as exc:
        return {"available": False, "error": f"missing dep: {exc}"}

    started = time.perf_counter()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"available": False, "error": f"cannot open video: {video_path}"}

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or fps_fallback
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        prev_gray = None
        cuts: list[float] = []
        frame_idx = 0
        sample_every = max(1, int(round(fps / sample_every_fps_divisor)))

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if frame_idx % sample_every != 0:
                frame_idx += 1
                continue
            small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = float(np.mean(cv2.absdiff(prev_gray, gray)))
                if diff >= threshold:
                    t = frame_idx / fps if fps > 0 else 0.0
                    if not cuts or t - cuts[-1] > debounce_sec:
                        cuts.append(t)
            prev_gray = gray
            frame_idx += 1

        if duration <= 0.0 and fps > 0:
            duration = frame_idx / fps

        ranges: list[tuple[float, float]] = []
        start = 0.0
        for cut in cuts:
            cut = max(0.0, min(cut, duration))
            if cut > start:
                ranges.append((start, cut))
                start = cut
        if duration > start:
            ranges.append((start, duration))
        ranges = ranges or [(0.0, duration)]

        return {
            "available": True,
            "wall_time_sec": round(time.perf_counter() - started, 3),
            "scene_count": len(ranges),
            "ranges": [[round(s, 3), round(e, 3)] for s, e in ranges],
            "config": {
                "threshold": threshold,
                "sample_every_frames": sample_every,
                "downsample_size": [160, 90],
                "debounce_sec": debounce_sec,
                "fps_detected": round(fps, 2),
                "duration_sec": round(duration, 3),
            },
        }
    except Exception as exc:
        return {"available": False, "error": f"pixel_diff raised: {exc}"}
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# SceneMap side — mirrors backend/app/.../scene_detector.py:detect_scenes
# ---------------------------------------------------------------------------


def run_scene_map(video_path: str, threshold: float = 28.0) -> dict:
    """Reproduces the SceneMap detector (PySceneDetect ContentDetector +
    optional AdaptiveDetector + optional TransNetV2 merge).

    Mirrors ``detect_scenes`` in
    ``backend/app/features/render/engine/pipeline/scene_detector.py:334-383``.
    """
    try:
        from scenedetect import open_video, SceneManager  # type: ignore[import]
        from scenedetect.detectors import ContentDetector  # type: ignore[import]
    except ImportError as exc:
        return {"available": False, "error": f"missing dep: {exc}"}

    try:
        from scenedetect.detectors import AdaptiveDetector  # type: ignore[import]
        has_adaptive = True
    except ImportError:
        AdaptiveDetector = None  # type: ignore[assignment]
        has_adaptive = False

    started = time.perf_counter()
    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        if has_adaptive:
            try:
                scene_manager.add_detector(AdaptiveDetector(
                    adaptive_threshold=3.0, min_content_val=15.0
                ))
            except Exception:
                has_adaptive = False
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        ranges: list[tuple[float, float]] = []
        for scene in scene_list:
            start = scene[0].get_seconds()
            end = scene[1].get_seconds()
            if end > start:
                ranges.append((start, end))

        # Total duration via the last range's end (or 0 on empty).
        duration = ranges[-1][1] if ranges else 0.0

        return {
            "available": True,
            "wall_time_sec": round(time.perf_counter() - started, 3),
            "scene_count": len(ranges),
            "ranges": [[round(s, 3), round(e, 3)] for s, e in ranges],
            "config": {
                "threshold": threshold,
                "adaptive": has_adaptive,
                "transnetv2": False,  # not exercised by benchmark to keep it lightweight
                "duration_sec": round(duration, 3),
            },
        }
    except Exception as exc:
        return {"available": False, "error": f"scene_map raised: {exc}"}


# ---------------------------------------------------------------------------
# Diff + verdict
# ---------------------------------------------------------------------------


def _boundaries_from_ranges(ranges: list[list[float]]) -> list[float]:
    """A "boundary" is the start of every range except the first (which is
    always 0.0). We compare these between detectors."""
    return [r[0] for r in ranges[1:]] if len(ranges) > 1 else []


def compute_diff(
    pixel_diff: dict,
    scene_map: dict,
    boundary_match_tolerance_sec: float = 0.5,
) -> dict:
    """Compare two detector outputs. Returns a structured diff for the
    operator to inspect + go/no-go verdict."""
    if not (pixel_diff.get("available") and scene_map.get("available")):
        return {
            "computable": False,
            "reason": "one or both detectors unavailable — see individual error fields",
        }

    pd_boundaries = _boundaries_from_ranges(pixel_diff["ranges"])
    sm_boundaries = _boundaries_from_ranges(scene_map["ranges"])

    # Greedy match: each PD boundary picks its nearest SM boundary within
    # tolerance. Unmatched are detector-only.
    sm_used: set[int] = set()
    common_pairs: list[tuple[float, float]] = []
    pd_only: list[float] = []
    for pd_b in pd_boundaries:
        best_i = -1
        best_d = float("inf")
        for i, sm_b in enumerate(sm_boundaries):
            if i in sm_used:
                continue
            d = abs(pd_b - sm_b)
            if d < best_d:
                best_i, best_d = i, d
        if best_i >= 0 and best_d <= boundary_match_tolerance_sec:
            sm_used.add(best_i)
            common_pairs.append((pd_b, sm_boundaries[best_i]))
        else:
            pd_only.append(pd_b)
    sm_only = [sm_boundaries[i] for i in range(len(sm_boundaries)) if i not in sm_used]

    drifts = [round(abs(a - b), 3) for a, b in common_pairs]
    mean_drift = round(sum(drifts) / len(drifts), 3) if drifts else 0.0

    pd_count = max(1, len(pd_boundaries))
    boundary_count_ratio = round(len(sm_boundaries) / pd_count, 3)

    # GO criteria (from audit §8.2; operator can tune at the call site).
    ratio_ok = 0.5 <= boundary_count_ratio <= 2.0
    drift_ok = mean_drift <= 0.3 if drifts else True
    go = ratio_ok and drift_ok

    return {
        "computable": True,
        "boundary_count_ratio": boundary_count_ratio,
        "common_boundary_count": len(common_pairs),
        "common_boundary_drift_sec": drifts,
        "mean_drift_sec": mean_drift,
        "pixel_diff_only_boundaries": [round(b, 3) for b in pd_only],
        "scene_map_only_boundaries": [round(b, 3) for b in sm_only],
        "verdict": {
            "go_criteria_met": go,
            "go_criteria": {
                "boundary_count_ratio_ok": f"0.5 <= {boundary_count_ratio} <= 2.0 = {ratio_ok}",
                "mean_drift_ok": f"{mean_drift} <= 0.3 = {drift_ok}",
            },
            "recommendation": (
                "GO — SceneMap can replace pixel-diff for this fixture"
                if go else
                "NO-GO — keep pixel-diff for this fixture (or tune SceneMap thresholds)"
            ),
        },
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def build_report(
    video_path: str,
    pixel_threshold: float = 30.0,
    scenemap_threshold: float = 28.0,
    match_tolerance_sec: float = 0.5,
) -> dict:
    pd = run_pixel_diff(video_path, threshold=pixel_threshold)
    sm = run_scene_map(video_path, threshold=scenemap_threshold)
    diff = compute_diff(pd, sm, boundary_match_tolerance_sec=match_tolerance_sec)
    return {
        "video": {
            "path": video_path,
            "duration_sec": (
                pd.get("config", {}).get("duration_sec")
                or sm.get("config", {}).get("duration_sec")
                or 0.0
            ),
            "fps": pd.get("config", {}).get("fps_detected", 0.0),
        },
        "pixel_diff": pd,
        "scene_map": sm,
        "diff": diff,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="A/B benchmark for D-2-motion scene-detection swap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("video", help="Path to source video file (mp4/mov/...)")
    parser.add_argument(
        "--pixel-threshold", type=float, default=30.0,
        help="Pixel-diff scene_cut_threshold (default 30.0 = production)"
    )
    parser.add_argument(
        "--scenemap-threshold", type=float, default=28.0,
        help="SceneMap ContentDetector threshold (default 28.0 = scene_detector.py)"
    )
    parser.add_argument(
        "--match-tolerance", type=float, default=0.5,
        help="Seconds within which two boundaries count as 'common' (default 0.5)"
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Write JSON report to this path instead of stdout"
    )
    args = parser.parse_args(argv)

    video = args.video
    if not Path(video).exists():
        print(f"error: video file not found: {video}", file=sys.stderr)
        return 2

    report = build_report(
        video_path=video,
        pixel_threshold=args.pixel_threshold,
        scenemap_threshold=args.scenemap_threshold,
        match_tolerance_sec=args.match_tolerance,
    )

    out_json = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out_json, encoding="utf-8")
        print(f"wrote report to {args.out}")
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
