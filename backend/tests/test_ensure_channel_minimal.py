"""Tests for the slimmed ensure_channel (2026-06-06 audit follow-up).

The previous implementation created 14 directories and 5 files per
``ensure_channel()`` call, all scaffolding for the auto-upload pipeline
that was retired in Phase 4F.5A:

  hashtag/hashtags.txt                     ← TikTok upload tags
  account/account.json                     ← TikTok upload selectors
  account/upload_settings.json             ← proxy / browser preference
  account/templates/credential_line_template.txt
  CHANNEL_STRUCTURE.txt                    ← README for upload flow

These were written every time a render job was queued. The user
caught it; the audit's Batch 2 DC02 already deleted the matching
Pydantic models — this commit closes the writer half.

These tests pin the new contract:

1. Only the two render-essential paths are created.
2. The five legacy upload files MUST NOT be re-created.
3. Idempotency: a second call on the same channel does not fail and
   does not start re-creating upload artefacts.
4. The returned base path matches the channel-code directory under
   the resolved root.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.channel_service import ensure_channel


# ---------------------------------------------------------------------------
# Render-essential paths must exist
# ---------------------------------------------------------------------------

def test_creates_video_out_dir(tmp_path):
    base = ensure_channel("kx", root_dir=tmp_path)
    assert (base / "video_out").is_dir()


def test_creates_logs_render_dir(tmp_path):
    base = ensure_channel("kx", root_dir=tmp_path)
    assert (base / "logs" / "render").is_dir()


def test_returns_channel_base_path(tmp_path):
    base = ensure_channel("the_channel", root_dir=tmp_path)
    assert base == tmp_path / "the_channel"
    assert base.is_dir()


# ---------------------------------------------------------------------------
# Upload pipeline artefacts MUST NOT be created (the regression we're closing)
# ---------------------------------------------------------------------------

_FORBIDDEN_FILES = (
    "CHANNEL_STRUCTURE.txt",
    "hashtag/hashtags.txt",
    "account/account.json",
    "account/upload_settings.json",
    "account/templates/credential_line_template.txt",
)
_FORBIDDEN_DIRS = (
    "hashtag",
    "account",
    "account/profiles",
    "account/templates",
    "account/mailbox",
    "browser-profile",
    "upload",
    "upload/source",
    "upload/queue",
    "upload/uploaded",
    "upload/failed",
    "upload/archive",
    "upload/logs",
    "upload/video_output",
    "logs/upload",
)


@pytest.mark.parametrize("filename", _FORBIDDEN_FILES)
def test_does_not_create_upload_files(tmp_path, filename):
    base = ensure_channel("kx", root_dir=tmp_path)
    assert not (base / filename).exists(), (
        f"ensure_channel re-created upload artefact {filename!r}. "
        f"Upload feature was retired in Phase 4F.5A; this file must "
        f"NOT be written by the render path."
    )


@pytest.mark.parametrize("dirname", _FORBIDDEN_DIRS)
def test_does_not_create_upload_dirs(tmp_path, dirname):
    base = ensure_channel("kx", root_dir=tmp_path)
    assert not (base / dirname).exists(), (
        f"ensure_channel re-created upload scaffold dir {dirname!r}."
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_called_twice_does_not_raise(tmp_path):
    ensure_channel("kx", root_dir=tmp_path)
    # Second call must not raise and must not regress the contract.
    ensure_channel("kx", root_dir=tmp_path)


def test_idempotent_does_not_recreate_upload_artefacts(tmp_path):
    ensure_channel("kx", root_dir=tmp_path)
    ensure_channel("kx", root_dir=tmp_path)
    base = tmp_path / "kx"
    for f in _FORBIDDEN_FILES:
        assert not (base / f).exists()


def test_preserves_existing_upload_files_on_old_channels(tmp_path):
    """Sacred Contract #2 spirit — we slim the writer but never delete
    artefacts that already exist on the user's disk from older runs.
    """
    base = tmp_path / "legacy"
    (base / "account").mkdir(parents=True)
    (base / "account" / "upload_settings.json").write_text(
        '{"keep": "me"}', encoding="utf-8"
    )
    ensure_channel("legacy", root_dir=tmp_path)
    assert (base / "account" / "upload_settings.json").read_text(encoding="utf-8") == '{"keep": "me"}'


# list_channels test removed in Batch 10H — the function was deleted
# alongside the orphan /api/channels/* surface (audit FINDING-API05 closure).
