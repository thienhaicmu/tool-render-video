"""Re-export shim for the legacy ``app.services.dev_commands`` import path.

Audit MT-1 (Batch 10J 2026-06-06): the original 1542-LOC monolith was
decomposed into the ``app.services.dev`` package. This file remains
as the canonical import path so the route consumer
(``app.routes.devtools.run_dev_command``) keeps working without
edits. New code SHOULD prefer ``from app.services.dev import …``.

The 6 sub-modules of the new package:

- ``app.services.dev._shared``  — bottom-layer utilities.
- ``app.services.dev.log``      — log discovery + parsing + ``_cmd_log``.
- ``app.services.dev.bug``      — bug classification + ``_choose_error`` + ``_cmd_error``.
- ``app.services.dev.registry`` — fix feature registry + target parsing.
- ``app.services.dev.autofix``  — autofix machinery + ``_cmd_fix``.
- ``app.services.dev.router``   — dispatcher + simple commands.
"""
from __future__ import annotations

from app.services.dev import execute_dev_command

__all__ = ["execute_dev_command"]
