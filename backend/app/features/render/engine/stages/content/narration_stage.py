"""
narration_stage.py — W5-6 two-phase narration for the word-by-word subtitle path.

Instead of transcribing each scene's narration clip separately (N Whisper calls,
each paying Whisper's fixed per-call overhead — measured ~2.2x the cost of one
call), this synthesizes ALL scene narrations, concatenates them in scene order,
transcribes the whole thing ONCE with word timestamps, and splits the word
timings back per scene by cumulative time offset.

Only runs for the word-by-word path (the sentence-SRT path never transcribes).
Fully best-effort: on ANY failure it returns whatever it has (possibly empty),
and the render loop falls back to the original per-scene synth + transcribe — so
this is a pure optimization with the old path as a safety net. Never raises.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.stages.content_scene_render import (
    synthesize_scene_narration,
    _srt_to_sec,
    _srt_time,
    _SRT_TIME_LINE_RE,
    _CONTENT_WHISPER_MODEL,
)

logger = logging.getLogger("app.render.content")


def _split_srt_window(srt_text: str, start: float, end: float) -> str:
    """Return an SRT (re-based to 0) of the cues whose START time falls in
    [start, end). Used to slice the whole-video word SRT back to one scene."""
    blocks = [b for b in srt_text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    out: list[str] = []
    n = 0
    for b in blocks:
        lines = b.split("\n")
        ti = next((k for k, ln in enumerate(lines) if _SRT_TIME_LINE_RE.match(ln.strip())), None)
        if ti is None:
            continue
        m = _SRT_TIME_LINE_RE.match(lines[ti].strip())
        a = _srt_to_sec(m.group(1))
        z = _srt_to_sec(m.group(2))
        if not (start <= a < end):
            continue
        na = max(0.0, a - start)
        nz = max(na, z - start)
        n += 1
        out.append(str(n))
        out.append(f"{_srt_time(na)} --> {_srt_time(nz)}")
        out.extend(lines[ti + 1:])
        out.append("")
    return "\n".join(out)


def prepare_narration_word_timings(ctx, scenes):
    """Synthesize all (not-yet-rendered) scene narrations, transcribe the
    concatenation ONCE, and split word timings per scene.

    Returns ``(audio_map, word_srt_map)`` where ``audio_map[i] = (audio_path,
    dur)`` and ``word_srt_map[i] = <0-based word SRT path>`` (1-based scene index).
    A scene missing from a map falls back to the per-scene path in the render
    loop. Never raises."""
    audio_map: dict[int, tuple[str, float]] = {}
    srt_map: dict[int, str] = {}
    try:
        from app.features.render.engine.subtitle.transcription.whisper import transcribe_to_srt

        scenes_dir = ctx.scenes_dir
        order: list[tuple[int, str, float]] = []  # (scene index, audio path, dur), in render order
        for i, scene in enumerate(scenes, start=1):
            scene_out = scenes_dir / f"scene_{i:03d}.mp4"
            # Resume (disk-truth): a scene already rendered keeps its burned subs —
            # don't re-synth/transcribe it.
            if scene_out.exists() and scene_out.stat().st_size > 0 \
                    and _validate_render_output(scene_out, expect_audio=True).get("ok"):
                continue
            narr = synthesize_scene_narration(
                scene=scene, job_id=ctx.job_id, language=ctx.language, gender=ctx.gender,
                voice_id=ctx.voice_id, tts_engine=ctx.tts_engine,
                out_path=str(scenes_dir / f"narr_{i:03d}.mp3"),
            )
            if narr is None:
                continue  # TTS failed — the render loop will mark this scene FAILED
            audio_map[i] = narr
            order.append((i, narr[0], narr[1]))

        if not order:
            return audio_map, srt_map

        # Concatenate the narrations in render order (relative paths → the concat
        # demuxer resolves them against the list file's own directory).
        lst = scenes_dir / "narr_all.txt"
        lst.write_text("".join(f"file '{Path(a).name}'\n" for _, a, _ in order), encoding="utf-8")
        concat = str(scenes_dir / "narr_all.mp3")
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", concat],
            capture_output=True, timeout=600,
        )
        if not (Path(concat).exists() and Path(concat).stat().st_size > 0):
            logger.info("content: narration concat failed — per-scene transcription fallback")
            return audio_map, srt_map

        # ONE transcription for the whole video.
        gsrt = scenes_dir / "narr_all.srt"
        transcribe_to_srt(concat, str(gsrt), model_name=_CONTENT_WHISPER_MODEL, highlight_per_word=True)
        gtext = gsrt.read_text(encoding="utf-8") if gsrt.exists() else ""
        if not gtext.strip():
            logger.info("content: whole-video transcription empty — per-scene fallback")
            return audio_map, srt_map

        cum = 0.0
        for i, _a, d in order:
            per = _split_srt_window(gtext, cum, cum + d)
            if per.strip():
                ps = scenes_dir / f"word_{i:03d}.srt"
                ps.write_text(per, encoding="utf-8")
                srt_map[i] = str(ps)
            cum += d
        logger.info(
            "content: one-shot narration transcription split into %d scene(s) (of %d synth'd)",
            len(srt_map), len(order),
        )
        return audio_map, srt_map
    except Exception as exc:
        logger.info("content: narration pre-pass failed (%s) — per-scene fallback", exc)
        return audio_map, srt_map
