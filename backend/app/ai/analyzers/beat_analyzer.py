"""
beat_analyzer.py — Optional audio beat detection via librosa.

No hard import at module level. Returns a safe unavailable dict if
librosa is not installed, audio_path is None/missing, or any error occurs.

Public API:
    is_beat_analysis_available() -> bool
    analyze_beats(audio_path: str | None) -> dict

Return shape:
    {
        "available":  bool,
        "bpm":        float | None,
        "beats":      list[float],
        "energy": {
            "mean":  float | None,
            "peak":  float | None,
            "curve": list[dict],   # max 64 points: [{"t": float, "e": float}]
        },
        "warnings": list[str],
    }
"""
from __future__ import annotations

from typing import Optional

from app.ai.dependencies import has_librosa

_MAX_CURVE_POINTS = 64


def is_beat_analysis_available() -> bool:
    return has_librosa()


def analyze_beats(audio_path: Optional[str]) -> dict:
    """Detect BPM, beat timestamps, and energy curve from an audio file.

    Returns a safe result dict regardless of librosa availability or errors.
    Never raises.
    """
    _empty_energy = {"mean": None, "peak": None, "curve": []}

    if audio_path is None:
        return {
            "available": False,
            "bpm": None,
            "beats": [],
            "energy": _empty_energy,
            "warnings": ["no_audio_path"],
        }

    if not has_librosa():
        return {
            "available": False,
            "bpm": None,
            "beats": [],
            "energy": _empty_energy,
            "warnings": ["librosa_not_installed"],
        }

    try:
        import librosa  # type: ignore

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)

        # Beat tracking
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)

        # Energy analysis — RMS, downsampled to max 64 points
        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(rms.mean()) if len(rms) > 0 else None
        energy_peak = float(rms.max()) if len(rms) > 0 else None
        curve = _build_energy_curve(rms, sr)

        return {
            "available": True,
            "bpm": round(bpm, 2),
            "beats": [round(t, 4) for t in beat_times],
            "energy": {
                "mean": round(energy_mean, 6) if energy_mean is not None else None,
                "peak": round(energy_peak, 6) if energy_peak is not None else None,
                "curve": curve,
            },
            "warnings": [],
        }
    except FileNotFoundError:
        return {
            "available": True,
            "bpm": None,
            "beats": [],
            "energy": _empty_energy,
            "warnings": ["audio_file_not_found"],
        }
    except Exception as exc:
        return {
            "available": True,
            "bpm": None,
            "beats": [],
            "energy": _empty_energy,
            "warnings": [f"analysis_error: {type(exc).__name__}"],
        }


def _build_energy_curve(rms: "Any", sr: int) -> list[dict]:
    """Downsample RMS array to at most _MAX_CURVE_POINTS time-indexed entries."""
    try:
        import librosa  # type: ignore

        n = len(rms)
        if n == 0:
            return []

        step = max(1, n // _MAX_CURVE_POINTS)
        indices = list(range(0, n, step))[:_MAX_CURVE_POINTS]
        times = librosa.frames_to_time(indices, sr=sr)

        return [
            {"t": round(float(times[i]), 2), "e": round(float(rms[indices[i]]), 6)}
            for i in range(len(indices))
        ]
    except Exception:
        return []
