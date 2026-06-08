"""pipeline_cache.py — Render cache helpers (scene, transcription, segment scores).

Extracted from render_pipeline.py (lines 175–264) as part of C-1 decomposition.
All logic is identical — this is a mechanical lift, not a rewrite.

Audit FINDING-BR14 closure (Batch 10F 2026-06-06): all four ``_*_cache_put``
helpers now write via a temp file + ``os.replace`` to give the cache file
atomic-rename semantics. The pruner in ``services/maintenance.py`` was
walking each subdir on a 30-minute cadence and could ``unlink`` a target
mid-write — the writer's flush would then either fail (Windows: sharing
violation) or write into an orphaned inode (POSIX). With atomic-rename the
file is either fully present or absent; the pruner can never observe a
half-written state. Belt-and-suspenders: the pruner also skips ``.tmp``
sidecars so a freshly-allocated tmp file that's about to be renamed in
can't be pruned mid-flight.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from app.core.config import APP_DATA_DIR

_RENDER_CACHE_TTL_SEC = 72 * 3600  # 72 h


def _render_cache_key(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()


# Audit FINDING-BR14 helpers — atomic write via temp + os.replace.
# os.replace is atomic on both POSIX (rename(2)) and Windows (MoveFileExW
# with MOVEFILE_REPLACE_EXISTING). The pruner is taught to skip the
# ".tmp" sidecar so even a 30-minute-stale tmp file (from a crashed
# writer) is not deleted out from under a concurrent writer.

def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via a ``.tmp`` sidecar.

    The pruner is instructed to skip ``.tmp`` files (see
    services/maintenance.prune_render_cache) so the sidecar is safe even
    if this process crashes between create and rename. A subsequent
    successful write will overwrite the orphan; the periodic prune will
    eventually evict it once its mtime ages past the TTL.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_copy2(src: Path, dst: Path) -> None:
    """``shutil.copy2`` source → tmp sidecar, then ``os.replace`` into dst."""
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(str(src), str(tmp))
    os.replace(tmp, dst)


def _scene_cache_get(source_path: str) -> list | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_file = APP_DATA_DIR / "cache" / "scene_detect" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _scene_cache_put(source_path: str, scenes: list) -> None:
    try:
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_dir = APP_DATA_DIR / "cache" / "scene_detect"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(cache_dir / f"{key}.json", json.dumps(scenes))
    except Exception:
        pass


def _transcription_cache_get(source_path: str, model_name: str, cache_suffix: str) -> Path | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_file = APP_DATA_DIR / "cache" / "transcription" / f"{key}.srt"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return cache_file
    except Exception:
        return None


def _transcription_cache_put(source_path: str, model_name: str, cache_suffix: str, srt_path: Path) -> None:
    try:
        if not srt_path.exists() or srt_path.stat().st_size == 0:
            return
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_dir = APP_DATA_DIR / "cache" / "transcription"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_copy2(srt_path, cache_dir / f"{key}.srt")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sprint 7.3 — Content-addressable ASS cache.
#
# Eliminates per-part srt_to_ass_* re-runs on re-renders of identical
# source+style. Cache key is SHA-256 of the 13 inputs that affect the ASS
# body (SRT bytes + writer choice + style + scale_y + font + size + margin +
# play_res + x_percent + highlight_per_word + colors + outline). Hash inputs
# (not outputs) so a cache hit skips both the generation cost (5-20 ms) and
# the write cost.
#
# Helpers are best-effort: any error → return None / silent no-op. Sacred
# Contract #3 spirit — the render pipeline never sees an exception from
# this layer, falls through to the existing generation path.
#
# Source: docs/review/SPRINT_PLAN_2026-06-05.md Sprint 7.3 row.
# ---------------------------------------------------------------------------


def _ass_cache_key(
    *,
    srt_path: Path,
    writer: str,
    style: str,
    scale_y: int,
    font_name: str,
    font_size: int,
    margin_v: int,
    play_res_y: int,
    play_res_x: int,
    x_percent: float,
    highlight_per_word: bool,
    base_color: str = "",
    highlight_color: str = "",
    outline_size: int = 0,
) -> str | None:
    """Compute SHA-256 cache key from the 13 inputs that determine ASS body.

    Returns None on any error (caller treats None as "cache disabled,
    fall through to generation"). The SRT bytes hash is the slowest step
    but cheaper than the 5-20 ms srt_to_ass_* call this enables skipping.

    SHA-256 (not MD5 like _render_cache_key) — content cache where the
    file IS the cache value, deliberately stronger.
    """
    try:
        if not srt_path.exists():
            return None
        srt_bytes = srt_path.read_bytes()
        srt_sha = hashlib.sha256(srt_bytes).hexdigest()
        key_str = "|".join((
            writer,
            srt_sha,
            style,
            str(scale_y),
            font_name,
            str(font_size),
            str(margin_v),
            str(play_res_y),
            str(play_res_x),
            str(x_percent),
            str(highlight_per_word),
            base_color,
            highlight_color,
            str(outline_size),
        ))
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    except Exception:
        return None


def _ass_cache_get(key: str) -> Path | None:
    """Return cached .ass path if exists + within TTL; lazy-unlink on stale."""
    try:
        cache_file = APP_DATA_DIR / "cache" / "ass" / f"{key}.ass"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return cache_file
    except Exception:
        return None


def _ass_cache_put(key: str, src_path: Path) -> None:
    """Atomic ``shutil.copy2`` src_path → cache/ass/{key}.ass.

    Audit BR14: the copy is staged through a ``.tmp`` sidecar and renamed
    with ``os.replace`` so the periodic prune can never observe a
    half-written cache entry. Silent on any error.
    """
    try:
        if not src_path.exists() or src_path.stat().st_size == 0:
            return
        cache_dir = APP_DATA_DIR / "cache" / "ass"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_copy2(src_path, cache_dir / f"{key}.ass")
    except Exception:
        pass


def _score_cache_get(key: str) -> list | None:
    try:
        cache_file = APP_DATA_DIR / "cache" / "segment_scores" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _score_cache_put(key: str, scored: list) -> None:
    try:
        cache_dir = APP_DATA_DIR / "cache" / "segment_scores"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(cache_dir / f"{key}.json", json.dumps(scored))
    except Exception:
        pass
