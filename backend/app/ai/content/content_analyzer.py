"""
content_analyzer.py — ContentAnalyzer: single-pass content understanding.

Runs all analysis modules (transcript, emotion, beat, structure, hook, silence)
ONCE per render job and packages results into ContentAnalysisResult.

Downstream consumers (AI Director, segment scoring, S4.x refinements) read
from ContentAnalysisResult instead of each re-running the same analyzers.

Public API:
    ContentAnalyzer.analyze(source_path, srt_path, source_duration) -> ContentAnalysisResult
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from app.orchestration.content_analysis import ContentAnalysisResult

logger = logging.getLogger("app.ai.content")


class ContentAnalyzer:
    """Stateless single-pass content analysis. All methods are classmethods."""

    @classmethod
    def analyze(
        cls,
        source_path: str,
        srt_path: Optional[str],
        source_duration: float = 0.0,
    ) -> ContentAnalysisResult:
        """Run full content analysis on a source video + transcript.

        Never raises. Returns ContentAnalysisResult(available=False) on total
        failure so render pipeline can always call this safely.
        """
        t0 = time.perf_counter()
        warnings: list[str] = []

        try:
            # ── 1. Normalize transcript chunks ────────────────────────────────
            chunks = cls._load_chunks(srt_path, warnings)
            if not chunks:
                return ContentAnalysisResult(
                    available=False,
                    source_duration=source_duration,
                    analysis_ms=int((time.perf_counter() - t0) * 1000),
                    warnings=["no_transcript"],
                )

            # ── 2. Emotion analysis ───────────────────────────────────────────
            dominant_emotion, emotion_score = cls._analyze_emotion(chunks, warnings)

            # ── 3. Beat / pacing analysis ─────────────────────────────────────
            beat_available, bpm, beat_count, energy_level, pacing_style, suggested_cut_style = (
                cls._analyze_beats(source_path, warnings)
            )

            # ── 4. Silence map ────────────────────────────────────────────────
            silence_penalty = cls._analyze_silence(chunks, warnings)

            # ── 5. Narrative arc (4-window structural analysis) ───────────────
            narrative_arc = cls._build_narrative_arc(chunks, source_duration, warnings)

            # ── 6. Hook positions ─────────────────────────────────────────────
            hook_positions = cls._extract_hook_positions(chunks, source_duration, warnings)

            # ── 7. Speaker segments ───────────────────────────────────────────
            speaker_segments = cls._build_speaker_segments(chunks, warnings)

            # ── 8. Emotion arc (per-window) ───────────────────────────────────
            emotion_arc = cls._build_emotion_arc(chunks, source_duration, warnings)

            return ContentAnalysisResult(
                available=True,
                chunks=chunks,
                narrative_arc=narrative_arc,
                hook_positions=hook_positions,
                dominant_emotion=dominant_emotion,
                emotion_score=emotion_score,
                emotion_arc=emotion_arc,
                speaker_segments=speaker_segments,
                beat_available=beat_available,
                bpm=bpm,
                beat_count=beat_count,
                energy_level=energy_level,
                pacing_style=pacing_style,
                suggested_cut_style=suggested_cut_style,
                silence_penalty=silence_penalty,
                source_duration=source_duration,
                analysis_ms=int((time.perf_counter() - t0) * 1000),
                warnings=warnings,
            )

        except Exception as exc:
            logger.warning("content_analyzer_failed: %s", exc)
            return ContentAnalysisResult(
                available=False,
                source_duration=source_duration,
                analysis_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[f"content_analyzer_exception:{type(exc).__name__}"],
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _load_chunks(cls, srt_path: Optional[str], warnings: list) -> list:
        """Read SRT file and normalize into chunks. Returns [] on failure."""
        if not srt_path:
            warnings.append("no_srt_path")
            return []
        try:
            from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks
            srt_text = Path(str(srt_path)).read_text(encoding="utf-8", errors="replace")
            chunks = normalize_transcript_chunks(srt_text)
            if not chunks:
                warnings.append("srt_empty_or_unparseable")
            return chunks
        except Exception as exc:
            warnings.append(f"srt_load_failed:{type(exc).__name__}")
            return []

    @classmethod
    def _analyze_emotion(
        cls, chunks: list, warnings: list
    ) -> tuple[str, float]:
        """Return (dominant_emotion, emotion_score). Never raises."""
        try:
            from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion
            result = analyze_pacing_emotion(chunks)
            return (
                str(result.get("dominant", "neutral")),
                float(result.get("score", 0.0)),
            )
        except Exception as exc:
            warnings.append(f"emotion_analysis_failed:{type(exc).__name__}")
            return "neutral", 0.0

    @classmethod
    def _analyze_beats(
        cls, source_path: str, warnings: list
    ) -> tuple[bool, Optional[float], int, Optional[float], str, str]:
        """Return (beat_available, bpm, beat_count, energy_level, pacing_style, cut_style). Never raises."""
        try:
            from app.ai.analyzers.beat_analyzer import analyze_beats
            result = analyze_beats(source_path)
            if not result.get("available"):
                warnings.extend(result.get("warnings") or [])
                return False, None, 0, None, "default", "standard"
            bpm = result.get("bpm")
            beat_count = len(result.get("beats") or [])
            energy = (result.get("energy") or {}).get("mean")
            pacing_style, cut_style = cls._infer_pacing(bpm)
            return True, bpm, beat_count, energy, pacing_style, cut_style
        except Exception as exc:
            warnings.append(f"beat_analysis_failed:{type(exc).__name__}")
            return False, None, 0, None, "default", "standard"

    @staticmethod
    def _infer_pacing(bpm: Optional[float]) -> tuple[str, str]:
        if bpm is None:
            return "default", "standard"
        if bpm >= 140:
            return "fast", "fast_cut"
        if bpm >= 100:
            return "balanced", "medium_cut"
        return "slow", "slow_cut"

    @classmethod
    def _analyze_silence(cls, chunks: list, warnings: list) -> float:
        """Return silence_penalty 0–100. Never raises."""
        try:
            from app.ai.analyzers.silence_analyzer import estimate_silence_penalty
            return float(estimate_silence_penalty(chunks))
        except Exception as exc:
            warnings.append(f"silence_analysis_failed:{type(exc).__name__}")
            return 0.0

    @classmethod
    def _build_narrative_arc(
        cls, chunks: list, source_duration: float, warnings: list
    ) -> list:
        """Divide video into 4 time windows and detect narrative phase in each.

        Returns [{start, end, phase, confidence}]. Never raises.
        Uses structure_analyzer on each quarter to find phase markers.
        """
        if not chunks or source_duration <= 0:
            return []
        try:
            from app.ai.analyzers.structure_analyzer import (
                analyze_window_structure,
                STRUCTURE_INTELLIGENCE_ENABLED,
            )
            if not STRUCTURE_INTELLIGENCE_ENABLED:
                return []

            arc = []
            quarter = source_duration / 4.0
            phase_labels = ["hook", "build", "climax", "outro"]

            for i, label in enumerate(phase_labels):
                win_start = i * quarter
                win_end = (i + 1) * quarter
                try:
                    struct = analyze_window_structure(chunks, win_start, win_end)
                    phases = struct.get("phases_detected") or []
                    # Confidence: fraction of expected phase signals found
                    confidence = min(1.0, len(phases) / 3.0) if phases else 0.1
                    arc.append({
                        "start": round(win_start, 2),
                        "end": round(win_end, 2),
                        "phase": label,
                        "confidence": round(confidence, 3),
                        "phases_detected": phases,
                    })
                except Exception:
                    arc.append({
                        "start": round(win_start, 2),
                        "end": round(win_end, 2),
                        "phase": label,
                        "confidence": 0.1,
                        "phases_detected": [],
                    })
            return arc
        except Exception as exc:
            warnings.append(f"narrative_arc_failed:{type(exc).__name__}")
            return []

    @classmethod
    def _extract_hook_positions(
        cls, chunks: list, source_duration: float, warnings: list
    ) -> list:
        """Find top hook candidates in the first 30% of the video.

        Returns [{time, score, hook_type, text}]. Never raises.
        """
        if not chunks:
            return []
        try:
            from app.ai.analyzers.hook_analyzer import (
                score_hook_text,
                detect_hook_type,
                get_opening_window_text,
            )
            hook_window_end = source_duration * 0.30 if source_duration > 0 else float("inf")
            candidates = []
            for chunk in chunks:
                t = float(chunk.get("start", 0))
                if t > hook_window_end:
                    break
                text = str(chunk.get("text", ""))
                if not text.strip():
                    continue
                score = score_hook_text(text)
                if score >= 20.0:
                    candidates.append({
                        "time": round(t, 2),
                        "score": round(score, 1),
                        "hook_type": detect_hook_type(text),
                        "text": text[:120],
                    })
            # Sort by score, keep top 5
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:5]
        except Exception as exc:
            warnings.append(f"hook_extraction_failed:{type(exc).__name__}")
            return []

    @classmethod
    def _build_speaker_segments(cls, chunks: list, warnings: list) -> list:
        """Group chunks into speaker segments by pause gaps.

        Returns [{start, end, speech_density, is_question}]. Never raises.
        A new segment starts when there's a gap > 1.5s between chunks.
        """
        if not chunks:
            return []
        try:
            from app.ai.analyzers.silence_analyzer import score_speech_density
            _GAP_THRESHOLD = 1.5
            segments = []
            seg_chunks: list = []

            def _flush(seg_chunks: list) -> None:
                if not seg_chunks:
                    return
                start = float(seg_chunks[0].get("start", 0))
                end = float(seg_chunks[-1].get("end", start))
                avg_density = sum(
                    score_speech_density(c) for c in seg_chunks
                ) / len(seg_chunks)
                full_text = " ".join(str(c.get("text", "")) for c in seg_chunks)
                segments.append({
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "speech_density": round(avg_density, 1),
                    "is_question": full_text.strip().endswith("?"),
                })

            for i, chunk in enumerate(chunks):
                if i == 0:
                    seg_chunks.append(chunk)
                    continue
                prev_end = float(chunks[i - 1].get("end", 0))
                curr_start = float(chunk.get("start", 0))
                if curr_start - prev_end > _GAP_THRESHOLD:
                    _flush(seg_chunks)
                    seg_chunks = [chunk]
                else:
                    seg_chunks.append(chunk)
            _flush(seg_chunks)
            return segments
        except Exception as exc:
            warnings.append(f"speaker_segments_failed:{type(exc).__name__}")
            return []

    @classmethod
    def _build_emotion_arc(
        cls, chunks: list, source_duration: float, warnings: list, num_windows: int = 6
    ) -> list:
        """Build per-window emotion map across the video.

        Returns [{start, end, emotion, intensity}]. Never raises.
        Divides transcript into num_windows equal time windows.
        """
        if not chunks or source_duration <= 0:
            return []
        try:
            from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion
            window_size = source_duration / num_windows
            arc = []
            for i in range(num_windows):
                win_start = i * window_size
                win_end = (i + 1) * window_size
                win_chunks = [
                    c for c in chunks
                    if float(c.get("start", 0)) >= win_start
                    and float(c.get("start", 0)) < win_end
                ]
                if not win_chunks:
                    continue
                result = analyze_pacing_emotion(win_chunks)
                arc.append({
                    "start": round(win_start, 2),
                    "end": round(win_end, 2),
                    "emotion": str(result.get("dominant", "neutral")),
                    "intensity": round(float(result.get("score", 0.0)) / 100.0, 3),
                })
            return arc
        except Exception as exc:
            warnings.append(f"emotion_arc_failed:{type(exc).__name__}")
            return []
