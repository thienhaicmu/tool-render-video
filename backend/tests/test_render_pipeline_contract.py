"""Contract tests for render_pipeline.py (audit FINDING-TEST02).

run_render_pipeline is the 1,357-LOC orchestrator that owns the per-job
state machine. A full integration test would require mocking 15+ heavy
dependencies (FFmpeg, Whisper, LLM, motion-crop, motion path cache,
DB writes, WS emission, audio mixer …) — not practical at this scope.

Instead, this file pins the orchestrator's **static contracts** via AST
traversal: properties of the source code that a regression would silently
break. The contracts checked:

1. Every `update_job_progress(...)` call in render_pipeline.py uses a
   stage value from JobStage — never a raw string literal that could
   typo into silent corruption.
2. Every `_emit_render_event(...)` call uses keyword-only invocation
   (Sacred Contract #6 — the signature is frozen and positional args
   would break consumers).
3. The 4 active feature flags in render_pipeline.py read env vars and
   coerce to bool exactly. Default values match the audit documentation.
4. STAGE_TO_EVENT (in core/stage.py) covers every JobStage member that
   could realistically appear as a stage value in render_pipeline — a
   miss here means `_event_from_stage` falls through to a default.
5. process_render (in routers/_common.py) correctly marks
   JobStage.CANCELLED on the cancel path. This is the WS / DB visible
   half of the cancel contract.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterator

import pytest

from app.core import stage as stage_module
from app.core.stage import JobPartStage, JobStage


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_PATH = (
    _BACKEND_DIR
    / "app" / "features" / "render" / "engine" / "pipeline" / "render_pipeline.py"
)


def _pipeline_tree() -> ast.Module:
    # render_pipeline.py was saved with a BOM (U+FEFF) on Windows; utf-8-sig
    # strips it transparently so ast.parse doesn't choke.
    return ast.parse(_PIPELINE_PATH.read_text(encoding="utf-8-sig"))


def _calls(tree: ast.AST) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


# ---------------------------------------------------------------------------
# 1. update_job_progress — stage values must be JobStage members
# ---------------------------------------------------------------------------

# Whitelist of literal stage strings that are intentionally raw (only set
# from router-level finally blocks, where importing JobStage would be a
# circular dependency). Empty for render_pipeline.py — all calls in the
# orchestrator should use the enum.
_RAW_STAGE_WHITELIST: set[str] = set()


def _arg_value(arg: ast.AST) -> str | None:
    """Return the literal string value of an arg if it is a Constant string."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _is_jobstage_reference(arg: ast.AST) -> bool:
    """True when the arg is JobStage.SOMETHING (attribute access on JobStage)."""
    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
        return arg.value.id in {"JobStage", "JobPartStage"}
    return False


def test_update_job_progress_calls_use_jobstage_enum():
    """Every update_job_progress(job_id, <stage>, ...) call in the
    orchestrator must pass a JobStage enum member as the stage arg, not
    a raw string literal. A typo in a raw string silently corrupts the
    state machine (Phase 4 finding BR05/C06 enforces it at write time —
    this test stops the typo from being written in the first place).
    """
    tree = _pipeline_tree()
    violations: list[tuple[int, str]] = []

    for call in _calls(tree):
        if _callee_name(call) != "update_job_progress":
            continue
        # Positional arg 1 (after job_id at index 0) is the stage.
        if len(call.args) < 2:
            continue
        stage_arg = call.args[1]
        if _is_jobstage_reference(stage_arg):
            continue
        literal = _arg_value(stage_arg)
        if literal is not None and literal in _RAW_STAGE_WHITELIST:
            continue
        if literal is not None:
            violations.append((call.lineno, literal))

    assert not violations, (
        "update_job_progress called with raw stage string(s) in "
        f"render_pipeline.py:\n  " +
        "\n  ".join(f"line {ln}: {repr(s)}" for ln, s in violations)
    )


# ---------------------------------------------------------------------------
# 2. _emit_render_event — keyword-only invocation (Sacred Contract #6)
# ---------------------------------------------------------------------------

def test_emit_render_event_uses_keyword_only_calls():
    """Sacred Contract #6 freezes the signature of _emit_render_event as
    keyword-only. Any positional call here would be a contract violation
    and almost certainly a regression.
    """
    tree = _pipeline_tree()
    positional_calls: list[tuple[int, int]] = []

    for call in _calls(tree):
        if _callee_name(call) != "_emit_render_event":
            continue
        # No positional args allowed — every value must be a keyword.
        if call.args:
            positional_calls.append((call.lineno, len(call.args)))

    assert not positional_calls, (
        "_emit_render_event called with positional arg(s) in render_pipeline.py: "
        f"{positional_calls}"
    )


# ---------------------------------------------------------------------------
# 3. Feature flag defaults — bool, OFF / ON per audit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("env_var", "expected_default_on"),
    [
        ("LLM_EMIT_RENDER_PLAN",             True),
    ],
)
def test_feature_flag_default(env_var: str, expected_default_on: bool, monkeypatch):
    """Pin the LLM_EMIT_RENDER_PLAN flag default state.

    Sprint 7.6a (2026-06-05) flipped LLM_EMIT_RENDER_PLAN from OFF → ON.

    Re-imports render_pipeline with the env unset to capture the default.
    """
    import importlib
    monkeypatch.delenv(env_var, raising=False)
    rp = importlib.reload(
        importlib.import_module(
            "app.features.render.engine.pipeline.render_pipeline"
        )
    )
    # The flag attribute names in render_pipeline:
    name_map = {
        "LLM_EMIT_RENDER_PLAN":              "_FEATURE_LLM_EMIT_RENDER_PLAN",
    }
    attr = name_map[env_var]
    actual = getattr(rp, attr)
    assert isinstance(actual, bool), f"{attr} is not a bool: {type(actual).__name__}"
    assert actual is expected_default_on, (
        f"{env_var} default = {actual}, expected {expected_default_on}. "
        f"Sacred Contract #2 — feature flags must default OFF unless the "
        f"audit + sprint plan explicitly authorise a flip (e.g. Sprint 7.6a "
        f"for LLM_EMIT_RENDER_PLAN)."
    )


# ---------------------------------------------------------------------------
# 4. STAGE_TO_EVENT — every JobStage member maps to an event name
# ---------------------------------------------------------------------------

def test_stage_to_event_covers_every_jobstage():
    """STAGE_TO_EVENT is consulted by _event_from_stage to attach a
    structured event name to every WS frame. A missing entry means the FE
    sees a generic event for that stage transition — confusing the
    Phase 6 / FE consumers.
    """
    mapping = stage_module.STAGE_TO_EVENT
    missing = [s.value for s in JobStage if s not in mapping]
    # CANCELLED is the documented exception — it is set from router-level
    # finally, not from inside the orchestrator. Allow it.
    missing = [s for s in missing if s != JobStage.CANCELLED.value]
    assert not missing, (
        f"STAGE_TO_EVENT missing entries for: {missing}. "
        f"Add them in app/core/stage.py."
    )


def test_stage_to_event_all_values_are_render_dot_names():
    """Pin the convention: every event name is dot-separated and starts
    with 'render.'. The FE WS handler routes on this prefix.
    """
    for stage, event in stage_module.STAGE_TO_EVENT.items():
        assert isinstance(event, str), f"{stage} maps to non-string event {event!r}"
        assert event.startswith("render."), (
            f"event {event!r} for stage {stage} does not start with 'render.' — "
            f"breaks FE event-routing convention."
        )


# ---------------------------------------------------------------------------
# 5. process_render cancel-path marks JobStage.CANCELLED
# ---------------------------------------------------------------------------

def test_process_render_cancel_path_marks_cancelled(monkeypatch):
    """When the cancel registry fires JobCancelledError, process_render
    must call update_job_progress with JobStage.CANCELLED so the FE WS
    polling loop sees the terminal status. A regression here strands
    cancelled jobs in 'running' state.
    """
    from app.features.render.routers import _common as common

    progress_writes: list[tuple] = []

    def _capture_progress(*args, **kwargs):
        progress_writes.append((args, kwargs))

    # Stub the dependency chain. We DO NOT want a real pipeline run.
    class _CancelReg:
        class JobCancelledError(Exception):
            pass

        @staticmethod
        def register(job_id):
            ev = type("E", (), {"is_set": lambda self: False})()
            return ev

        @staticmethod
        def unregister(job_id):
            return None

    import app.jobs.cancel as cancel_real
    monkeypatch.setattr(cancel_real, "register", _CancelReg.register)
    monkeypatch.setattr(cancel_real, "unregister", _CancelReg.unregister)
    monkeypatch.setattr(cancel_real, "JobCancelledError", _CancelReg.JobCancelledError)

    def _fake_run_pipeline(**kw):
        # Simulate the cancel firing mid-render.
        raise _CancelReg.JobCancelledError()

    monkeypatch.setattr(common, "run_render_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(common, "update_job_progress", _capture_progress)

    # Run — must NOT propagate.
    common.process_render(
        "job-cancel-test",
        payload=type("P", (), {})(),  # dummy payload — _fake_run_pipeline ignores it
        resume_mode=False,
    )

    # Find the cancellation write.
    cancel_calls = [
        (args, kwargs) for args, kwargs in progress_writes
        if any(arg == JobStage.CANCELLED for arg in args) or
           kwargs.get("status") == JobStage.CANCELLED
    ]
    assert cancel_calls, (
        "process_render did not call update_job_progress with "
        "JobStage.CANCELLED after JobCancelledError. The FE WS loop would "
        "never see a terminal status."
    )


# ---------------------------------------------------------------------------
# 6. Feature flag reads via os.getenv — never via os.environ[…] (KeyError)
# ---------------------------------------------------------------------------

def test_feature_flag_reads_never_use_subscript_environ():
    """A `os.environ["FEATURE_X"]` read would raise KeyError at import
    time when the env var is missing. Always use os.getenv(...) so a
    missing env behaves as OFF.
    """
    tree = _pipeline_tree()
    bad: list[int] = []

    for node in ast.walk(tree):
        # Look for os.environ[<key>] subscripts at module-level reads.
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "os"
            and value.attr == "environ"
        ):
            bad.append(node.lineno)

    assert not bad, (
        "render_pipeline.py uses os.environ[...] subscript (line "
        f"{bad}). Use os.getenv(...) so a missing env var defaults to None."
    )


# ---------------------------------------------------------------------------
# 7. LLM_EMIT_RENDER_PLAN=0 — flag resolves to False when explicitly disabled
# ---------------------------------------------------------------------------

def test_llm_emit_render_plan_flag_off_when_zero(monkeypatch):
    """When LLM_EMIT_RENDER_PLAN=0 is set, _FEATURE_LLM_EMIT_RENDER_PLAN must
    be False. Verifies the explicit opt-out path, complementing the default=1
    test above which covers the absence case.
    """
    import importlib
    monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "0")
    rp = importlib.reload(
        importlib.import_module(
            "app.features.render.engine.pipeline.render_pipeline"
        )
    )
    assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is False
