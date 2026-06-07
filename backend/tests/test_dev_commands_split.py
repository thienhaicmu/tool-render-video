"""Audit MT-1 closure (Batch 10J 2026-06-06).

The 1542-LOC ``app.services.dev_commands`` monolith was split into the
``app.services.dev`` package (6 sub-modules + a router + a ``__init__``).
``app.services.dev_commands`` is now a re-export shim so the existing
route consumer in ``app.routes.devtools`` keeps working unchanged.

This file is the regression guard. The behavior tests cover the
dispatcher contract (unknown commands raise, every documented prefix
routes to the correct handler) so a future re-organisation can't
silently break the route surface that ``run_dev_command`` depends on.

Heavy commands (``/log``, ``/error``, ``/fix``) are mocked at the
handler boundary — we're testing the WIRING (dispatcher → handler),
not the handler bodies (those are exercised by their own behavior at
runtime against real logs).
"""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shim identity + module presence
# ---------------------------------------------------------------------------


def test_shim_re_exports_canonical_function():
    """``app.services.dev_commands.execute_dev_command`` must BE the same
    object as ``app.services.dev.execute_dev_command``. A separate
    definition would mean the dispatcher diverged."""
    from app.services.dev_commands import execute_dev_command as legacy
    from app.services.dev import execute_dev_command as canonical

    assert legacy is canonical


def test_sub_modules_importable():
    """Every sub-module must load cleanly — catches typos in cross-module
    imports + the bug↔autofix lazy-import dance."""
    for name in (
        "app.services.dev._shared",
        "app.services.dev.log",
        "app.services.dev.bug",
        "app.services.dev.registry",
        "app.services.dev.autofix",
        "app.services.dev.router",
    ):
        importlib.import_module(name)


def test_known_bug_classes_constant_preserved():
    """``_KNOWN_BUG_CLASSES`` moved from dev_commands.py to dev.bug.
    The set MUST be identical — fixture for autofix patch decisions."""
    from app.services.dev.bug import _KNOWN_BUG_CLASSES

    assert _KNOWN_BUG_CLASSES == {
        "filesystem/render_path",
        "download_format_fallback",
        "upload_selector_wait",
        "login_state",
        "profile_runtime",
        "proxy_runtime",
        "generic",
    }


# ---------------------------------------------------------------------------
# Dispatcher contract
# ---------------------------------------------------------------------------


def test_empty_command_raises_value_error():
    from app.services.dev import execute_dev_command
    with pytest.raises(ValueError, match="command is required"):
        execute_dev_command("")
    with pytest.raises(ValueError, match="command is required"):
        execute_dev_command("   ")


def test_unsupported_command_raises_value_error():
    from app.services.dev import execute_dev_command
    with pytest.raises(ValueError, match="Unsupported command"):
        execute_dev_command("/banana")


@pytest.mark.parametrize(
    "prefix,handler_path",
    [
        ("/log",      "app.services.dev.router._cmd_log"),
        ("/error",    "app.services.dev.router._cmd_error"),
        ("/fix",      "app.services.dev.router._cmd_fix"),
        ("/run",      "app.services.dev.router._cmd_run"),
        ("/test",     "app.services.dev.router._cmd_test"),
        ("/commit",   "app.services.dev.router._cmd_commit"),
        ("/status",   "app.services.dev.router._cmd_status"),
        ("/features", "app.services.dev.router._cmd_features"),
    ],
)
def test_dispatcher_routes_each_prefix_to_its_handler(prefix, handler_path):
    """Every documented slash command in the help string routes to the
    correct sub-module handler. The mock returns a sentinel dict so we
    don't accidentally hit real disk / git / HTTP."""
    from app.services.dev import execute_dev_command

    sentinel = {"command": prefix, "status": "mocked"}

    with patch(handler_path, return_value=sentinel) as m:
        result = execute_dev_command(f"{prefix} some args")

    assert m.called, f"{handler_path} was not invoked for {prefix}"
    assert result is sentinel


# ---------------------------------------------------------------------------
# Pure-function behavior (anchored extracted helpers)
# ---------------------------------------------------------------------------


def test_parse_status_paths_handles_renames():
    """``_parse_status_paths`` moved to router.py — exercise its 'A -> B'
    rename path so a future refactor that drops the split-on-'->' branch
    is caught."""
    from app.services.dev.router import _parse_status_paths

    raw = (
        " M src/a.py\n"
        "A  src/b.py\n"
        "R  old/c.py -> new/c.py\n"
        "?? scratch.txt\n"
    )
    paths = _parse_status_paths(raw)
    assert "src/a.py" in paths
    assert "src/b.py" in paths
    # Rename — the NEW name must be captured, not the old.
    assert "new/c.py" in paths
    assert "old/c.py" not in paths
    assert "scratch.txt" in paths


def test_filter_excluded_drops_matching_patterns(monkeypatch):
    from app.services.dev.router import _filter_excluded

    monkeypatch.setenv("DEV_COMMIT_EXCLUDE", "*.log,data/*")
    out = _filter_excluded([
        "src/a.py",
        "src/build.log",
        "data/secret.json",
        "docs/readme.md",
    ])
    assert out == ["src/a.py", "docs/readme.md"]


def test_filter_excluded_passes_through_when_no_env(monkeypatch):
    from app.services.dev.router import _filter_excluded

    monkeypatch.delenv("DEV_COMMIT_EXCLUDE", raising=False)
    files = ["src/a.py", "src/b.py"]
    assert _filter_excluded(files) == files


def test_err_code_extracts_two_letter_family():
    from app.services.dev._shared import _err_code

    assert _err_code("ERROR: DL0042 failed to download") == "DL0042"
    assert _err_code("RN1234 render failed") == "RN1234"
    assert _err_code("no code here") == ""


def test_severity_thresholds():
    from app.services.dev._shared import _severity

    assert _severity("CRITICAL") == 4
    assert _severity("FATAL") == 4
    assert _severity("ERROR") == 3
    assert _severity("WARN") == 1
    assert _severity("INFO") == 1
    assert _severity("") == 1


def test_classify_uses_code_family_first():
    from app.services.dev.log import _classify

    # Code family takes precedence over text rules.
    assert _classify("anything goes here", "DL0042") == "download"
    assert _classify("anything goes here", "RN1234") == "render"
    assert _classify("ffmpeg failed somehow", "") == "render"  # text fallback
    assert _classify("nothing matches", "") == "unknown"


def test_infer_bug_class_returns_generic_for_unknown():
    from app.services.dev.bug import _infer_bug_class

    assert _infer_bug_class("download", "tried formats but none worked yt-dlp") == "download_format_fallback"
    assert _infer_bug_class("login", "session expired") == "login_state"
    assert _infer_bug_class("anything", "completely benign text") == "generic"


def test_actions_for_falls_back_to_unknown_recommendations():
    from app.services.dev.bug import _actions_for

    download = _actions_for("download")
    assert isinstance(download, list) and download

    unknown_cat = _actions_for("totally-made-up-category")
    assert unknown_cat == _actions_for("unknown")
    assert "Inspect traceback snippet" in " ".join(unknown_cat)


# ---------------------------------------------------------------------------
# Last-error round-trip (bug.py ↔ autofix.py state)
# ---------------------------------------------------------------------------


def test_last_error_round_trip_via_get_set():
    """``set_last_error`` / ``get_last_error`` are the cross-command
    state hand-off between ``/error`` and ``/fix``. Pin the round-trip
    so a future encapsulation move doesn't silently drop the contract."""
    from app.services.dev.bug import get_last_error, set_last_error

    set_last_error(None)
    assert get_last_error() is None

    payload = {"summary": "bla", "category": "render"}
    set_last_error(payload)
    assert get_last_error() == payload

    set_last_error(None)
    assert get_last_error() is None


def test_routes_devtools_still_imports_from_shim_path():
    """The only production consumer of execute_dev_command imports it
    via the legacy shim path. The split must NOT have moved that
    import out from under it."""
    import app.routes.devtools as devtools_route
    from app.services.dev_commands import execute_dev_command as shim_exec

    # The route's reference must be the same object as the shim's.
    assert devtools_route.execute_dev_command is shim_exec
