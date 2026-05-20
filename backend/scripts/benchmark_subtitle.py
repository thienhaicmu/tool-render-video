"""
Subtitle transcription benchmark — OQ-1.1A methodology.

Usage:
    python -m scripts.benchmark_subtitle <video_file> [--model large-v3] [--word]

Measures wall-clock transcription latency for every available adapter and
prints a comparison table.  Run from the backend/ directory with the virtualenv
active.

Methodology notes
-----------------
- Each adapter runs against the same source video in sequence (no overlap).
- WAV extraction time is included in the elapsed_ms figure (matches production).
- Model load time for the first run is included; cached runs are NOT re-loaded
  (mirrors production _FW_MODEL_CACHE behaviour).
- VRAM is not measured here; use nvidia-smi dmon for live VRAM monitoring.
- For accurate CPU benchmarks disable Turbo Boost or run 3 trials and take median.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running as `python -m scripts.benchmark_subtitle` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _fmt_ms(ms: int) -> str:
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}min"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    return f"{ms}ms"


def _count_words(srt_path: str) -> int:
    try:
        text = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().isdigit() and "-->" not in l]
        return sum(len(l.split()) for l in lines)
    except Exception:
        return 0


def _detect_device() -> str:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def run_benchmark(video_path: str, model_name: str, word_level: bool) -> None:
    from app.ai.dependencies import has_faster_whisper, has_whisperx
    from app.services.subtitle_transcription_adapters import (
        DefaultWhisperAdapter,
        FasterWhisperAdapter,
        WhisperXAdapter,
    )

    device = _detect_device()
    video = Path(video_path)
    if not video.exists():
        print(f"ERROR: video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = Path(os.environ.get("TEMP", "/tmp")) / "subtitle_bench"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    adapters = [
        ("default (openai-whisper)", DefaultWhisperAdapter(), True),
        ("faster_whisper", FasterWhisperAdapter(), has_faster_whisper()),
        ("whisperx", WhisperXAdapter(), has_whisperx()),
    ]

    print(f"\nSubtitle Transcription Benchmark")
    print(f"  video   : {video.name} ({video.stat().st_size // 1024}KB)")
    print(f"  model   : {model_name}")
    print(f"  device  : {device}")
    print(f"  word    : {word_level}")
    print()
    print(f"{'Adapter':<30}  {'Status':<10}  {'Elapsed':<10}  {'Words':<8}  {'Aligned'}")
    print("-" * 75)

    for label, adapter, available in adapters:
        if not available:
            print(f"{label:<30}  {'SKIP':<10}  {'—':<10}  {'—':<8}  —")
            continue

        srt_path = str(tmp_dir / f"bench_{label.replace(' ', '_')}.srt")
        t0 = time.perf_counter()
        try:
            result = adapter.transcribe(
                video_path,
                srt_path,
                model_name=model_name,
                retry_count=1,
                highlight_per_word=word_level,
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            words = _count_words(srt_path)
            status = "WARN" if result.warnings else "OK"
            warn_str = f"  [{result.warnings[0][:60]}]" if result.warnings else ""
            print(
                f"{label:<30}  {status:<10}  {_fmt_ms(elapsed_ms):<10}  {words:<8}  {result.aligned}"
                f"{warn_str}"
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            print(f"{label:<30}  {'ERROR':<10}  {_fmt_ms(elapsed_ms):<10}  {'—':<8}  —  [{exc}]")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark subtitle transcription adapters")
    parser.add_argument("video", help="Path to source video file")
    parser.add_argument("--model", default="large-v3", help="Whisper model name (default: large-v3)")
    parser.add_argument("--word", action="store_true", help="Enable word-level timestamps")
    args = parser.parse_args()
    run_benchmark(args.video, args.model, args.word)


if __name__ == "__main__":
    main()
