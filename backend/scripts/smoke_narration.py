"""
smoke_narration.py — REAL-VALUE smoke test for the AI narration output.

Unlike pytest (which only checks "does the function error?"), this calls the
ACTUAL AI (rewrite / reaction / recap) on a real/sample transcript and prints
the ACTUAL narration text the engine would speak — so you can JUDGE the value:
is it natural? faithful? right pacing? It optionally synthesizes the TTS to an
mp3 so you can HEAR it. No 24-minute render needed.

Usage (from backend/, venv active; needs a provider key in .env or --key):

  # Reaction on a built-in English sample → Vietnamese, print spoken text:
  python scripts/smoke_narration.py --mode reaction --lang vi-VN --sample

  # Rewrite from your own SRT file, also synth to mp3 to listen:
  python scripts/smoke_narration.py --mode rewrite --lang vi-VN --srt clip.srt --tts out.mp3

  # Recap: feed a film transcript SRT, print AI scene plan + authored narration:
  python scripts/smoke_narration.py --mode recap --lang vi-VN --srt film.srt

Provider/key resolution: --provider (default gemini) + --key, else GEMINI_API_KEY
/ OPENAI_API_KEY / CLAUDE_API_KEY env.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow running from backend/ (python scripts/smoke_narration.py).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_SAMPLE_SRT = """1
00:00:00,000 --> 00:00:05,000
He walks up to the counter, totally calm, like nothing happened.

2
00:00:05,000 --> 00:00:11,000
Then the officer pulls out the file and asks about the car he sold last week.

3
00:00:11,000 --> 00:00:17,000
You can see his face change. He starts stumbling over his own words.

4
00:00:17,000 --> 00:00:24,000
And that's when the whole story he told falls apart, right there on camera.
"""


def _read_srt(path: str | None) -> str:
    if not path:
        return _SAMPLE_SRT
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _srt_to_blocks(srt_text: str) -> list[dict]:
    from app.features.render.engine.subtitle.generator.srt import parse_srt_blocks
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".srt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(srt_text)
        return parse_srt_blocks(p)
    finally:
        try:
            os.unlink(p)
        except Exception:
            pass


def _resolve_key(provider: str, cli_key: str | None) -> str:
    if cli_key:
        return cli_key
    env = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "claude": "CLAUDE_API_KEY"}.get(provider, "")
    return (os.getenv(env) or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-value narration smoke test")
    ap.add_argument("--mode", required=True, choices=["rewrite", "reaction", "recap"])
    ap.add_argument("--lang", default="vi-VN", help="voice/target language (vi-VN, en-US, ja-JP, ko-KR, en-GB)")
    ap.add_argument("--provider", default="gemini", choices=["gemini", "openai", "claude"])
    ap.add_argument("--key", default=None, help="API key (else from env)")
    ap.add_argument("--srt", default=None, help="path to an SRT; omit + --sample for the built-in clip")
    ap.add_argument("--sample", action="store_true", help="use the built-in sample transcript")
    ap.add_argument("--tone", default="", help="tone hint (e.g. 'kịch tính', 'hài hước')")
    ap.add_argument("--intensity", default="", choices=["", "low", "medium", "high"], help="reaction density")
    ap.add_argument("--video-dur", type=float, default=0.0, help="recap: full film duration in seconds")
    ap.add_argument("--tts", default=None, help="also synthesize the narration to this mp3")
    args = ap.parse_args()

    key = _resolve_key(args.provider, args.key)
    if not key:
        print(f"[!] No API key for provider={args.provider}. Pass --key or set the env var.", file=sys.stderr)
        return 2

    srt_text = _read_srt(args.srt if not args.sample else None)
    from app.features.render.engine.audio.timed_narration import _strip_time_artifacts

    if args.mode in ("rewrite", "reaction"):
        from app.features.render.ai.llm.rewrite import rewrite_subtitle
        from app.features.render.ai.llm.rewrite_prompts import format_segments_for_prompt
        blocks = _srt_to_blocks(srt_text)
        if not blocks:
            print("[!] No SRT blocks parsed.", file=sys.stderr)
            return 2
        clip_dur = max(1.0, float(blocks[-1]["end"]))
        srt_segmented = format_segments_for_prompt(blocks)
        print(f"=== MODE={args.mode} provider={args.provider} lang={args.lang} clip_dur={clip_dur:.1f}s ===\n")
        segments = rewrite_subtitle(
            provider=args.provider, srt_segmented=srt_segmented, clip_duration_sec=clip_dur,
            target_language=args.lang, tone=args.tone, api_key=key,
            narration_mode=("reaction" if args.mode == "reaction" else ""),
            reaction_intensity=args.intensity,
        )
        if not segments:
            print("[!] AI returned None (key invalid / rate-limit / parse). See logs.", file=sys.stderr)
            return 1
        print("--- AI NARRATION OUTPUT (what the engine will SPEAK) ---")
        for i, s in enumerate(segments, 1):
            kind = s.get("kind", "voice")
            spoken = _strip_time_artifacts(s.get("text", ""))
            fa = s.get("freeze_after", 0)
            tag = f"[{kind}]" + (f" freeze={fa}s" if fa else "")
            if kind == "original":
                print(f"  {i:2d} {tag} ({s['start']:.1f}-{s['end']:.1f}s)  ▶ original audio plays (reactor silent)")
            else:
                print(f"  {i:2d} {tag} ({s['start']:.1f}-{s['end']:.1f}s)  🗣 {spoken!r}")
        _maybe_tts(args, segments, clip_dur)
        return 0

    # recap
    from app.features.render.ai.llm import select_recap_plan
    blocks = _srt_to_blocks(srt_text)
    video_dur = args.video_dur or (max((b["end"] for b in blocks), default=0.0))
    print(f"=== MODE=recap provider={args.provider} lang={args.lang} film_dur={video_dur:.0f}s ===\n")
    plan = select_recap_plan(
        provider=args.provider, srt_content=srt_text, video_duration=video_dur,
        target_language=args.lang, tone=args.tone, api_key=key,
    )
    if plan is None:
        print("[!] AI returned None. See logs.", file=sys.stderr)
        return 1
    print(f"--- RECAP PLAN: {len(plan.acts)} acts, {plan.scene_count()} scenes, target={plan.total_target_sec:.0f}s ---")
    for ai, act in enumerate(plan.acts, 1):
        print(f"\nACT {ai}: {act.title or '-'} [{act.beat or '-'}]")
        for s in act.scenes:
            spoken = _strip_time_artifacts(s.narration or s.narration_intent)
            climax = " ⭐" if s.is_climax else ""
            print(f"  ({s.start:.0f}-{s.end:.0f}s){climax}  🗣 {spoken!r}")
    return 0


def _maybe_tts(args, segments, clip_dur):
    if not args.tts:
        return
    print(f"\n[+] Synthesizing TTS → {args.tts} …")
    from app.features.render.engine.audio.timed_narration import synthesize_timed_narration
    import shutil
    out = synthesize_timed_narration(
        segments=segments, clip_duration_sec=clip_dur, voice_language=args.lang,
        voice_gender="female", voice_rate="+0%", voice_id=None, content_type="vlog",
        tts_engine="edge", job_id="smoke", part_idx=1,
    )
    if out and os.path.exists(out):
        try:
            shutil.copyfile(out, args.tts)
            print(f"[+] Saved: {args.tts}")
        except Exception as exc:
            print(f"[!] copy failed: {exc} (raw at {out})")
    else:
        print("[!] TTS failed (edge-tts installed? network?).")


if __name__ == "__main__":
    raise SystemExit(main())
