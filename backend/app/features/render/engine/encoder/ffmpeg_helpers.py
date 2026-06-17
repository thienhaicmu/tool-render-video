
import json
import os
import subprocess
import threading
import time
import logging
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin, _summarize_ffmpeg_stderr
from app.features.render.engine.encoder.encoder_helpers import (
    has_encoder as _has_encoder,
    nvenc_runtime_ready as _nvenc_runtime_ready,
    reup_audio_filter as _reup_audio_filter,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource semaphores
# ---------------------------------------------------------------------------
# Consumer NVIDIA GPUs support 3–5 concurrent NVENC sessions. Exceeding the
# limit causes encode failures with "no NVENC capable devices found".
# Override with NVENC_MAX_SESSIONS env var if your GPU supports more.
_NVENC_SEM_VALUE: int = max(1, int(os.getenv("NVENC_MAX_SESSIONS", "3")))
NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)

# Maximum wall-clock seconds a single FFmpeg encode call is allowed to run.
# A hung FFmpeg (codec bug, I/O stall, corrupted input) would otherwise hold a
# JOB_SEMAPHORE slot forever, stalling all further renders.
# Override with FFMPEG_TIMEOUT_SECONDS env var (e.g. for very long source files).
_FFMPEG_TIMEOUT_SEC: int = max(60, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600")))

# Thread-local slot for the per-job cancel event.
# render_pipeline sets it at the start of each part so _run_ffmpeg_with_retry can
# kill the FFmpeg Popen when a cancel is requested without needing an extra argument.
_tls = threading.local()


def set_thread_cancel_event(ev) -> None:
    """Register a cancel threading.Event for the current worker thread."""
    _tls.cancel_event = ev


def get_thread_cancel_event():
    """Return this thread's cancel event, or None if none registered.

    T2.2 — Audit 2026-06-08 closure (Batch A V9-F3). The OpenCV
    motion-tracking loops in engine/motion/ call ``check_thread_cancel``
    below to break out of long per-frame loops when the operator
    clicks Cancel. The getter is exposed so external callers can poll
    the same event the FFmpeg subprocess monitor uses.
    """
    return getattr(_tls, "cancel_event", None)


def check_thread_cancel() -> None:
    """Raise JobCancelledError if the current thread's cancel event is set.

    Cheap O(1) helper for use inside hot loops where threading a
    ``job_id`` argument through the call chain is impractical.
    Imports ``JobCancelledError`` lazily to avoid an encoder ↔
    jobs/cancel import cycle. The check is a no-op (None compare +
    early return) on threads that never registered a cancel event,
    so direct test calls into motion modules are unaffected.
    """
    ev = getattr(_tls, "cancel_event", None)
    if ev is not None and ev.is_set():
        from app.jobs.cancel import JobCancelledError
        raise JobCancelledError("operation cancelled by user")

# ---------------------------------------------------------------------------
# ffprobe metadata cache — keyed by (abspath, mtime_ns, size_bytes)
# ---------------------------------------------------------------------------
# Consolidates multiple per-attribute probes into one subprocess call per file.
# Cache is invalidated automatically when file mtime or size changes.
# Failed probes are never cached — they return zero/None defaults and retry.
_PROBE_CACHE_MAX = 500
_PROBE_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_PROBE_CACHE_LOCK = threading.Lock()


def _file_probe_key(path: str) -> "tuple | None":
    """Return (abspath, mtime_ns, size) cache key, or None if stat fails."""
    try:
        st = Path(path).stat()
        return (str(Path(path).resolve()), st.st_mtime_ns, st.st_size)
    except Exception:
        return None


def probe_video_metadata(path: str, timeout: int = 15) -> dict:
    """Return {duration, fps, has_audio, has_video, width, height} for path.

    Runs one ffprobe JSON call and caches by (abspath, mtime, size) so repeated
    probes on the same unmodified file cost zero subprocess calls.
    Failed probes are not cached — zero/None defaults are returned and retried.
    """
    key = _file_probe_key(path)
    if key:
        with _PROBE_CACHE_LOCK:
            cached = _PROBE_CACHE.get(key)
        if cached is not None:
            return cached

    result: dict = {
        "duration": None,
        "fps": 0.0,
        "has_audio": False,
        "has_video": False,
        "width": 0,
        "height": 0,
        # Perf-opt Phase 8 (R27) — audio_codec lets callers like
        # render_part decide whether ``-c:a copy`` is safe (no audio
        # filter + source already AAC = bit-identical pass-through).
        # Empty string when no audio stream or probe failed.
        "audio_codec": "",
    }
    try:
        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,avg_frame_rate,r_frame_rate,width,height",
            "-of", "json", str(path),
        ]
        t0 = time.monotonic()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        _ms = int((time.monotonic() - t0) * 1000)
        if r.returncode == 0:
            data = json.loads(r.stdout or "{}")
            fmt = data.get("format", {})
            try:
                raw_dur = fmt.get("duration")
                if raw_dur:
                    result["duration"] = float(raw_dur)
            except (ValueError, TypeError):
                pass
            for stream in data.get("streams", []):
                ct = stream.get("codec_type", "")
                if ct == "video" and not result["has_video"]:
                    result["has_video"] = True
                    try:
                        result["width"] = int(stream.get("width") or 0)
                        result["height"] = int(stream.get("height") or 0)
                    except (ValueError, TypeError):
                        pass
                    for fps_field in ("avg_frame_rate", "r_frame_rate"):
                        fps_val = _parse_fps_ratio(stream.get(fps_field) or "")
                        if 1.0 <= fps_val <= 120.0:
                            result["fps"] = fps_val
                            break
                elif ct == "audio":
                    result["has_audio"] = True
                    # Phase 8 (R27) — first audio stream wins (mirrors
                    # the first-video-stream pattern above). Lower-cased
                    # so callers can compare against a literal "aac".
                    if not result["audio_codec"]:
                        result["audio_codec"] = str(stream.get("codec_name") or "").lower()
            logger.debug(
                "ffprobe_metadata_ms=%d path=%s has_video=%s has_audio=%s fps=%.1f dur=%s",
                _ms, Path(path).name, result["has_video"], result["has_audio"],
                result["fps"], result["duration"],
            )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe_metadata_timeout path=%s timeout=%ds", Path(path).name, timeout)
        return result
    except Exception:
        return result

    # Only store probes where we confirmed video presence — avoids caching garbage.
    if key and result["has_video"]:
        with _PROBE_CACHE_LOCK:
            _PROBE_CACHE[key] = result
            if len(_PROBE_CACHE) > _PROBE_CACHE_MAX:
                _PROBE_CACHE.popitem(last=False)  # evict oldest entry
    return result


def extract_thumbnail_frame(
    path: str,
    offset_sec: float = 0.5,
    width: int = 320,
    timeout: int = 10,
) -> "bytes | None":
    """Extract one JPEG frame at offset_sec from path. Returns raw JPEG bytes or None."""
    try:
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-ss", str(max(0.0, offset_sec)),
            "-i", str(path),
            "-frames:v", "1",
            "-vf", f"scale={max(32, width)}:-2",
            "-f", "image2",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode == 0 and len(r.stdout) > 100:
            return bytes(r.stdout)
    except Exception:
        pass
    return None


# Curated set of NVENC encoder codec names recognised by FFmpeg.
# Extend this set as NVIDIA releases new codecs (e.g. a future avx_nvenc).
# Using an exact-match set rather than a substring search avoids the
# false-positive trap where a filename or path token containing the
# literal substring "_nvenc" (e.g. /tmp/render_my_nvenc.mp4) would
# incorrectly trigger semaphore acquisition.
NVENC_CODECS: frozenset[str] = frozenset({
    "h264_nvenc",
    "hevc_nvenc",
    "av1_nvenc",
})


def _argv_uses_nvenc(args: list[str]) -> bool:
    """Return True if any argv token exactly matches a known NVENC codec.

    Sprint 4.2 (audit 2026-06-02 P2-B1) introduced this guard so that
    _run_ffmpeg_with_retry can acquire NVENC_SEMAPHORE automatically for
    any FFmpeg invocation that uses an NVENC codec — closing the gap
    that the explicit acquire sites in clip_renderer.py and
    overlay_compositor.py alone could not cover.

    Batch 3 hardening (audit FINDING-R01/BR04, 2026-06-06): switched
    from substring match to exact-set membership. The old form
    `"_nvenc" in token.lower()` matched filenames and paths that happen
    to contain the literal substring, occasionally producing false
    positives that held the semaphore unnecessarily. The new form is
    precise: only the codec tokens themselves trigger the lock.
    """
    return any(isinstance(t, str) and t in NVENC_CODECS for t in args)


def _run_ffmpeg_with_retry(
    command: list[str],
    retry_count: int = 2,
    wait_sec: float = 0.8,
    *,
    nvenc_externally_held: bool = False,
):
    """Run an FFmpeg subprocess with retry, cancel, and timeout protection.

    nvenc_externally_held=True: caller already holds NVENC_SEMAPHORE
    (e.g. base_clip_renderer for render_base_clip, render_part, and
    render_part_smart after Sprint 5.2; plus overlay_compositor).
    Skip the internal acquire to avoid double-counting against the
    GPU session limit.

    nvenc_externally_held=False (default): if the argv uses an NVENC
    codec, acquire the semaphore here and release after the subprocess
    completes. Sprint 4.2 closed-gap protection.
    """
    # Pick up the cancel event registered by render_pipeline for this worker thread.
    cancel_event = getattr(_tls, 'cancel_event', None)
    needs_nvenc_lock = (not nvenc_externally_held) and _argv_uses_nvenc(command)
    # Sprint 6.C: instrumentation hooks. The metrics module's no-op shim
    # absorbs any failure if prometheus_client is unavailable.
    from app.services.metrics import (
        FFMPEG_DURATION,
        FFMPEG_INVOCATIONS_TOTAL,
        NVENC_ACQUIRE_WAIT,
        NVENC_ACTIVE_SESSIONS,
    )
    if needs_nvenc_lock:
        _nvenc_wait_start = time.monotonic()
        NVENC_SEMAPHORE.acquire()
        try:
            NVENC_ACQUIRE_WAIT.observe(time.monotonic() - _nvenc_wait_start)
            NVENC_ACTIVE_SESSIONS.inc()
        except Exception:
            pass
    _ffmpeg_start = time.monotonic()
    _final_result = "ok"
    try:
        attempt = 0
        while True:
            attempt += 1
            try:
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                # Run communicate in a daemon thread so the main loop can poll for
                # cancel/timeout without risking pipe-buffer deadlock.
                _done = threading.Event()
                _result: list = [None, None, None]  # [stdout, stderr, returncode]

                def _communicate(_p=proc, _d=_done, _r=_result):
                    out, err = _p.communicate()
                    _r[0] = out
                    _r[1] = err
                    _r[2] = _p.returncode
                    _d.set()

                threading.Thread(target=_communicate, daemon=True).start()

                deadline = time.monotonic() + _FFMPEG_TIMEOUT_SEC
                while not _done.wait(timeout=1.0):
                    if cancel_event is not None and cancel_event.is_set():
                        proc.terminate()
                        if not _done.wait(timeout=5):
                            proc.kill()
                            _done.wait(timeout=2)
                        raise RuntimeError("FFmpeg cancelled")
                    if time.monotonic() > deadline:
                        proc.terminate()
                        if not _done.wait(timeout=5):
                            proc.kill()
                            _done.wait(timeout=2)
                        raise RuntimeError(
                            f"FFmpeg timed out after {_FFMPEG_TIMEOUT_SEC}s and was killed. "
                            "Increase FFMPEG_TIMEOUT_SECONDS env var for very long source files."
                        )

                stdout = _result[0] or ""
                stderr = _result[1] or ""
                if _result[2] != 0:
                    raise subprocess.CalledProcessError(_result[2], command, stdout, stderr)
                return subprocess.CompletedProcess(command, _result[2], stdout, stderr)
            except RuntimeError as rt_exc:
                # Categorize for the metric label. Re-raise unchanged.
                _msg = str(rt_exc).lower()
                if "cancelled" in _msg:
                    _final_result = "cancelled"
                elif "timed out" in _msg:
                    _final_result = "timeout"
                else:
                    _final_result = "failed"
                raise
            except subprocess.CalledProcessError as exc:
                if attempt > retry_count:
                    _final_result = "failed"
                    stderr_text = exc.stderr or ""
                    diag = _summarize_ffmpeg_stderr(stderr_text)
                    stderr_tail = stderr_text[-2000:].strip()
                    raise RuntimeError(
                        f"FFmpeg render failed: {diag} (exit={exc.returncode})"
                        + (f"\n{stderr_tail}" if stderr_tail else "")
                    ) from exc
                time.sleep(wait_sec * attempt)
            except Exception:
                if attempt > retry_count:
                    _final_result = "failed"
                    raise
                time.sleep(wait_sec * attempt)
    finally:
        try:
            FFMPEG_INVOCATIONS_TOTAL.labels(result=_final_result).inc()
            FFMPEG_DURATION.labels(result=_final_result).observe(time.monotonic() - _ffmpeg_start)
        except Exception:
            pass
        if needs_nvenc_lock:
            try:
                NVENC_ACTIVE_SESSIONS.dec()
            except Exception:
                pass
            NVENC_SEMAPHORE.release()


# ---------------------------------------------------------------------------
# nvenc_available — cached GPU-readiness check exported to render_pipeline
# _resolve_codec — kept as a proper function so tests can patch _has_encoder
#                  and _nvenc_runtime_ready at the render_engine module level
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Return True if at least one NVENC encoder is present and runtime-ready.

    Cached at module level so the GPU probe runs at most once per process.
    Importable by other modules (e.g. render_pipeline) to inform worker
    count decisions before any encoding actually starts.
    """
    for codec_name in ("h264_nvenc", "hevc_nvenc"):
        if _has_encoder(codec_name) and _nvenc_runtime_ready(codec_name):
            return True
    return False


def _resolve_codec(codec: str, encoder_mode: str = "auto"):
    c = (codec or "h264").lower()
    mode = (encoder_mode or "auto").lower()

    if mode in ("auto", "nvenc"):
        if c == "h265" and _has_encoder("hevc_nvenc") and _nvenc_runtime_ready("hevc_nvenc"):
            return "hevc_nvenc"
        if c != "h265" and _has_encoder("h264_nvenc") and _nvenc_runtime_ready("h264_nvenc"):
            return "h264_nvenc"
        if mode == "nvenc":
            # Requested nvenc but unavailable: fallback CPU.
            pass

    if c == "h265":
        return "libx265"
    return "libx264"


def _effect_filter(effect_preset: str):
    preset = (effect_preset or "slay_soft_01").lower()
    if preset == "slay_pop_01":
        return "eq=contrast=1.08:saturation=1.18:brightness=0.01:gamma=1.02,unsharp=5:5:1.2:3:3:0.5"
    if preset == "story_clean_01":
        return "eq=contrast=1.03:saturation=1.05:brightness=0.0,unsharp=3:3:0.6:3:3:0.15"
    if preset == "social_bright":
        return "eq=contrast=1.06:saturation=1.22:brightness=0.02:gamma=0.98,unsharp=5:5:1.0:3:3:0.4"
    if preset == "cinematic_soft":
        return "eq=contrast=1.04:saturation=0.92:brightness=-0.01:gamma=1.04,unsharp=3:3:0.5:3:3:0.1,hqdn3d=1.5:1.5:6:6"
    if preset == "high_contrast":
        return "eq=contrast=1.15:saturation=1.10:brightness=-0.02:gamma=1.0,unsharp=7:7:1.5:5:5:0.6"
    # slay_soft_01 (default): natural cinematic look with light sharpening
    return "eq=contrast=1.05:saturation=1.10:brightness=0.0:gamma=1.01,unsharp=5:5:0.9:3:3:0.35"


def _zoom_burst_filter(
    max_zoom: float = 1.15,
    target_w: int = 720,
    target_h: int = 1280,
) -> str:
    """Return a scale+crop filter string that applies a static punch-in zoom.

    Scales up by max_zoom then crops back to target_w × target_h from center.
    Static (not animated) — zoompan was avoided because its default fps=25 and
    s=hd720 corrupt duration and size on 60fps vertical sources.
    Output is always exactly target_w × target_h with no timing changes.
    """
    return (
        f"scale=trunc(iw*{max_zoom:.4f}/2)*2:trunc(ih*{max_zoom:.4f}/2)*2:flags=lanczos,"
        f"crop={target_w}:{target_h}:(iw-{target_w})/2:(ih-{target_h})/2"
    )


# ---------------------------------------------------------------------------
# Phase 5.7 — Safe visual intensity → effect preset resolver
# ---------------------------------------------------------------------------
# Supported preset names (all keys in _effect_filter above):
#   slay_soft_01    default — natural cinematic, light sharpening
#   slay_pop_01     high energy — boosted contrast/saturation/unsharp
#   story_clean_01  subtle — low contrast/saturation, soft sharpening
#   social_bright   bright social — high saturation, strong brightness
#   cinematic_soft  cinematic desaturated — soft, denoised
#   high_contrast   maximum contrast — heaviest unsharp
#
# AI visual_intensity mapping (renderer-owned, AI never picks the preset name):
#   "low"    → "story_clean_01"  (subtle look, gentle processing)
#   "medium" → "slay_soft_01"    (natural default, matches schema default)
#   "high"   → "slay_pop_01"     (energetic pop look, boosted processing)
#
# Priority (documented in render contract):
#   1. FFmpeg safety (enforced by _effect_filter — only accepts known presets)
#   2. user_effect_is_explicit=True → return effect_preset unchanged
#   3. Valid visual_intensity_hint → map to known preset (renderer decides)
#   4. Default: return effect_preset unchanged

_VISUAL_INTENSITY_ALLOWED = frozenset({"low", "medium", "high"})

_VISUAL_INTENSITY_PRESET_MAP: dict[str, str] = {
    # low  → subtle look: lower contrast/saturation, softer sharpening
    "low": "story_clean_01",
    # medium → natural default: matches the schema default effect_preset
    "medium": "slay_soft_01",
    # high → energetic pop: boosted contrast/saturation/sharpening
    "high": "slay_pop_01",
}


def resolve_effect_preset_with_intensity(
    effect_preset: "str | None",
    visual_intensity_hint: "str | None",
    user_effect_is_explicit: bool = False,
) -> "str | None":
    """Map AI visual_intensity_hint to a renderer-owned effect preset.

    Phase 5.7 safe injection point — renderer OWNS the mapping table.
    AI may only pass None, "low", "medium", or "high".
    This function NEVER raises. Invalid inputs are silently ignored.

    Priority:
      1. user_effect_is_explicit=True → return effect_preset unchanged
      2. visual_intensity_hint is None or invalid → return effect_preset unchanged
      3. Valid hint → return mapped preset (only known supported presets)

    NEVER returns:
      - A raw FFmpeg filter string (no "vf=", "eq=", "unsharp=" content)
      - An unsupported preset name
      - A preset not listed in _effect_filter()

    Args:
        effect_preset:          The current effect_preset (may be None or default).
        visual_intensity_hint:  AI hint — one of None/"low"/"medium"/"high".
        user_effect_is_explicit: True when the user explicitly chose effect_preset.

    Returns:
        A known supported effect preset name, or effect_preset unchanged.
    """
    try:
        # Priority 1: user explicit wins unconditionally
        if user_effect_is_explicit:
            return effect_preset

        # Priority 2: missing or invalid hint → no change
        if not visual_intensity_hint:
            return effect_preset
        hint = str(visual_intensity_hint).strip().lower()
        if hint not in _VISUAL_INTENSITY_ALLOWED:
            return effect_preset

        # Priority 3: map to renderer-owned preset
        mapped = _VISUAL_INTENSITY_PRESET_MAP.get(hint)
        if mapped is None:
            # Defensive: hint in ALLOWED but not in map (shouldn't happen)
            return effect_preset
        return mapped
    except Exception:
        # Safety: never raise — return unchanged on any error
        return effect_preset


def _cinematic_color_filter(src_h: int, content_type: str = "vlog") -> "str | None":
    """Content-type-aware contrast/saturation lift after recompression.

    tutorial/interview: near-neutral — preserve screen and face authenticity.
    montage: slightly richer for energy feel.
    commentary/vlog: balanced lift (original behaviour).
    Disabled for sources below 480p.
    """
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "eq=contrast=1.01:saturation=1.01"
    if content_type == "montage":
        return "eq=contrast=1.03:saturation=1.06"
    return "eq=contrast=1.02:saturation=1.03"


def _cinematic_sharpen_filter(src_h: int, content_type: str = "vlog") -> "str | None":
    """Content-type-aware luma-only edge sharpening.

    tutorial/interview: slightly stronger for text and screen clarity.
    montage: reduced to avoid halos on fast motion.
    commentary/vlog: standard (original behaviour).
    Disabled for sources below 480p — halos appear on noisy/low-res content.
    """
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "unsharp=5:5:0.5:5:5:0.0"
    if content_type == "montage":
        return "unsharp=3:3:0.25:3:3:0.0"
    return "unsharp=5:5:0.4:5:5:0.0"


def _smart_denoise_filter(content_type: str, preset: str, src_h: int) -> "str | None":
    """Return an hqdn3d denoise filter string, or None when denoise should be skipped.

    montage: skipped — motion smearing risk outweighs benefit.
    slower/veryslow preset: full denoise (quality mode, no change to existing behaviour).
    slow preset + interview/tutorial: lite denoise for static talking-head / screen content.
    low-res source (<720p, any non-montage type): lite denoise — compressed noise amplified by upscale.
    """
    if content_type == "montage":
        return None
    if preset in ("slower", "veryslow"):
        return "hqdn3d=1.5:1.5:6:6"
    if preset == "slow" and content_type in ("interview", "tutorial"):
        return "hqdn3d=1.0:1.0:4:4"
    if 0 < src_h < 720:
        return "hqdn3d=0.8:0.8:3:3"
    return None


def content_type_crf_delta(content_type: str) -> int:
    """Return a CRF adjustment for content-type-aware encode sharpness.

    tutorial/interview: -2 — fine text and screen detail benefit from tighter quantisation.
    montage: +1 — fast motion benefits more from AQ than marginal CRF improvement.
    Others: 0 (no change from profile default).
    """
    return {"tutorial": -2, "interview": -2, "montage": 1}.get(content_type or "", 0)


def _build_audio_mix_filter(a0: str, a1: str, out: str) -> str:
    """Return the filter graph segment that mixes voice (a0) and BGM (a1) into out.

    BGM_DUCKING_ENABLED=1 (default): sidechaincompress ducks BGM during speech,
    then amix blends. Produces premium creator-grade mix without pumping.
    BGM_DUCKING_ENABLED=0: plain amix at static volume ratios (pre-OQ-2.1 behavior).
    """
    if os.environ.get("BGM_DUCKING_ENABLED", "1") == "1":
        # threshold=0.015 (~-36.5 dBFS): triggers on clear speech, not room noise.
        # ratio=3: BGM drops to ~40% during speech. attack=200ms, release=1000ms: no pumping.
        return (
            f"[{a1}][{a0}]sidechaincompress="
            f"threshold=0.015:ratio=3:attack=200:release=1000[bgm_ducked];"
            f"[{a0}][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[{out}]"
        )
    return f"[{a0}][{a1}]amix=inputs=2:duration=first:dropout_transition=2[{out}]"


def _build_audio_filter(loudnorm_enabled: bool, reup_mode: bool, speed: float) -> str | None:
    """Return a comma-joined -af filter string, or None when no audio processing is needed."""
    parts = []
    if loudnorm_enabled and not reup_mode:
        # Creator-grade audio polish: rumble removal → loudness target → gentle compression → limiter.
        # acompressor ratio=2 at -18dB threshold: natural dynamic control without pumping.
        parts.append("highpass=f=80")
        parts.append("loudnorm=I=-14:LRA=11:TP=-1.0")
        parts.append("acompressor=threshold=-18dB:ratio=2:attack=40:release=300:makeup=1.5")
        parts.append("alimiter=limit=0.95")
    if reup_mode:
        parts.append(_reup_audio_filter())
    if abs(speed - 1.0) > 1e-4:
        parts.append(f"atempo={speed:.4f}")
    return ",".join(parts) if parts else None


_FPS_CAP = 60  # hard ceiling — prevents encode overhead for HFR sources


def _parse_fps_ratio(s: str) -> float:
    """Parse a fraction string like '60/1' or '60000/1001' to a float. Returns 0.0 on failure."""
    s = (s or "").strip()
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _probe_fps(input_path: str) -> float:
    """Return source video fps via cached ffprobe. Returns 0.0 on any failure."""
    return probe_video_metadata(input_path)["fps"]


def _resolve_fps(input_path: str, output_fps: int) -> tuple[int, str]:
    """Determine output frame rate and return a log string.

    Policy
    ------
    output_fps == 0  (auto / not set):
        Preserve source fps, capped at _FPS_CAP.
    output_fps  > 0  (user-specified):
        Use min(user_fps, source_fps, _FPS_CAP).
        Never upscale beyond source — avoids judder without minterpolate.

    Returns (target_fps, policy_str).  Caller should log policy_str.
    """
    src_fps = _probe_fps(input_path)

    if src_fps <= 0:
        target = max(1, min(_FPS_CAP, output_fps or _FPS_CAP))
        return target, f"fps_policy=fallback(probe_failed) target={target}"

    src_int = int(round(src_fps))

    if not output_fps:
        target = max(1, min(src_int, _FPS_CAP))
        return target, f"fps_policy=auto src={src_fps:.3f} target={target}"

    target = max(1, min(src_int, output_fps, _FPS_CAP))
    return target, f"fps_policy=user({output_fps}) src={src_fps:.3f} target={target}"


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


def _has_audio_stream(input_path: str) -> bool:
    """Return True if the file has at least one audio stream (cached ffprobe)."""
    return probe_video_metadata(input_path)["has_audio"]


# Public alias — same behaviour, used by subtitle_engine and render_pipeline importers.
def has_audio_stream(input_path: str) -> bool:
    return _has_audio_stream(input_path)


def _probe_duration(input_path: str) -> "float | None":
    """Return video duration in seconds via cached ffprobe, or None on error."""
    return probe_video_metadata(input_path)["duration"]


def resolve_ffmpeg_threads(max_parallel_parts: int | None = None) -> int:
    cpu_total = os.cpu_count() or 4
    workers = max(1, int(max_parallel_parts or 2))
    return max(1, min(8, cpu_total // workers))


def resolve_target_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) output canvas for the given aspect_ratio string.

    Supported values: "1:1", "9:16", "16:9", "3:4", "4:5".
    Unknown values fall through to the portrait default (1080×1440).
    """
    ar = (aspect_ratio or "").strip()
    if ar == "1:1":
        return 1080, 1080
    if ar == "9:16":
        return 1080, 1920
    if ar == "16:9":
        return 1920, 1080
    return 1080, 1440  # 3:4, 4:5, and any unrecognised value

