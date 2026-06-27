"""Single source of truth for cross-surface (FE↔BE) contract constants.

C1 (2026-06-27). The frozen job-stage / job-part names (Sacred Contracts
#4 and #5) and the result_json backward-compat keys (Sacred Contract #1)
are matched as bare string literals in BOTH the backend and the React
frontend, with no shared type system bridging them. A rename on one side
that is not mirrored on the other does not raise — it silently breaks
progress UI / history parsing.

This module is the BACKEND canonical declaration. The frontend mirror is
``frontend/src/types/enums.ts`` (JOB_STAGE_VALUES / JOB_PART_STAGE_VALUES /
RESULT_JSON_REQUIRED_KEYS). The parity test
``backend/tests/test_fe_be_contract_parity.py`` fails CI the moment the two
drift, converting a class of silent runtime breakage into a red build.

Do not add legacy aliases here — this is the exact, current wire contract.
The frontend type unions may carry extra legacy values for tolerance, but
these canonical tuples must stay byte-identical across the two surfaces.
"""
from __future__ import annotations

from app.core.stage import JobPartStage, JobStage

# Frozen job-stage names — Sacred Contract #4 (core/stage.py is the enum).
JOB_STAGE_VALUES: tuple[str, ...] = tuple(s.value for s in JobStage)

# Frozen per-part status names — Sacred Contract #5.
JOB_PART_STAGE_VALUES: tuple[str, ...] = tuple(s.value for s in JobPartStage)

# Sacred Contract #1 — these keys MUST exist in every result_json blob the
# render pipeline writes, forever. The history / output-compare UIs read
# them as hardcoded string literals.
RESULT_JSON_BACKWARD_COMPAT_KEYS: tuple[str, ...] = (
    "output_rank_score",
    "is_best_output",
    "is_best_clip",
)
