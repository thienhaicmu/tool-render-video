"""
beat_analyzer.py — Optional audio beat detection via librosa.

No hard import at module level. Returns a safe unavailable dict if
librosa is not installed or audio loading fails.

Public API:
    is_beat_analysis_available() -> bool
    analyze_beats(audio_path: str) -> dict
"""
from __future__ import annotations

from app.ai.dependencies import has_librosa


def is_beat_analysis_available() -> bool:
    return has_librosa()


def analyze_beats(audio_path: str) -> dict:
    """Detect BPM and beat timestamps from an audio file.

    Returns a safe result dict regardless of librosa availability or errors.
    """
    if not has_librosa():
        return {
            "available": False,
            "bpm": None,
            "beats": [],
            "warnings": ["librosa_not_installed"],
        }

    try:
        import librosa  # type: ignore

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        # librosa ≥0.10 returns tempo as a 1-element array
        bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)

        return {
            "available": True,
            "bpm": round(bpm, 2),
            "beats": [round(t, 4) for t in beat_times],
            "warnings": [],
        }
    except FileNotFoundError:
        return {
            "available": True,
            "bpm": None,
            "beats": [],
            "warnings": ["audio_file_not_found"],
        }
    except Exception as exc:
        return {
            "available": True,
            "bpm": None,
            "beats": [],
            "warnings": [f"analysis_error: {type(exc).__name__}"],
        }
