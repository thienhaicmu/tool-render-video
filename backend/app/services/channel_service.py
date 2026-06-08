"""Channel directory bootstrap.

Audit 2026-06-06 follow-up: this module previously created a large upload
pipeline scaffold (account/, upload/, hashtag/, CHANNEL_STRUCTURE.txt,
browser-profile/, …) every time a render job was queued. That entire
pipeline was retired in Phase 4F.5A:

- The 7 upload-related HTTP endpoints were removed (see comments in
  ``frontend/src/api/upload.ts``).
- The 15 upload Pydantic models were deleted in Batch 2 (commit cbd8cca).
- The corresponding routes/channels.py readers are now UNCALLED per
  Phase 6 FINDING-API05 — they exist but the FE never invokes them.

Yet ``ensure_channel`` was still writing the upload artefacts to disk
(``hashtag/hashtags.txt``, ``account/account.json`` with TikTok upload
selectors + credential paths, ``CHANNEL_STRUCTURE.txt`` README) on
every render submission. The user (rightly) asked: why are we creating
files for a feature that was removed long ago?

This rewrite slims ``ensure_channel`` to only the two paths the live
render pipeline actually needs:

- ``<base>/video_out/``    — channel-mode output target.
- ``<base>/logs/render/``  — per-job log directory used by render_pipeline.

Anything else is left to whoever needs it. If the channel CRUD API
ever gets resurrected, it can re-add its own scaffolding without
forcing every render to pay the cost.
"""
from pathlib import Path

from app.core.config import CHANNELS_DIR


def ensure_channel(channel_code: str, root_dir=None):
    """Create the minimal channel folder structure for the render pipeline.

    Idempotent: calling on an existing channel folder is a no-op.

    NOTE: This intentionally does NOT create the upload pipeline scaffold
    that older versions of this function shipped (hashtag/, account/,
    upload/, browser-profile/, CHANNEL_STRUCTURE.txt, …). Those belonged
    to the auto-upload feature retired in Phase 4F.5A. Their reader code
    in routes/channels.py is uncalled per Phase 6 FINDING-API05; if any
    of those endpoints ever ship again they can lazily create what they
    need at that point.
    """
    root = Path(root_dir) if root_dir else CHANNELS_DIR
    root.mkdir(parents=True, exist_ok=True)
    base = root / channel_code
    base.mkdir(parents=True, exist_ok=True)

    # Render-essential paths only:
    # - video_out/      → channel-mode output target (referenced by router
    #                     validators in routers/_common.py)
    # - logs/render/    → per-job log directory consumed by
    #                     render_pipeline.register_job_log_dir
    for p in (base / "video_out", base / "logs" / "render"):
        p.mkdir(parents=True, exist_ok=True)

    return base


# list_channels() removed in Batch 10H (audit FINDING-API05 closure): its sole
# caller was routes/channels.py:get_channels, which has been deleted alongside
# the rest of the orphan /api/channels surface.
