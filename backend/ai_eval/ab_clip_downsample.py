"""
ab_clip_downsample.py — measure 0D (long-transcript downsampling) impact.

Faithful A/B of the exact code change, on ONE long source transcript:
  Arm A (OLD): monkeypatch prompts._fit_seconds_transcript back to a head-slice
               → the selector sees only the first ~cap chars (front of the film).
  Arm B (NEW): the real runtime-spanning downsample → the selector sees start→end.

The metric is deterministic COVERAGE (no LLM judge needed): where do the
selected clips land? The 0D fix should make clips appear in the BACK HALF of a
long source, which the head-slice made invisible.

Usage (from backend/):
    python -m ai_eval.ab_clip_downsample --srt <long_film.srt>
"""
from __future__ import annotations

import argparse
import re
import sys

import app.core.config  # noqa: F401 — load .env keys first
import app.features.render.ai.llm.prompts as prompts
from app.features.render.ai.llm import select_render_plan
from ai_eval.llm_client import resolve_api_key

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _last_ts(srt: str) -> float:
    last = 0.0
    for m in _TS.finditer(srt):
        h, mi, s, ms = (int(x) for x in m.groups()[4:])
        last = max(last, h * 3600 + mi * 60 + s + ms / 1000)
    return last


def _head_slice(text: str, cap: int) -> str:
    """The pre-0D behaviour: keep the first ``cap`` chars only."""
    out = text[:cap]
    if len(text) > cap:
        out += "\n... [transcript truncated]"
    return out


def _coverage(plan, dur: float) -> dict:
    if plan is None or not plan.clips:
        return {"clips": 0}
    starts = sorted(float(c.start) for c in plan.clips)
    back = sum(1 for s in starts if s > dur * 0.5)
    return {
        "clips": len(starts),
        "earliest_start": round(starts[0], 0),
        "latest_start": round(starts[-1], 0),
        "span_pct": round((starts[-1] - starts[0]) / dur * 100, 1) if dur else 0.0,
        "back_half_clips": back,
        "starts": [round(s) for s in starts],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A/B measure 0D clip downsampling")
    ap.add_argument("--srt", required=True)
    ap.add_argument("--provider", default="gemini")
    ap.add_argument("--output-count", type=int, default=6)
    ap.add_argument("--min-sec", type=float, default=20)
    ap.add_argument("--max-sec", type=float, default=60)
    args = ap.parse_args(argv)

    srt = open(args.srt, encoding="utf-8").read()
    dur = _last_ts(srt)
    api_key = resolve_api_key(args.provider)
    if not api_key:
        print(f"[0d] no API key for {args.provider}")
        return 3
    print(f"[0d] transcript chars={len(srt)} duration={dur:.0f}s (~{dur/60:.0f} min)")

    _real_fit = prompts._fit_seconds_transcript
    common = dict(provider=args.provider, srt_content=srt, output_count=args.output_count,
                  min_sec=args.min_sec, max_sec=args.max_sec, video_duration=dur,
                  api_key=api_key, language="auto")
    try:
        # Arm A — OLD head-slice.
        print("[0d] arm A (OLD head-slice) ...")
        prompts._fit_seconds_transcript = _head_slice
        plan_a = select_render_plan(**common)
        # Arm B — NEW downsample.
        print("[0d] arm B (NEW downsample) ...")
        prompts._fit_seconds_transcript = _real_fit
        plan_b = select_render_plan(**common)
    finally:
        prompts._fit_seconds_transcript = _real_fit

    ca, cb = _coverage(plan_a, dur), _coverage(plan_b, dur)
    if not ca.get("clips") or not cb.get("clips"):
        print(f"[0d] a arm empty (A={ca.get('clips')}, B={cb.get('clips')}) — likely quota/None.")
        return 3

    print(f"\n=== 0D CLIP DOWNSAMPLING — COVERAGE A/B (film {dur/60:.0f} min) ===")
    for name, c in (("OLD head-slice", ca), ("NEW downsample", cb)):
        print(f"{name:<16} clips={c['clips']} "
              f"start_range={c['earliest_start']:.0f}s..{c['latest_start']:.0f}s "
              f"span={c['span_pct']:.0f}% back_half={c['back_half_clips']}/{c['clips']}")
        print(f"                 clip starts (s): {c['starts']}")
    print(f"\nback-half clips: OLD={ca['back_half_clips']}  NEW={cb['back_half_clips']}  "
          f"(Δ={cb['back_half_clips'] - ca['back_half_clips']:+d}) — the 0D fix should surface "
          "clips the head-slice made invisible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
