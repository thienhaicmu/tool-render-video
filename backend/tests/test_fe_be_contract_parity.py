"""C1 (2026-06-27) — FE↔BE contract parity guard.

The frozen job-stage / job-part names and the result_json backward-compat
keys are matched as bare string literals on BOTH sides of the wire with no
shared type system. This test reads the frontend's canonical mirror
(frontend/src/types/enums.ts) and asserts it is byte-identical to the
backend canonical declaration (app/core/contracts.py). A rename on either
side that is not mirrored on the other turns a silent runtime UI breakage
(progress stuck, history empty) into a red CI build.

No live server / no codegen toolchain — pure source parsing, runs in the
normal pytest suite.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.contracts import (
    JOB_PART_STAGE_VALUES,
    JOB_STAGE_VALUES,
    RESULT_JSON_BACKWARD_COMPAT_KEYS,
)

_ENUMS_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "enums.ts"
)


def _extract_const_array(source: str, const_name: str) -> list[str]:
    """Return the string members of ``export const <name> = [ ... ] as const``."""
    m = re.search(
        rf"export const {re.escape(const_name)}\s*=\s*\[(.*?)\]\s*as const",
        source,
        re.DOTALL,
    )
    assert m, f"{const_name} not found in {_ENUMS_TS.name} — FE mirror missing/renamed"
    body = m.group(1)
    return re.findall(r"'([^']*)'", body)


def _extract_union(source: str, type_name: str) -> set[str]:
    """Return the string-literal members of a ``type X = 'a' | 'b' | ...`` union."""
    m = re.search(rf"export type {re.escape(type_name)}\s*=([^;]*?)(?:\n\n|//|export)", source, re.DOTALL)
    assert m, f"type {type_name} not found in {_ENUMS_TS.name}"
    return set(re.findall(r"'([^']*)'", m.group(1)))


def test_enums_ts_exists():
    assert _ENUMS_TS.is_file(), f"FE contract mirror missing: {_ENUMS_TS}"


def test_job_stage_values_match():
    fe = _extract_const_array(_ENUMS_TS.read_text(encoding="utf-8-sig"), "JOB_STAGE_VALUES")
    assert list(fe) == list(JOB_STAGE_VALUES), (
        "C1 drift — JOB_STAGE_VALUES in frontend/src/types/enums.ts no longer "
        "matches backend JobStage (app/core/contracts.py). Sacred Contract #4. "
        f"FE={list(fe)} BE={list(JOB_STAGE_VALUES)}. Mirror the change on both "
        "sides (and audit every WebSocket/progress consumer of the renamed stage)."
    )


def test_job_part_stage_values_match():
    fe = _extract_const_array(_ENUMS_TS.read_text(encoding="utf-8-sig"), "JOB_PART_STAGE_VALUES")
    assert list(fe) == list(JOB_PART_STAGE_VALUES), (
        "C1 drift — JOB_PART_STAGE_VALUES in enums.ts no longer matches backend "
        "JobPartStage. Sacred Contract #5. "
        f"FE={list(fe)} BE={list(JOB_PART_STAGE_VALUES)}."
    )


def test_result_json_required_keys_match():
    fe = _extract_const_array(_ENUMS_TS.read_text(encoding="utf-8-sig"), "RESULT_JSON_REQUIRED_KEYS")
    assert set(fe) == set(RESULT_JSON_BACKWARD_COMPAT_KEYS), (
        "C1 drift — RESULT_JSON_REQUIRED_KEYS in enums.ts no longer matches the "
        "backend Sacred Contract #1 keys. The history / output-compare UIs read "
        f"these as literals. FE={sorted(fe)} BE={sorted(RESULT_JSON_BACKWARD_COMPAT_KEYS)}."
    )


def test_render_stage_union_covers_every_canonical_stage():
    """The renderable RenderStage union may carry extra legacy values, but it
    must never DROP a canonical backend stage — otherwise the progress UI has
    no case for a stage the backend can emit (e.g. the 'cancelled' drift this
    test was added to catch)."""
    union = _extract_union(_ENUMS_TS.read_text(encoding="utf-8-sig"), "RenderStage")
    missing = set(JOB_STAGE_VALUES) - union
    assert not missing, (
        f"RenderStage union in enums.ts is missing canonical backend stages: "
        f"{sorted(missing)}. The progress UI cannot label a stage the backend emits."
    )
