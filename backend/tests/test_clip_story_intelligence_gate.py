"""
test_clip_story_intelligence_gate.py — guard for 0C (clip Story Intelligence env gate).

Pins the Sacred Contract #2 guarantee: the CLIP_STORY_INTELLIGENCE_DEFAULT env
gate defaults OFF, so a stored/replayed job (whose ``use_story_intelligence``
field is False) behaves byte-identically to the pre-0C baseline — the
Comprehension stage is skipped. Only an explicit env opt-in enables it globally.

Uses subprocesses so importing render_pipeline under a mutated env doesn't
pollute the shared test session (the module creates module-level semaphores).
"""
from __future__ import annotations

import os
import subprocess
import sys

_SNIPPET = (
    "import app.features.render.engine.pipeline.render_pipeline as r; "
    "print('FLAG=' + str(r._CLIP_STORY_INTEL_DEFAULT))"
)


def _read_flag(env_value: str | None) -> str:
    env = dict(os.environ)
    env.pop("CLIP_STORY_INTELLIGENCE_DEFAULT", None)
    if env_value is not None:
        env["CLIP_STORY_INTELLIGENCE_DEFAULT"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    for line in out.stdout.splitlines():
        if line.startswith("FLAG="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"flag not printed. stdout={out.stdout!r} stderr={out.stderr[-500:]!r}")


def test_clip_story_intelligence_defaults_off_contract2_baseline():
    # Unset env → must be False so replayed jobs are byte-identical to pre-0C.
    assert _read_flag(None) == "False"


def test_clip_story_intelligence_env_enables():
    assert _read_flag("1") == "True"


def test_clip_story_intelligence_non_one_stays_off():
    # Only the literal "1" enables it (matches LLM_EMIT_RENDER_PLAN convention).
    assert _read_flag("true") == "False"
    assert _read_flag("0") == "False"
