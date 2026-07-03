"""Regression guard for the motion-crop stderr-drain fix (2026-07-03).

The motion-aware crop encode wrote rawvideo frames to ffmpeg's stdin in a tight
loop while ffmpeg wrote to stderr, but `stderr=subprocess.PIPE` was never drained
during the loop. Once ffmpeg's ~64 KB stderr buffer filled, ffmpeg blocked on the
stderr write, stopped reading stdin, and our `stdin.write()` blocked in turn — a
mutual deadlock that froze the render indefinitely with the ffmpeg error trapped,
unread, in the pipe (zero diagnostics). The fix drains stderr in a daemon thread
(`_drain_pipe`). These tests pin that: (1) it captures the full stderr, and
(2) it prevents the stdin/stderr deadlock with a faithful single-threaded child.
"""
from __future__ import annotations

import subprocess
import sys
import threading

from app.features.render.engine.motion.crop import _drain_pipe


def test_drain_pipe_captures_full_stderr():
    code = "import sys; sys.stderr.buffer.write(b'E'*300000); sys.stderr.buffer.flush()"
    proc = subprocess.Popen([sys.executable, "-c", code], stderr=subprocess.PIPE)
    chunks: list = []
    th = threading.Thread(target=_drain_pipe, args=(proc.stderr, chunks), daemon=True)
    th.start()
    rc = proc.wait(timeout=30)
    th.join(timeout=5)
    assert rc == 0
    assert b"".join(chunks) == b"E" * 300000


def test_drain_pipe_prevents_stdin_stderr_deadlock():
    # Faithful single-threaded child (like ffmpeg): for every stdin chunk it
    # reads, it writes an equal-size stderr chunk. Without draining stderr this
    # deadlocks once the stderr pipe fills; with _drain_pipe it completes.
    code = (
        "import sys\n"
        "buf = sys.stdin.buffer\n"
        "err = sys.stderr.buffer\n"
        "while True:\n"
        "    d = buf.read(4096)\n"
        "    if not d:\n"
        "        break\n"
        "    err.write(b'x' * len(d))\n"
        "    err.flush()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    chunks: list = []
    th = threading.Thread(target=_drain_pipe, args=(proc.stderr, chunks), daemon=True)
    th.start()
    # 1 MB stdin — far exceeds the ~64 KB stderr pipe buffer, so this write would
    # block forever if stderr were not being drained concurrently.
    proc.stdin.write(b"X" * (1024 * 1024))
    proc.stdin.close()
    rc = proc.wait(timeout=30)  # must NOT hang
    th.join(timeout=5)
    assert rc == 0
    assert len(b"".join(chunks)) == 1024 * 1024  # 1:1 stderr fully captured
