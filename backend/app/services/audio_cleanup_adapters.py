from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.ai.dependencies import has_deepfilternet


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
        warnings = []
        if not self.is_available():
            warnings.append("deepfilternet_unavailable")
        warnings.append("deepfilternet_adapter_not_implemented")
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
