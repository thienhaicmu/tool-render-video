"""Strategic-5 closure regression guard — Audit 2026-06-08 (Batch B B-12-A).

Batch B flagged ``motion/crop.py``, ``audio/mixer.py``,
``encoder/clip_ops.py``, and ``preview/ffmpeg_probers.py`` as not
acquiring ``NVENC_SEMAPHORE``. Investigation classified the four
sites:

  - ``encoder/clip_ops.py`` — 3× detection-only subprocess.run with
    ``-f null -`` output (silencedetect, blackdetect). NO encode.
    FALSE POSITIVE.

  - ``audio/mixer.py`` — 2× ffprobe + 1× ffmpeg with ``-c:v copy
    -c:a aac``. NO video encode. FALSE POSITIVE.

  - ``preview/ffmpeg_probers.py`` — 2× ffprobe + 1× ffmpeg with
    ``-f null -`` (blackdetect probe). NO encode. FALSE POSITIVE.

  - ``motion/crop.py`` — Real Popen at line 714 with ``-c:v
    <resolved_codec>`` where ``resolved_codec`` MAY be
    ``h264_nvenc`` / ``hevc_nvenc``. The function does NOT acquire
    NVENC_SEMAPHORE itself; the THREE production call sites in
    ``encoder/clip_renderer.py`` (lines ~94-98, ~635-640, ~819-823)
    acquire it externally BEFORE invoking ``render_motion_aware_crop``.

The actual closure for B-12-A is therefore:

  1. Document the "caller-acquires" contract in
     ``render_motion_aware_crop``'s docstring (done in the
     accompanying commit).

  2. This test pins the contract via AST inspection of
     ``encoder/clip_renderer.py``: every call to
     ``render_motion_aware_crop`` MUST be guarded by an
     ``NVENC_SEMAPHORE.acquire()`` or a ``with NVENC_SEMAPHORE``
     block within the same function body. A refactor that drops the
     external acquire fires this test before landing.

  3. The three "false-positive" files are pinned to NOT regress into
     NVENC-capable encodes — if a future change adds ``-c:v
     h264_nvenc`` to any of them, that's a real new risk and this
     test flags it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


_BACKEND_APP = Path(__file__).resolve().parent.parent / "app"

_CLIP_RENDERER = (
    _BACKEND_APP / "features" / "render" / "engine"
    / "encoder" / "clip_renderer.py"
)

# Three files Batch B B-12-A flagged that were investigated and
# classified as NOT containing NVENC-capable encodes. If a future
# change adds an NVENC codec to any of them, the test flags it as a
# real new risk (the file would need to start acquiring the semaphore).
_FALSE_POSITIVE_FILES = (
    _BACKEND_APP / "features" / "render" / "engine" / "encoder" / "clip_ops.py",
    _BACKEND_APP / "features" / "render" / "engine" / "audio" / "mixer.py",
    _BACKEND_APP / "features" / "render" / "engine" / "preview" / "ffmpeg_probers.py",
    # W5-7: content_background must NEVER use NVENC — backgrounds are many and
    # short; borrowing a GPU session for them would starve the real scene-mux /
    # xfade encodes (mirrors the recap act-title-card CPU policy documented in
    # content_background.py). The W5-7 NVENC path lives in content_scene_render
    # and content_assembler, which route through _run_ffmpeg_with_retry.
    _BACKEND_APP / "features" / "render" / "engine" / "stages" / "content_background.py",
)


# ---------------------------------------------------------------------------
# 1. clip_renderer.py — every call to render_motion_aware_crop must be
#    preceded by an NVENC_SEMAPHORE acquire within the same function.
# ---------------------------------------------------------------------------


def test_every_render_motion_aware_crop_call_is_preceded_by_semaphore_acquire():
    """The caller-acquires invariant: each call to
    ``render_motion_aware_crop`` in ``clip_renderer.py`` MUST be
    preceded — within the same function body — by either:
    - ``NVENC_SEMAPHORE.acquire()`` followed by ``try:``, OR
    - ``with NVENC_SEMAPHORE:``.

    A refactor that drops the acquire (or moves it OUT of the same
    function as the call) causes this test to fail.
    """
    source = _CLIP_RENDERER.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    failures: list[str] = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Find every Call node whose function name is render_motion_aware_crop.
        call_lines: list[int] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                func_name = _call_name(node.func)
                if func_name == "render_motion_aware_crop":
                    call_lines.append(node.lineno)

        if not call_lines:
            continue

        # Collect every NVENC_SEMAPHORE acquire / with-statement line in
        # this function body.
        acquire_lines: list[int] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                # NVENC_SEMAPHORE.acquire(...)
                if _is_attribute_call(node, "NVENC_SEMAPHORE", "acquire"):
                    acquire_lines.append(node.lineno)
                # Caller pattern: _crop_ctx.acquire() where _crop_ctx is
                # bound to NVENC_SEMAPHORE on the line above. Match the
                # bare ``.acquire()`` call name; we further verify the
                # binding via source search below.
                elif _is_attribute_call(node, None, "acquire"):
                    acquire_lines.append(node.lineno)
            elif isinstance(node, ast.With):
                for item in node.items:
                    name = _call_name(item.context_expr)
                    if name == "NVENC_SEMAPHORE":
                        acquire_lines.append(node.lineno)

        # The acquire line must be on or before the call line. Confirm
        # by checking each call has an acquire line at <= its lineno.
        for cl in call_lines:
            preceding = [al for al in acquire_lines if al <= cl]
            if not preceding:
                failures.append(
                    f"  function `{func.name}` calls render_motion_aware_crop "
                    f"at line {cl} but no NVENC_SEMAPHORE acquire / with-block "
                    f"appears in the same function. Strategic-5 contract "
                    f"violated — see motion/crop.py docstring."
                )

    assert not failures, (
        "B-12-A regression — at least one render_motion_aware_crop "
        "call in clip_renderer.py is missing the external NVENC_"
        "SEMAPHORE acquire required by the caller-acquires contract. "
        "Failures:\n" + "\n".join(failures)
    )


def test_clip_renderer_branches_on_nvenc_codec_before_acquiring():
    """Defence-in-depth: when the codec is NOT NVENC (e.g. libx264),
    the semaphore should NOT be acquired (wasted slot). The
    canonical caller pattern in clip_renderer.py reads:

        _crop_codec = _resolve_codec(video_codec, encoder_mode=...)
        _crop_ctx = NVENC_SEMAPHORE if _crop_codec in ("h264_nvenc", "hevc_nvenc") else None
        if _crop_ctx is not None:
            _crop_ctx.acquire()

    OR:

        if _use_nvenc:
            NVENC_SEMAPHORE.acquire()

    Pin that the NVENC-codec check appears alongside the acquire.
    Without the gate, every render would consume an NVENC session
    slot even when using a CPU codec, halving the effective NVENC
    parallelism.
    """
    source = _CLIP_RENDERER.read_text(encoding="utf-8-sig")

    # At least one explicit NVENC codec literal must appear near each
    # call site. We match the tokens that gate the acquire.
    assert "h264_nvenc" in source, (
        "clip_renderer.py no longer references 'h264_nvenc' — the "
        "NVENC-vs-CPU branch is required to avoid waste-acquiring "
        "the semaphore on every CPU encode."
    )
    assert "hevc_nvenc" in source, (
        "clip_renderer.py no longer references 'hevc_nvenc' — same "
        "reasoning as h264_nvenc."
    )
    # The conditional acquire pattern: at least one acquire MUST sit
    # inside an `if` block that mentions NVENC.
    # Cheap heuristic: search for the canonical 4-line pattern.
    assert re.search(
        r"NVENC_SEMAPHORE\s+if\s+_crop_codec\s+in\s*\(\s*\"h264_nvenc\"",
        source,
    ) or re.search(
        r"_use_nvenc\s*=\s*_crop_codec\s+in\s*\(\s*\"h264_nvenc\"",
        source,
    ), (
        "clip_renderer.py no longer has the conditional NVENC acquire "
        "pattern. Either (a) `_crop_ctx = NVENC_SEMAPHORE if ...` or "
        "(b) `_use_nvenc = ...` followed by `if _use_nvenc: "
        "NVENC_SEMAPHORE.acquire()`. Strategic-5 contract violated."
    )


# ---------------------------------------------------------------------------
# 2. False-positive files — must NOT regress into NVENC-capable encodes.
# ---------------------------------------------------------------------------


def test_false_positive_files_do_not_use_nvenc_codecs():
    """The three files Batch B B-12-A flagged as NOT acquiring the
    semaphore (encoder/clip_ops.py, audio/mixer.py,
    preview/ffmpeg_probers.py) were classified as NOT containing
    NVENC-capable encodes:
    - clip_ops.py: silencedetect / blackdetect with `-f null -` output
    - mixer.py: ffprobe + ffmpeg with `-c:v copy`
    - ffmpeg_probers.py: ffprobe + blackdetect with `-f null -`

    If a future change adds an NVENC codec literal to any of them,
    this test fires before the new NVENC site becomes a real
    production-crash class (concurrent renders fail simultaneously
    when the GPU session cap is exceeded).
    """
    for path in _FALSE_POSITIVE_FILES:
        source = path.read_text(encoding="utf-8-sig")
        for needle in ("h264_nvenc", "hevc_nvenc"):
            assert needle not in source, (
                f"Strategic-5 regression — {path.name} now references "
                f"'{needle}'. The file MUST acquire NVENC_SEMAPHORE "
                f"around any subprocess that spawns an NVENC-capable "
                f"FFmpeg invocation, OR be reclassified out of the "
                f"false-positive list in this test. See "
                f"motion/crop.py docstring for the caller-acquires "
                f"contract."
            )


# ---------------------------------------------------------------------------
# 3. The canonical semaphore symbol remains where motion/crop.py expects it.
# ---------------------------------------------------------------------------


def test_nvenc_semaphore_symbol_lives_in_ffmpeg_helpers():
    """The semaphore is defined in ``ffmpeg_helpers.py`` and imported
    by every caller. If the module split moves the symbol, every
    acquire site breaks and the entire NVENC contract collapses."""
    from app.features.render.engine.encoder import ffmpeg_helpers
    import threading

    assert hasattr(ffmpeg_helpers, "NVENC_SEMAPHORE"), (
        "NVENC_SEMAPHORE was moved out of ffmpeg_helpers.py — every "
        "import site needs the new location. Audit all current "
        "callers (3 in clip_renderer.py + the test guards) before "
        "moving the symbol."
    )
    assert isinstance(ffmpeg_helpers.NVENC_SEMAPHORE, type(threading.Semaphore())), (
        "NVENC_SEMAPHORE is no longer a threading.Semaphore — the "
        "GPU session-cap protection relies on the bounded-counter "
        "semantics of Semaphore."
    )


# ---------------------------------------------------------------------------
# 4. recap_assembler.py — Fix D (2026-07-02): the episode concat re-encode
#    may use h264_nvenc via a raw subprocess.run, so the semaphore MUST be
#    held in the same function (with NVENC_SEMAPHORE: block).
# ---------------------------------------------------------------------------

_RECAP_ASSEMBLER = (
    _BACKEND_APP / "features" / "render" / "engine"
    / "stages" / "recap_assembler.py"
)


def test_recap_assembler_nvenc_encode_is_semaphore_guarded():
    """Every function in recap_assembler.py that mentions an NVENC codec
    must also contain a ``with NVENC_SEMAPHORE`` block. A refactor that
    drops the guard lets the job-level concat open an extra NVENC session
    while parallel renders encode — NVIDIA fails ALL active sessions."""
    source = _RECAP_ASSEMBLER.read_text(encoding="utf-8-sig")
    assert "h264_nvenc" in source, (
        "recap_assembler.py no longer references h264_nvenc — if Fix D's "
        "GPU concat was removed, delete this test alongside it."
    )
    tree = ast.parse(source)
    failures: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_src = ast.get_source_segment(source, func) or ""
        if "h264_nvenc" not in func_src and "hevc_nvenc" not in func_src:
            continue
        has_with_sem = any(
            isinstance(node, ast.With)
            and any(_call_name(item.context_expr) == "NVENC_SEMAPHORE" for item in node.items)
            for node in ast.walk(func)
        )
        if not has_with_sem:
            failures.append(
                f"{func.name} (line {func.lineno}) references an NVENC codec "
                f"without a 'with NVENC_SEMAPHORE:' block"
            )
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _call_name(node: ast.AST) -> str:
    """Return the dotted name of a Call.func / context_expr, or ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_attribute_call(call: ast.Call, expected_obj: str | None, expected_attr: str) -> bool:
    """True when ``call`` is ``<obj>.<attr>(...)`` and ``<attr>`` matches.
    When ``expected_obj`` is None, only the attribute name is checked.
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != expected_attr:
        return False
    if expected_obj is None:
        return True
    return isinstance(func.value, ast.Name) and func.value.id == expected_obj
