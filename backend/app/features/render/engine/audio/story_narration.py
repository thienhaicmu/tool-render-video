"""
story_narration.py — synthesize the Story v2 timeline narration (B6).

Fills ``plan.render.beat_audio[beat_id] = BeatAudio(path, dur, words)`` for every
beat, using the cast voice/engine (``plan.render.voices[speaker_id]`` from B4). Each
beat is synthesized to its own clip so the render walks the cue sheet with exact
per-beat durations.

Design note: TTS is priced PER CHARACTER, so a single batched call saves no money
over per-beat calls — and splitting a batched audio precisely by beat is fragile
for Vietnamese/Japanese (the same tokenizer mismatch that made us drop word-level
focus). So this synthesizes per beat (robust + deterministic + engine-agnostic),
grouped by voice-run for observability. ``words`` (timed transcript) is only needed
for full-subtitle karaoke (default is hook-only) and is left empty here; a best-
effort Whisper alignment can fill it later without changing this contract.

Sacred Contract #3 spirit: never raises; a beat whose TTS fails gets an empty audio
(the render treats it as a silent hold), so one bad beat never aborts the render.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.domain.story_plan_v2 import BeatAudio
from app.features.render.engine.audio.tts import generate_narration_audio
from app.features.render.engine.stages.content_scene_render import (
    _reading_speed_to_rate, probe_audio_duration,
)

logger = logging.getLogger("app.render.story_narration")

_LOCALE = {"vi": "vi-VN", "en": "en-US", "ja": "ja-JP", "ko": "ko-KR"}


def _voice_for(plan, speaker_id: str) -> "tuple[str, str]":
    entry = plan.render.voices.get(speaker_id or "")
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        return (entry[0] or "edge"), (entry[1] or "")
    return "edge", ""


def _gender_for(plan, speaker_id: str) -> str:
    c = plan.character(speaker_id) if speaker_id else None
    g = (getattr(c, "voice_gender", "") or getattr(c, "gender", "")) if c is not None else ""
    return g or "female"


def synthesize_timeline(plan, *, job_id: str, audio_dir, subtitle_mode: str = "hook_only",
                        effective_channel: str = "", on_progress=None) -> None:
    """Synthesize every beat's narration → ``plan.render.beat_audio``. Never raises.

    ``generate_narration_audio`` already falls back through its own engine chain
    (elevenlabs/gemini → edge → offline piper), so an EMPTY result here means EVERY
    engine failed for that beat — the beat renders silent. When that happens on beats
    that HAD narration text, emit one ``story.tts.silent`` warning so the loss is visible
    in the monitor instead of a silently muted stretch (F-R1').

    P0: the spoken beats are synthesized in a bounded thread POOL (``STORY_TTS_WORKERS``,
    default 4) instead of one-by-one — each beat is independent (own file, own
    ``beat_audio`` key), so this cuts the ~N×latency wall that froze the UI at 0%. Result
    collection + ``on_progress(done, total)`` run on the CALLING thread (no cross-thread DB
    writes). ``on_progress`` lets the pipeline stream per-beat progress so the monitor
    moves during narration. Order-independent (keyed by beat id) — deterministic output."""
    silent_spoken: list[str] = []
    try:
        d = Path(audio_dir)
        d.mkdir(parents=True, exist_ok=True)
        locale = _LOCALE.get((plan.language or "vi").strip().lower()[:2], "vi-VN")
        runs = plan.voice_runs()
        beats = list(plan.timeline)
        total = len(beats)
        logger.info("story_narration: %d beats in %d voice-run(s) lang=%s",
                    total, len(runs), locale)

        # Silent-hold beats (no text) resolve instantly; only text beats hit TTS.
        spoken = []
        for beat in beats:
            if (beat.narration or "").strip():
                spoken.append(beat)
            else:                                          # silent hold beat (intentional)
                plan.render.beat_audio[beat.id] = BeatAudio("", max(0.0, float(beat.hold_sec or 0.0)), [])

        done = total - len(spoken)                         # silent beats already resolved

        def _emit(n: int) -> None:
            if on_progress is not None:
                try:
                    on_progress(n, total)
                except Exception:
                    pass
        _emit(done)

        def _synth_one(beat) -> "tuple[str, BeatAudio, bool]":
            """Synthesize ONE beat → (beat_id, BeatAudio, produced_no_audio). Runs in a
            worker thread — no shared mutable state, no DB, own output file."""
            text = (beat.narration or "").strip()
            engine, voice_id = _voice_for(plan, beat.speaker_id)
            gender = _gender_for(plan, beat.speaker_id)
            rate = _reading_speed_to_rate(beat.reading_speed)
            out = d / f"beat_{beat.id}.mp3"
            try:
                path = generate_narration_audio(
                    text=text, language=locale, gender=gender, rate=rate,
                    job_id=f"{job_id}-{beat.id}", voice_id=(voice_id or None),
                    output_path=str(out), content_type="vlog", tts_engine=engine,
                    emotion=(beat.emotion or ""),
                )
            except Exception as exc:
                logger.warning("story_narration: beat %s TTS failed %s", beat.id, exc)
                path = None
            if not path or not Path(path).exists() or Path(path).stat().st_size <= 0:
                return beat.id, BeatAudio("", 0.0, []), True
            dur = probe_audio_duration(str(path))
            return beat.id, BeatAudio(str(path), float(dur or 0.0), []), False

        try:
            workers = max(1, int(os.getenv("STORY_TTS_WORKERS", "4") or 4))
        except (TypeError, ValueError):
            workers = 4

        if workers <= 1 or len(spoken) <= 1:               # serial path (rollback / trivial)
            for beat in spoken:
                bid, ba, no_audio = _synth_one(beat)
                plan.render.beat_audio[bid] = ba
                if no_audio:
                    silent_spoken.append(bid)
                done += 1
                _emit(done)
        else:                                              # bounded parallel synth
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_synth_one, b): b.id for b in spoken}
                for f in as_completed(futs):
                    try:
                        bid, ba, no_audio = f.result()
                    except Exception as exc:               # _synth_one already guards; belt-and-suspenders
                        bid = futs[f]
                        ba, no_audio = BeatAudio("", 0.0, []), True
                        logger.warning("story_narration: beat %s task error %s", bid, exc)
                    plan.render.beat_audio[bid] = ba
                    if no_audio:
                        silent_spoken.append(bid)
                    done += 1
                    _emit(done)
    except Exception as exc:
        logger.warning("story_narration: synthesize_timeline error %s", exc)
    if silent_spoken:
        logger.warning("story_narration: %d spoken beat(s) produced NO audio (every TTS "
                       "engine failed) — they render silent: %s", len(silent_spoken), silent_spoken)
        if effective_channel:
            try:
                from app.features.render.engine.pipeline.render_events import _emit_render_event
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id, event="story.tts.silent",
                    level="WARNING",
                    message=(f"{len(silent_spoken)} narrated beat(s) had no audio — TTS "
                             f"unavailable (check network / voice config); they play silent."),
                    step="render.story", context={"silent_beats": silent_spoken})
            except Exception:
                pass


__all__ = ["synthesize_timeline"]
