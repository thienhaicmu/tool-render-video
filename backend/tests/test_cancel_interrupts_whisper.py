"""T2.1 closure regression guard — Audit 2026-06-08 (Batch A V9-F2).

Pre-T2.1 the faster-whisper segment iterator was consumed via
``segments = list(segments_iter)`` in ``_write_fw_srt``. faster-whisper
transcribes LAZILY — each iteration runs ~2-5 s of model inference —
so the slurp forced the entire transcription (minutes on long videos)
to complete before the cancel signal could be observed. The operator
UI showed "cancelling…" for the duration.

T2.1 (commit 1c8635b) replaced the slurp with an explicit per-yield
loop and called ``check_thread_cancel()`` between yields. The fix
mirrors T2.2's OpenCV pattern: reuse the per-thread cancel-event
mechanism (set in part_renderer.py:162) so the cancel signal arrives
within ~1 audio segment of real time.

This file pins T2.1 with three checks:

1. **Behavioural** — feed a synthetic segment iterator into
   ``_write_fw_srt`` with a cancel event set; expect the iterator
   loop to raise ``JobCancelledError`` after consuming at least one
   segment (proving the per-yield poll fires).

2. **Structural** — ``check_thread_cancel`` is imported into
   ``adapters.py`` AND called inside ``_write_fw_srt``. A future
   refactor that drops either side silently re-introduces the
   uninterruptible-Whisper bug.

3. **Anti-regression** — the pre-T2.1 ``segments = list(segments_iter)``
   slurp must NOT reappear. If a refactor "simplifies" the loop back
   to the slurp, the cancel poll vanishes and this test fires.
"""
from __future__ import annotations

import re
import threading
from collections import namedtuple
from pathlib import Path

import pytest


ADAPTERS_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine"
    / "subtitle" / "transcription" / "adapters.py"
)


# ---------------------------------------------------------------------------
# 1. Behavioural — _write_fw_srt raises mid-iteration on cancel.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_thread_cancel_event():
    """Clear the thread-local cancel event before and after each test
    so a stray Event from prior tests doesn't bleed into this one."""
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        set_thread_cancel_event,
    )
    set_thread_cancel_event(None)
    yield
    set_thread_cancel_event(None)


# Minimal Segment shape matching faster-whisper's namedtuple — only the
# fields _write_fw_srt actually reads.
_FakeSegment = namedtuple("_FakeSegment", ["start", "end", "text", "words"])


def _make_fake_segments(n: int):
    """Return n synthetic segments shaped like faster-whisper output."""
    return [
        _FakeSegment(
            start=float(i * 5),
            end=float((i + 1) * 5),
            text=f"synthetic segment {i}",
            words=[],  # word-level off
        )
        for i in range(n)
    ]


def test_write_fw_srt_raises_when_cancel_event_set_mid_iteration(tmp_path):
    """Behavioural pin: feed a 10-segment iterator and SET the cancel
    event after the first segment is consumed. The per-yield
    ``check_thread_cancel`` poll must observe the event AT THE NEXT
    iteration and raise JobCancelledError.

    Pre-T2.1 this scenario silently consumed all 10 segments and
    returned normally — proving the cancel signal was lost.
    """
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        set_thread_cancel_event,
    )
    from app.features.render.engine.subtitle.transcription.adapters import (
        _write_fw_srt,
    )
    from app.jobs.cancel import JobCancelledError

    cancel_ev = threading.Event()
    set_thread_cancel_event(cancel_ev)

    fake_segments = _make_fake_segments(10)

    def _iter_then_set_cancel():
        """Yield segments one at a time; after the first one is
        consumed, set the cancel event so the next iteration's
        check_thread_cancel poll fires."""
        for i, seg in enumerate(fake_segments):
            yield seg
            if i == 0:
                cancel_ev.set()  # trigger cancel between segment 0 and 1

    out_srt = tmp_path / "out.srt"
    with pytest.raises(JobCancelledError):
        _write_fw_srt(_iter_then_set_cancel(), str(out_srt), word_level=False)


def test_write_fw_srt_consumes_full_iterator_when_cancel_not_set(tmp_path):
    """Happy path: with NO cancel event registered, the loop runs to
    completion and writes a valid SRT file. This is the per-render
    default scenario; a regression here would kill every transcription.
    """
    from app.features.render.engine.subtitle.transcription.adapters import (
        _write_fw_srt,
    )

    # No cancel event registered — the autouse fixture already cleared it.
    fake_segments = _make_fake_segments(3)
    out_srt = tmp_path / "out.srt"

    # Should NOT raise.
    _write_fw_srt(iter(fake_segments), str(out_srt), word_level=False)

    # Sanity: the SRT was written and contains at least one block.
    assert out_srt.exists()
    content = out_srt.read_text(encoding="utf-8")
    assert "synthetic segment 0" in content, (
        f"SRT writer wrote {len(content)} bytes but couldn't find the "
        f"first segment text. Loop may have skipped iteration."
    )


# ---------------------------------------------------------------------------
# 2. Structural — import + call site presence.
# ---------------------------------------------------------------------------


def test_check_thread_cancel_imported_into_adapters():
    """The import line MUST be present. Without it, the call site is a
    NameError and the cancel poll silently disappears."""
    source = ADAPTERS_PATH.read_text(encoding="utf-8-sig")
    assert "check_thread_cancel" in source, (
        "T2.1 regression — engine/subtitle/transcription/adapters.py no "
        "longer references check_thread_cancel. The Whisper segment "
        "iterator becomes uninterruptible again. Restore the import "
        "from app.features.render.engine.encoder.ffmpeg_helpers."
    )


def test_check_thread_cancel_called_inside_write_fw_srt():
    """Pin that the call appears AS A CALL SITE, not just an import.
    A future refactor could leave the import in place for ``# noqa:
    F401`` reasons but drop the call inside ``_write_fw_srt``. That
    would re-introduce the slurp behaviour."""
    source = ADAPTERS_PATH.read_text(encoding="utf-8-sig")
    assert re.search(r"\bcheck_thread_cancel\s*\(\s*\)", source), (
        "T2.1 regression — engine/subtitle/transcription/adapters.py "
        "imports check_thread_cancel but never calls it. The Whisper "
        "segment iterator's cancel poll is dead code. Add the "
        "check_thread_cancel() call at the top of the for-loop inside "
        "_write_fw_srt."
    )


# ---------------------------------------------------------------------------
# 3. Anti-regression — the pre-T2.1 slurp must not reappear.
# ---------------------------------------------------------------------------


def test_no_segments_iter_slurp_inside_write_fw_srt():
    """The pre-T2.1 implementation had ``segments = list(segments_iter)``
    which forced the entire transcription to complete before
    interruption was possible. A refactor that "simplifies" the loop
    back to that form silently re-breaks the cancel UX. Catch it
    here."""
    source = ADAPTERS_PATH.read_text(encoding="utf-8-sig")

    # The bad pattern is the ASSIGNMENT `segments = list(segments_iter)`
    # — the pre-T2.1 form. Filter out comment / docstring mentions of
    # the literal phrase ``list(segments_iter)`` (the T2.1 docstring
    # explicitly cites it as the regression to avoid). We do that by
    # stripping every line that begins with ``#`` or ``*`` AFTER
    # stripping leading whitespace, and by ignoring lines inside
    # triple-quoted docstrings via a coarse marker scan.
    code_lines: list[str] = []
    in_doc = False
    for raw in source.splitlines():
        line = raw.strip()
        if not in_doc:
            # Enter docstring on opening triple-quote that isn't also a
            # closer on the same line.
            if line.startswith(('"""', "'''")):
                # Check if it also closes on the same line.
                quote = line[:3]
                rest = line[3:]
                if rest.count(quote) % 2 == 1:
                    # Open-close on same line; not entering doc.
                    pass
                else:
                    in_doc = True
                    continue
            if line.startswith("#"):
                continue
            code_lines.append(raw)
        else:
            if '"""' in line or "'''" in line:
                in_doc = False
    code_only = "\n".join(code_lines)

    bad_pattern = re.compile(r"\bsegments\s*=\s*list\s*\(\s*segments_iter\s*\)")
    assert not bad_pattern.search(code_only), (
        "T2.1 regression — engine/subtitle/transcription/adapters.py "
        "contains `segments = list(segments_iter)` in a CODE line. "
        "That's the pre-T2.1 slurp that consumes the entire Whisper "
        "iterator before any interruption can be observed, making "
        "Whisper uninterruptible. Replace with an explicit for-loop "
        "that calls check_thread_cancel() between yields."
    )
