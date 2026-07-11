import logging
import os
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("app.render.audio.mixer")

# Wall-clock ceilings so a stalled ffprobe/ffmpeg can't hang the render worker
# (these audio helpers run inside the per-part render path, bypassing the
# bounded _run_ffmpeg_with_retry encoder wrapper). Audio-only work is fast, so
# these are generous. Override via FFMPEG_TIMEOUT_SECONDS.
_PROBE_TIMEOUT_SEC: int = 30
_AUDIO_FFMPEG_TIMEOUT_SEC: int = max(60, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600")))

# Loudness normalisation (EBU R128) applied to the narration track before it is
# mixed in. Without it, per-clip TTS loudness drifts (engine/voice/segment
# dependent) so narration sounds inconsistent — louder on some clips, near-mute
# on others. Single-pass loudnorm at the social/speech target (-16 LUFS, -1.5
# dBTP) lands every clip's voice at the same perceived level. Disable via
# NARRATION_LOUDNORM=0; tune via NARRATION_LOUDNORM_PARAMS (raw ffmpeg filter).
_NARRATION_LOUDNORM_ENABLED: bool = os.getenv("NARRATION_LOUDNORM", "1") == "1"
_NARRATION_LOUDNORM: str = os.getenv(
    "NARRATION_LOUDNORM_PARAMS", "loudnorm=I=-16:TP=-1.5:LRA=11"
)


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
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True, timeout=_PROBE_TIMEOUT_SEC)
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
    # Loudness-normalise the narration chain for consistent per-clip voice level.
    _ln = f",{_NARRATION_LOUDNORM}" if _NARRATION_LOUDNORM_ENABLED else ""

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
                "-filter_complex", f"[1:a]atempo={speed:.4f},apad{_ln}[narr]",
                "-map", "0:v:0",
                "-map", "[narr]",
                "-c:v", "copy",
                "-c:a", "aac",
                *_dur_args,
                str(mixed_output),
            ]
        else:
            cmd += [
                "-filter_complex", f"[1:a]apad{_ln}[narr]",
                "-map", "0:v:0",
                "-map", "[narr]",
                "-c:v", "copy",
                "-c:a", "aac",
                *_dur_args,
                str(mixed_output),
            ]
    elif str(mix_mode or "").strip() == "keep_original_low":
        if _has_audio_stream(str(source_video)):
            # Dynamic ducking — original audio stays at full volume and is
            # ducked ONLY while the narration is actually speaking, then
            # recovers when it falls silent. The narration stream is asplit
            # into a playback copy ([narr]) and a key ([key]) that drives
            # sidechaincompress on the original; the ducked original is
            # then amixed with the narration.
            #
            # 2026-06-27 — softened ducking params for the ai_rewrite flow:
            # the original aggressive setting (threshold=0.03 ratio=12) cut
            # the original to ~5-15% during speech, which sounded muted.
            # The new params (threshold=0.06 ratio=2.5) keep the original
            # at ~30-40% during narration so background atmosphere stays
            # audible, then recover to 100% during pauses.
            # Override per-deployment via NARRATION_DUCK_PARAMS env var
            # (raw ffmpeg sidechaincompress argument string).
            #
            # 2026-06-29 — amix normalize=0: default amix divides the output by
            # the input count (2) → the original sat at ~50% even when the
            # narration was silent. For reaction/interleave mode the original
            # MUST return to full volume in the gaps between reactor lines, so
            # normalize=0 keeps each input at unity gain (the sidechain still
            # ducks the original only while the reactor actually speaks).
            _DUCK = os.getenv(
                "NARRATION_DUCK_PARAMS",
                "sidechaincompress=threshold=0.06:ratio=2.5:attack=25:release=500",
            )
            if apply_atempo:
                cmd += [
                    "-filter_complex",
                    f"[1:a]atempo={speed:.4f},apad{_ln},volume=1.0,asplit=2[narr][key];[0:a][key]{_DUCK}[duck];[duck][narr]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]",
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
                    f"[1:a]apad{_ln},volume=1.0,asplit=2[narr][key];[0:a][key]{_DUCK}[duck];[duck][narr]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]",
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
                    "-filter_complex", f"[1:a]atempo={speed:.4f},apad{_ln}[narr]",
                    "-map", "0:v:0",
                    "-map", "[narr]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    *_dur_args,
                    str(mixed_output),
                ]
            else:
                cmd += [
                    "-filter_complex", f"[1:a]apad{_ln}[narr]",
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
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True, timeout=_AUDIO_FFMPEG_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Narration audio mix timed out after {_AUDIO_FFMPEG_TIMEOUT_SEC}s") from exc
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
    duck: bool = False,
) -> str:
    """Mix background music under the video's existing audio track.

    bgm_path is looped to fill the full video duration. bgm_db_gain is
    applied to the BGM stream before mixing — default -18 dB keeps it
    clearly below vocals. The existing video audio track stays at 0 dB.

    ``duck`` (CS-F, default False → byte-identical to the legacy behaviour):
    when True the BGM is side-chain compressed against the video's audio
    (the narration), so the music drops while the voice speaks and returns
    in the gaps. Off keeps the plain constant-gain mix.

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
    if duck:
        # Duck the BGM under the narration: sidechaincompress lowers [bg] while
        # the video's audio ([0:a]) is loud, then amix at unity gain (normalize=0
        # so the music returns to its set level in the gaps).
        filter_graph = (
            f"[1:a]aloop=loop=-1:size=2147483647,volume={gain:.1f}dB[bg];"
            "[bg][0:a]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[bgduck];"
            "[0:a][bgduck]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[out]"
        )
    else:
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
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True, timeout=_AUDIO_FFMPEG_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"BGM mix timed out after {_AUDIO_FFMPEG_TIMEOUT_SEC}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"BGM mix failed: {detail or exc}") from exc

    if not bgm_output.exists() or bgm_output.stat().st_size <= 0:
        raise RuntimeError("BGM mix failed: output file was not created")
    return str(bgm_output)


_BGM_SAMPLE_RATE = 48000


def _render_bgm_segment(ffmpeg_bin, src_path, dur, out_wav, fade_sec):
    """Render ONE scene's BGM to a pcm_s16le/48k/stereo wav of length ``dur``.

    ``src_path`` None → silence. Otherwise the music file is stream-looped to fill
    ``dur`` with a short afade in/out so scenes don't click at the seams. Returns
    True on success. Never raises (best-effort — a bad segment degrades to silence)."""
    try:
        dur = max(0.1, float(dur))
        if src_path:
            fin = min(fade_sec, dur / 2.0)
            fout_st = max(0.0, dur - fin)
            af = (f"afade=t=in:st=0:d={fin:.3f},afade=t=out:st={fout_st:.3f}:d={fin:.3f},"
                  f"aformat=sample_rates={_BGM_SAMPLE_RATE}:channel_layouts=stereo")
            cmd = [ffmpeg_bin, "-y", "-stream_loop", "-1", "-i", str(src_path),
                   "-t", f"{dur:.3f}", "-af", af,
                   "-c:a", "pcm_s16le", "-ar", str(_BGM_SAMPLE_RATE), "-ac", "2", str(out_wav)]
        else:
            cmd = [ffmpeg_bin, "-y", "-f", "lavfi", "-t", f"{dur:.3f}",
                   "-i", f"anullsrc=r={_BGM_SAMPLE_RATE}:cl=stereo",
                   "-c:a", "pcm_s16le", "-ar", str(_BGM_SAMPLE_RATE), "-ac", "2", str(out_wav)]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", check=True, timeout=_AUDIO_FFMPEG_TIMEOUT_SEC)
        return Path(out_wav).exists() and Path(out_wav).stat().st_size > 0
    except Exception as exc:
        logger.warning("bgm: segment render failed (%s)", exc)
        return False


def build_scene_bgm_track(segments, total_sec, output_path, *, pick_fn=None, fade_sec=0.8):
    """Dựng 1 track nhạc nền khớp timeline video từ các 'cảnh'
    ``segments = [(mood, start_sec, end_sec), ...]`` (thứ tự thời gian).

    Mỗi cảnh: ``pick_fn(mood)`` chọn 1 file nhạc theo mood → loop/trim khớp độ dài
    cảnh + afade in/out; cảnh không có file → im lặng độ dài đó. Nối tất cả → 1 file
    wav (pcm_s16le/48k/stereo) tại ``output_path``. Trả về ``output_path`` khi có ÍT
    NHẤT 1 cảnh có nhạc thật; ``None`` khi không mood nào có file (caller bỏ qua mix)
    hoặc khi dựng thất bại. Best-effort — never raises.

    Track khớp timeline → ``mix_with_bgm(duck=True)`` chỉ cần duck dưới lời kể, không
    cần biết ranh giới cảnh."""
    try:
        segs = [s for s in (segments or []) if s and float(s[2]) > float(s[1])]
        if not segs:
            return None
        if pick_fn is None:
            from app.core.config import _pick_bgm_file as pick_fn  # lazy — avoid import cycle

        # Resolve music per scene FIRST — if no mood has a file, bail before any ffmpeg.
        resolved: list[tuple] = []   # (src|None, dur)
        any_music = False
        for mood, start, end in segs:
            src = None
            try:
                src = pick_fn(mood or "")
            except Exception:
                src = None
            if src and Path(src).exists() and Path(src).stat().st_size > 0:
                any_music = True
            else:
                src = None
            resolved.append((src, float(end) - float(start)))
        if not any_music:
            return None

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = out.parent / f".{out.stem}_segs"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = get_ffmpeg_bin()

        seg_files: list[Path] = []
        for i, (src, dur) in enumerate(resolved):
            seg_wav = tmp_dir / f"seg_{i:04d}.wav"
            if _render_bgm_segment(ffmpeg_bin, src, dur, seg_wav, fade_sec):
                seg_files.append(seg_wav)

        if not seg_files:
            _cleanup_dir(tmp_dir)
            return None

        # Concat các đoạn cùng format (pcm_s16le) → copy, không re-encode.
        list_file = tmp_dir / "concat.txt"
        list_file.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in seg_files), encoding="utf-8")
        cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
               "-c", "copy", str(out)]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", check=True, timeout=_AUDIO_FFMPEG_TIMEOUT_SEC)
        _cleanup_dir(tmp_dir)
        if out.exists() and out.stat().st_size > 0:
            return str(out)
        return None
    except Exception as exc:
        logger.warning("bgm: build_scene_bgm_track failed (%s)", exc)
        return None


def build_placed_bgm_track(placements, total_sec, output_path, *, pick_fn=None, fade_sec=0.6):
    """Dựng 1 track nhạc nền dài ``total_sec`` với nhạc đặt tại ĐÚNG vị trí (s4 placed-BGM).

    ``placements = [(mood, start_sec, end_sec, gain_db), ...]`` — mỗi đoạn: ``pick_fn(mood)``
    chọn file → loop/trim khớp độ dài + afade in/out + volume(gain) → đặt tại ``start_sec``
    (adelay) trên nền im lặng ``total_sec``; các đoạn amix (normalize=0). Khoảng trống giữa
    các đoạn = im lặng → nhạc chỉ kêu ở đầu/giữa/cuối cảnh theo AI, KHÔNG liên tục.

    Trả ``output_path`` khi có ÍT NHẤT 1 đoạn có nhạc thật; ``None`` khi không mood nào có
    file hoặc dựng lỗi. Best-effort — never raises. Ghép với ``mix_with_bgm(duck=True)``."""
    try:
        segs = [p for p in (placements or []) if p and float(p[2]) > float(p[1])]
        if not segs:
            return None
        total = max(0.1, float(total_sec or 0))
        if pick_fn is None:
            from app.core.config import _pick_bgm_file as pick_fn  # lazy — avoid import cycle

        resolved: list[tuple] = []   # (src, start, dur, gain)
        for mood, s, e, gain in segs:
            src = None
            try:
                src = pick_fn(mood or "")
            except Exception:
                src = None
            if src and Path(src).exists() and Path(src).stat().st_size > 0:
                resolved.append((str(src), float(s), float(e) - float(s), float(gain)))
        if not resolved:
            return None

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = get_ffmpeg_bin()
        # Base silence [0] + each music file stream-looped as inputs [1..N].
        cmd = [ffmpeg_bin, "-y", "-f", "lavfi", "-t", f"{total:.3f}",
               "-i", f"anullsrc=r={_BGM_SAMPLE_RATE}:cl=stereo"]
        parts: list[str] = []
        for i, (src, start, dur, gain) in enumerate(resolved, start=1):
            cmd += ["-stream_loop", "-1", "-i", src]
            fin = min(fade_sec, dur / 2.0)
            fout_st = max(0.0, dur - fin)
            delay = max(0, int(round(start * 1000)))
            parts.append(
                f"[{i}:a]atrim=0:{dur:.3f},afade=t=in:st=0:d={fin:.3f},"
                f"afade=t=out:st={fout_st:.3f}:d={fin:.3f},volume={gain:.1f}dB,"
                f"aformat=sample_rates={_BGM_SAMPLE_RATE}:channel_layouts=stereo,"
                f"adelay={delay}|{delay}[m{i}]")
        mix_inputs = "[0:a]" + "".join(f"[m{i}]" for i in range(1, len(resolved) + 1))
        fc = ";".join(parts) + ";" + mix_inputs + \
            f"amix=inputs={len(resolved) + 1}:duration=first:normalize=0[out]"
        cmd += ["-filter_complex", fc, "-map", "[out]", "-t", f"{total:.3f}",
                "-c:a", "pcm_s16le", "-ar", str(_BGM_SAMPLE_RATE), "-ac", "2", str(out)]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", check=True, timeout=_AUDIO_FFMPEG_TIMEOUT_SEC)
        if out.exists() and out.stat().st_size > 0:
            return str(out)
        return None
    except Exception as exc:
        logger.warning("bgm: build_placed_bgm_track failed (%s)", exc)
        return None


def _cleanup_dir(d: Path) -> None:
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
