"""
ab_clip_story_intel.py — measure 0C (Story Intelligence on the clip path).

A/B on one source transcript:
  Arm A: select_render_plan WITHOUT a StoryModel (baseline).
  Arm B: select_render_plan WITH a StoryModel (whole-source understanding
         injected so the selector grounds picks in theme/conflict/beats).
Both judged on the clip rubric; reports the per-criterion + weighted delta.

Usage (from backend/):
    python -m ai_eval.ab_clip_story_intel --srt <film.srt> [--judge gemini]
"""
from __future__ import annotations

import argparse
import re
import sys

import app.core.config  # noqa: F401 — load .env keys
from app.features.render.ai.llm import select_render_plan, select_story_model
from app.features.render.ai.llm.recap_prompts import _fit_transcript
from ai_eval.llm_client import resolve_api_key
from ai_eval.judge import score_case
from ai_eval.rubrics import get_rubric

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _last_ts(srt: str) -> float:
    last = 0.0
    for m in _TS.finditer(srt):
        h, mi, s, ms = (int(x) for x in m.groups()[4:])
        last = max(last, h * 3600 + mi * 60 + s + ms / 1000)
    return last


def _clip_case(plan, cid, excerpt):
    return {
        "id": cid, "feature": "clip",
        "inputs": {"transcript_excerpt_downsampled": excerpt},
        "output": {"clips": [
            {"start": round(c.start, 1), "end": round(c.end, 1),
             "title": c.title, "reason": c.reason} for c in plan.clips
        ]},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A/B measure 0C clip Story Intelligence")
    ap.add_argument("--srt", required=True)
    ap.add_argument("--provider", default="gemini")
    ap.add_argument("--judge", default="gemini")
    ap.add_argument("--output-count", type=int, default=6)
    args = ap.parse_args(argv)

    srt = open(args.srt, encoding="utf-8").read()
    dur = _last_ts(srt)
    api_key = resolve_api_key(args.provider)
    if not api_key:
        print("[0c] no API key"); return 3
    print(f"[0c] chars={len(srt)} dur={dur:.0f}s (~{dur/60:.0f} min)")

    print("[0c] building StoryModel ...")
    story = None
    for _ in range(3):
        story = select_story_model(provider=args.provider, srt_content=srt,
                                   video_duration=dur, target_language="vi-VN", api_key=api_key)
        if story is not None and story.beats:
            break
    if story is None or story.is_empty():
        print("[0c] StoryModel unusable — cannot run A/B"); return 3
    print(f"[0c] StoryModel: characters={len(story.characters)} beats={len(story.beats)}")

    common = dict(provider=args.provider, srt_content=srt, output_count=args.output_count,
                  min_sec=20, max_sec=60, video_duration=dur, api_key=api_key, language="auto")
    print("[0c] arm A (NO story) ...")
    plan_a = select_render_plan(**common, story_model=None)
    print("[0c] arm B (WITH story) ...")
    plan_b = select_render_plan(**common, story_model=story)
    if plan_a is None or plan_b is None or not plan_a.clips or not plan_b.clips:
        print(f"[0c] an arm empty (A={plan_a and len(plan_a.clips)}, B={plan_b and len(plan_b.clips)})")
        return 3

    excerpt = _fit_transcript(srt, 12000)
    res_a = score_case(_clip_case(plan_a, "clip_NOstory", excerpt), provider=args.judge)
    res_b = score_case(_clip_case(plan_b, "clip_WITHstory", excerpt), provider=args.judge)
    if not (res_a.ok and res_b.ok):
        print(f"[0c] judge err A={res_a.error} B={res_b.error}"); return 3

    rub = get_rubric("clip")
    print(f"\n=== 0C CLIP STORY INTELLIGENCE — A/B (n=1) ===")
    print(f"{'criterion':<22}{'NO':>6}{'YES':>6}{'Δ':>7}")
    for c in rub.criteria:
        a, b = res_a.scores.get(c.key, 0), res_b.scores.get(c.key, 0)
        print(f"{c.key:<22}{a:>6g}{b:>6g}{b-a:>+7g}")
    print(f"{'WEIGHTED MEAN':<22}{res_a.weighted:>6g}{res_b.weighted:>6g}{res_b.weighted-res_a.weighted:>+7g}")
    print(f"\nNO-story rationale : {res_a.rationale}")
    print(f"WITH-story rationale: {res_b.rationale}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
