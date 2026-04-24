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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def mix_narration_audio(
    *,
    video_path: str,
    narration_audio_path: str,
    mix_mode: str,
    output_path: str,
) -> str:
    source_video = Path(video_path)
    narration_audio = Path(narration_audio_path)
    mixed_output = Path(output_path)

    if not source_video.exists():
        raise RuntimeError("Rendered video not found for narration mix")
    if not narration_audio.exists():
        raise RuntimeError("Narration audio file not found")

    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [ffmpeg_bin, "-y", "-i", str(source_video), "-i", str(narration_audio)]

    if str(mix_mode or "").strip() == "replace_original":
        cmd += [
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(mixed_output),
        ]
    elif str(mix_mode or "").strip() == "keep_original_low":
        if _has_audio_stream(str(source_video)):
            cmd += [
                "-filter_complex",
                "[0:a]volume=0.25[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(mixed_output),
            ]
        else:
            cmd += [
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(mixed_output),
            ]
    else:
        raise RuntimeError("Unsupported narration audio mix mode")

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Narration audio mix failed: {detail or exc}") from exc

    if not mixed_output.exists() or mixed_output.stat().st_size <= 0:
        raise RuntimeError("Narration audio mix failed: output file was not created")
    return str(mixed_output)
