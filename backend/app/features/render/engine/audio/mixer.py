import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin


def _has_audio_stream(input_path: str) -> bool:
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(input_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def _probe_duration_s(path: str) -> float:
    """Return duration in seconds via ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                get_ffprobe_bin(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def mix_narration_audio(
    *,
    video_path: str,
    narration_audio_path: str,
    mix_mode: str,
    output_path: str,
    playback_speed: float = 1.0,
) -> str:
    """Mix a TTS narration track into the rendered video.

    playback_speed: the effective render speed (base + platform delta).  When
    != 1.0, an atempo filter is applied to the narration stream so its tempo
    matches the speed-adjusted video.  Without this, the narration drifts
    behind (speed > 1.0) or runs ahead (speed < 1.0) of the video content.
    """
    source_video = Path(video_path)
    narration_audio = Path(narration_audio_path)
    mixed_output = Path(output_path)

    if not source_video.exists():
        raise RuntimeError("Rendered video not found for narration mix")
    if not narration_audio.exists():
        raise RuntimeError("Narration audio file not found")

    try:
        speed = max(0.5, min(2.0, float(playback_speed or 1.0)))
    except Exception:
        speed = 1.0
    apply_atempo = abs(speed - 1.0) > 1e-4

    # Probe once — used to cap output at video duration instead of TTS duration.
    # Without this, -shortest would truncate to the shorter TTS stream (~15s)
    # instead of the full video duration (~52s).
    _vdur = _probe_duration_s(str(source_video))
    _dur_args = ["-t", str(_vdur)] if _vdur > 0 else []

    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [ffmpeg_bin, "-y", "-i", str(source_video), "-i", str(narration_audio)]

    if str(mix_mode or "").strip() == "replace_original":
        if apply_atempo:
            cmd += [
                "-filter_complex", f"[1:a]atempo={speed:.4f},apad[narr]",
                "-map", "0:v:0",
                "-map", "[narr]",
                "-c:v", "copy",
                "-c:a", "aac",
                *_dur_args,
                str(mixed_output),
            ]
        else:
            cmd += [
                "-filter_complex", "[1:a]apad[narr]",
                "-map", "0:v:0",
                "-map", "[narr]",
                "-c:v", "copy",
                "-c:a", "aac",
                *_dur_args,
                str(mixed_output),
            ]
    elif str(mix_mode or "").strip() == "keep_original_low":
        if _has_audio_stream(str(source_video)):
            if apply_atempo:
                cmd += [
                    "-filter_complex",
                    f"[0:a]volume=0.25[a0];[1:a]atempo={speed:.4f},apad,volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    *_dur_args,
                    str(mixed_output),
                ]
            else:
                cmd += [
                    "-filter_complex",
                    "[0:a]volume=0.25[a0];[1:a]apad,volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    *_dur_args,
                    str(mixed_output),
                ]
        else:
            if apply_atempo:
                cmd += [
                    "-filter_complex", f"[1:a]atempo={speed:.4f},apad[narr]",
                    "-map", "0:v:0",
                    "-map", "[narr]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    *_dur_args,
                    str(mixed_output),
                ]
            else:
                cmd += [
                    "-filter_complex", "[1:a]apad[narr]",
                    "-map", "0:v:0",
                    "-map", "[narr]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    *_dur_args,
                    str(mixed_output),
                ]
    else:
        raise RuntimeError("Unsupported narration audio mix mode")

    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Narration audio mix failed: {detail or exc}") from exc

    if not mixed_output.exists() or mixed_output.stat().st_size <= 0:
        raise RuntimeError("Narration audio mix failed: output file was not created")
    return str(mixed_output)


def mix_with_bgm(
    *,
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_db_gain: float = -18.0,
) -> str:
    """Mix background music under the video's existing audio track.

    bgm_path is looped to fill the full video duration. bgm_db_gain is
    applied to the BGM stream before mixing — default -18 dB keeps it
    clearly below vocals. The existing video audio track stays at 0 dB.

    Raises RuntimeError on FFmpeg failure or missing output.
    """
    source_video = Path(video_path)
    bgm_audio = Path(bgm_path)
    bgm_output = Path(output_path)

    if not source_video.exists():
        raise RuntimeError("Video not found for BGM mix")
    if not bgm_audio.exists():
        raise RuntimeError(f"BGM file not found: {bgm_path}")

    _vdur = _probe_duration_s(str(source_video))
    _dur_args = ["-t", str(_vdur)] if _vdur > 0 else []

    gain = max(-60.0, min(0.0, float(bgm_db_gain)))
    # Loop BGM to fill video; mix at bgm_db_gain under existing audio
    filter_graph = (
        f"[1:a]aloop=loop=-1:size=2147483647,volume={gain:.1f}dB[bgm];"
        "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )
    cmd = [
        get_ffmpeg_bin(), "-y",
        "-i", str(source_video),
        "-i", str(bgm_audio),
        "-filter_complex", filter_graph,
        "-map", "0:v:0",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac",
        *_dur_args,
        str(bgm_output),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"BGM mix failed: {detail or exc}") from exc

    if not bgm_output.exists() or bgm_output.stat().st_size <= 0:
        raise RuntimeError("BGM mix failed: output file was not created")
    return str(bgm_output)
