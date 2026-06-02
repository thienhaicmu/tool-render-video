"""test_render_events_dirs.py — Sprint 4.3.

Verifies the locked register/unregister helpers around _JOB_LOG_DIRS
behave correctly under single-thread and concurrent access. The lock
protects mutations from interleaving on alternative interpreters where
single-key dict ops are not guaranteed atomic.

Audit reference: docs/review/AUDIT_2026-06-02.md P2-B3.
"""
from __future__ import annotations

import threading
from pathlib import Path

from app.orchestration.render_events import (
    _JOB_LOG_DIRS,
    register_job_log_dir,
    unregister_job_log_dir,
)


class TestRegisterUnregister:
    def test_register_then_lookup(self):
        register_job_log_dir("job-test-a", Path("/tmp/a"))
        try:
            assert _JOB_LOG_DIRS.get("job-test-a") == Path("/tmp/a")
        finally:
            unregister_job_log_dir("job-test-a")

    def test_unregister_removes_entry(self):
        register_job_log_dir("job-test-b", Path("/tmp/b"))
        unregister_job_log_dir("job-test-b")
        assert "job-test-b" not in _JOB_LOG_DIRS

    def test_unregister_unknown_is_noop(self):
        unregister_job_log_dir("job-never-registered")
        # No exception expected

    def test_register_is_idempotent(self):
        register_job_log_dir("job-test-c", Path("/tmp/c1"))
        register_job_log_dir("job-test-c", Path("/tmp/c2"))
        try:
            assert _JOB_LOG_DIRS["job-test-c"] == Path("/tmp/c2")
        finally:
            unregister_job_log_dir("job-test-c")


class TestConcurrentAccess:
    def test_no_exception_under_contention(self):
        """Stress: many threads register+unregister simultaneously.

        The lock must serialize mutations so no KeyError or RuntimeError
        escapes from concurrent operations.
        """
        errors: list[BaseException] = []

        def worker(i: int):
            try:
                key = f"job-stress-{i}"
                for _ in range(50):
                    register_job_log_dir(key, Path(f"/tmp/{key}"))
                    unregister_job_log_dir(key)
            except BaseException as exc:  # noqa: BLE001 — collect any failure
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All threads should drain. The stress keys should all be removed at end.
        leftover_stress = [k for k in _JOB_LOG_DIRS if k.startswith("job-stress-")]
        assert not errors, f"Concurrent worker raised: {errors[0]!r}"
        assert leftover_stress == [], f"Leaked entries: {leftover_stress}"
