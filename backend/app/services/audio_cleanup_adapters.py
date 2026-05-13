from __future__ import annotations

import importlib
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.dependencies import has_deepfilternet
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

_DEEPFILTERNET_TIMEOUT_SEC = 180
_DEEPFILTERNET_SAMPLE_RATE = 48000


@dataclass
class AudioCleanupResult:
    input_path: str
    output_path: str | None = None
    engine: str = "none"
    applied: bool = False
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


class NoopAudioCleanupAdapter:
    engine_name = "none"

    def is_available(self) -> bool:
        return True

    def cleanup(self, input_path: str, output_path: str | None = None) -> AudioCleanupResult:
        start = time.perf_counter()
        return AudioCleanupResult(
            input_path=input_path,
            output_path=input_path,
            engine=self.engine_name,
            applied=False,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )


class DeepFilterNetAdapter:
    engine_name = "deepfilternet"

    def is_available(self) -> bool:
        return has_deepfilternet()

    def cleanup(self, input_path: str, output_path: str | None = None) -> AudioCleanupResult:
        start = time.perf_counter()
        if not self.is_available():
            return self._result(input_path, start, ["deepfilternet_unavailable"])

        source = Path(input_path)
        target = _resolve_cleanup_output_path(source, output_path)
        work_wav = source.with_name(f"{source.stem}.deepfilternet.input.wav")

        try:
            api = _load_deepfilternet_api()
        except Exception:
            return self._result(input_path, start, ["deepfilternet_import_failed"])

        try:
            original_duration = _probe_audio_duration(str(source))
            _convert_audio_to_wav(str(source), str(work_wav))

            model, df_state, _ = api["init_df"]()
            sample_rate = _deepfilternet_sample_rate(df_state)
            audio, _ = api["load_audio"](str(work_wav), sr=sample_rate)
            enhanced = api["enhance"](model, df_state, audio)
            api["save_audio"](str(target), enhanced, sample_rate)

            if not target.exists() or target.stat().st_size <= 0:
                target.unlink(missing_ok=True)
                return self._result(input_path, start, ["deepfilternet_output_invalid"])

            cleaned_duration = _probe_audio_duration(str(target))
            if not _duration_within_tolerance(original_duration, cleaned_duration):
                target.unlink(missing_ok=True)
                return self._result(input_path, start, ["deepfilternet_duration_mismatch"])

            return AudioCleanupResult(
                input_path=input_path,
                output_path=str(target),
                engine=self.engine_name,
                applied=True,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception:
            target.unlink(missing_ok=True)
            return self._result(input_path, start, ["deepfilternet_runtime_failed"])
        finally:
            work_wav.unlink(missing_ok=True)

    def _result(
        self,
        input_path: str,
        start: float,
        warnings: list[str],
    ) -> AudioCleanupResult:
        return AudioCleanupResult(
            input_path=input_path,
            output_path=input_path,
            engine=self.engine_name,
            applied=False,
            warnings=warnings,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )


def cleanup_audio_with_adapter(
    input_path: str,
    output_path: str | None,
    *,
    engine: str,
    logger=None,
) -> AudioCleanupResult:
    requested = str(engine or "none").strip().lower()

    if requested == "none":
        return NoopAudioCleanupAdapter().cleanup(input_path, output_path)

    if requested == "deepfilternet":
        result = DeepFilterNetAdapter().cleanup(input_path, output_path)
        if result.applied:
            return result
        if logger is not None:
            logger.warning(
                "audio_cleanup_adapter_fallback requested=%s warnings=%s fallback=none elapsed_ms=%d",
                requested,
                ",".join(result.warnings),
                result.elapsed_ms,
            )
        result.engine = "none"
        return result

    if logger is not None:
        logger.warning("audio_cleanup_adapter_unknown requested=%s fallback=none", requested)
    result = NoopAudioCleanupAdapter().cleanup(input_path, output_path)
    result.warnings.append("unknown_audio_cleanup_engine")
    return result


def _resolve_cleanup_output_path(input_path: Path, output_path: str | None) -> Path:
    if output_path:
        requested = Path(output_path)
        if requested.resolve() != input_path.resolve():
            return requested.with_suffix(".wav")
    return input_path.with_name(f"{input_path.stem}.cleaned.wav")


def _run_command(command: list[str], *, timeout_sec: int = _DEEPFILTERNET_TIMEOUT_SEC) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )


def _convert_audio_to_wav(input_path: str, wav_path: str) -> None:
    _run_command(
        [
            get_ffmpeg_bin(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(_DEEPFILTERNET_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            wav_path,
        ]
    )
    target = Path(wav_path)
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError("audio conversion produced empty wav")


def _probe_audio_duration(path: str) -> float:
    proc = subprocess.run(
        [
            get_ffprobe_bin(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(str(proc.stdout or "").strip())


def _duration_within_tolerance(original_duration: float, cleaned_duration: float) -> bool:
    tolerance = max(0.15, abs(original_duration) * 0.02)
    return abs(float(original_duration) - float(cleaned_duration)) <= tolerance


def _load_deepfilternet_api() -> dict:
    try:
        module = importlib.import_module("df.enhance")
    except Exception:
        module = importlib.import_module("deepfilternet.enhance")
    return {
        "init_df": getattr(module, "init_df"),
        "load_audio": getattr(module, "load_audio"),
        "enhance": getattr(module, "enhance"),
        "save_audio": getattr(module, "save_audio"),
    }


def _deepfilternet_sample_rate(df_state) -> int:
    sr = getattr(df_state, "sr", None)
    if callable(sr):
        try:
            return int(sr())
        except Exception:
            return _DEEPFILTERNET_SAMPLE_RATE
    if sr:
        try:
            return int(sr)
        except Exception:
            return _DEEPFILTERNET_SAMPLE_RATE
    return _DEEPFILTERNET_SAMPLE_RATE
