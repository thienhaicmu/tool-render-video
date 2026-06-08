"""SRT core parsing, writing, slicing, and subprocess retry helper.

This module owns:
- format_srt_timestamp / parse_srt_timestamp — timestamp format/parse
- _parse_srt_blocks / parse_srt_blocks — SRT file parsing
- write_srt_blocks — SRT file writing
- slice_srt_by_time — time-range slicing with optional speed scaling
- slice_srt_to_text — plain-text extraction for a time range
- _run_with_retry — generic subprocess retry (shared with ass_core)

No style presets. No ASS conversion. No Whisper. No TimelineMap.
"""
import subprocess
import time
from pathlib import Path


def format_srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt_timestamp(ts: str) -> float:
    # Format: HH:MM:SS,mmm
    p = ts.strip().replace(".", ",").split(":")
    if len(p) != 3:
        return 0.0
    h = int(p[0])
    m = int(p[1])
    s_ms = p[2].split(",")
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return (h * 3600) + (m * 60) + s + (ms / 1000.0)


def _parse_srt_blocks(srt_path: str):
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = []
    for block in content.split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue
        start_s, end_s = time_line.split(" --> ", 1)
        start = parse_srt_timestamp(start_s)
        end = parse_srt_timestamp(end_s)
        text = " ".join(lines[2:]).strip()
        if text and end > start:
            blocks.append({"start": start, "end": end, "text": text})
    return blocks


def parse_srt_blocks(srt_path: str) -> list[dict]:
    """Parse SRT file into a list of {start, end, text} dicts for round-trip editing.

    Unlike the internal _parse_srt_blocks, multi-line text within a block is joined
    with \\n so that write_srt_blocks() faithfully preserves line breaks.
    """
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks: list[dict] = []
    for block in content.split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue
        start_s, end_s = time_line.split(" --> ", 1)
        start = parse_srt_timestamp(start_s)
        end = parse_srt_timestamp(end_s)
        text = "\n".join(lines[2:]).strip()
        if text and end > start:
            blocks.append({"start": start, "end": end, "text": text})
    return blocks


def write_srt_blocks(blocks: list[dict], srt_path: str) -> None:
    """Write parsed SRT blocks back to a file in standard SRT format.

    Preserves timing, block order, and multi-line text (\\n within text is kept).
    """
    with Path(srt_path).open("w", encoding="utf-8") as f:
        for idx, b in enumerate(blocks, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(b['start'])} --> {format_srt_timestamp(b['end'])}\n"
                f"{b['text']}\n\n"
            )


def slice_srt_by_time(
    source_srt_path: str,
    output_srt_path: str,
    start_sec: float,
    end_sec: float,
    rebase_to_zero: bool = True,
    playback_speed: float = 1.0,
    apply_playback_speed: bool = True,
) -> dict:
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    try:
        speed = max(0.5, min(1.5, float(playback_speed or 1.0)))
    except Exception:
        speed = 1.0
    time_scale = speed if apply_playback_speed else 1.0
    selected = []

    for b in src_blocks:
        ov_start = max(start_sec, b["start"])
        ov_end = min(end_sec, b["end"])
        if ov_end <= ov_start:
            continue
        if rebase_to_zero:
            out_start = (ov_start - start_sec) / time_scale
            out_end = (ov_end - start_sec) / time_scale
        else:
            out_start = ov_start / time_scale
            out_end = ov_end / time_scale
        if out_end <= out_start:
            continue
        selected.append({"start": out_start, "end": out_end, "text": b["text"]})

    with Path(output_srt_path).open("w", encoding="utf-8") as f:
        for idx, seg in enumerate(selected, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
                f"{seg['text']}\n\n"
            )
    return {
        "subtitle_count": len(selected),
        "first_start": selected[0]["start"] if selected else None,
        "first_end": selected[0]["end"] if selected else None,
        "last_start": selected[-1]["start"] if selected else None,
        "last_end": selected[-1]["end"] if selected else None,
        "playback_speed": speed,
        "apply_playback_speed": bool(apply_playback_speed),
    }


def slice_srt_to_text(source_srt_path: str, start_sec: float, end_sec: float) -> str:
    """Slice a SRT by time range and return plain text — no temp file written."""
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    texts = [
        b["text"] for b in src_blocks
        if min(end_sec, b["end"]) > max(start_sec, b["start"])
    ]
    return " ".join(texts).strip()


def _run_with_retry(command: list[str], retries: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
        except subprocess.CalledProcessError as exc:
            if attempt > retries:
                stderr_tail = (exc.stderr or "")[-1000:].strip()
                raise RuntimeError(
                    f"FFmpeg failed (exit={exc.returncode})"
                    + (f": {stderr_tail}" if stderr_tail else "")
                ) from exc
            time.sleep(wait_sec * attempt)
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)

