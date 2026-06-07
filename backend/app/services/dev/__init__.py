"""Dev-tools command package.

Audit MT-1 (Batch 10J 2026-06-06): decomposition of the 1542-LOC
``app.services.dev_commands`` monolith into 6 sub-modules
(``_shared``, ``log``, ``bug``, ``registry``, ``autofix``,
``router``). The public surface is unchanged: ``execute_dev_command``
remains the single entry point consumed by
``app.routes.devtools.run_dev_command``.

``app.services.dev_commands`` was preserved as a re-export shim so
the existing import path keeps working without edits.
"""
from app.services.dev.router import execute_dev_command

__all__ = ["execute_dev_command"]
