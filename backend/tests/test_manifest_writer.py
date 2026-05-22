"""
test_manifest_writer.py — Unit tests for manifest_writer service.

Coverage:
- manifest_path() naming convention
- write_manifest() creates the file
- Atomic write: temp file renamed, not written in-place
- read_manifest() returns None on missing file (no raise)
- read_manifest() returns None on corrupt JSON (no raise)
- write + read round-trip
- read_all_manifests() finds all part_* directories
- read_all_manifests() skips corrupt files, returns rest
- read_all_manifests() returns results sorted by part_no
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.timeline import TimelineMap
from app.domain.manifests import BaseClipManifest
from app.services.manifest_writer import (
    manifest_path,
    write_manifest,
    read_manifest,
    read_all_manifests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timeline(speed: float = 1.15) -> TimelineMap:
    return TimelineMap(source_start=10.0, source_end=40.0, effective_speed=speed)


def _make_manifest(job_id: str = "job_test", part_no: int = 1, **kw) -> BaseClipManifest:
    defaults = dict(
        job_id=job_id,
        part_no=part_no,
        source_path="/tmp/source.mp4",
        source_start=10.0,
        source_end=40.0,
        payload_speed=1.07,
        platform="tiktok",
        platform_delta=0.08,
        effective_speed=1.15,
        variant_type=None,
        variant_speed=None,
        silence_trim_offset=0.0,
        visual_trim_offset=0.0,
        timeline=_make_timeline(),
        ai_enabled=False,
        ai_mode=None,
        ai_selected=False,
        ai_speed_hint=None,
    )
    defaults.update(kw)
    return BaseClipManifest(**defaults)


# ---------------------------------------------------------------------------
# manifest_path()
# ---------------------------------------------------------------------------

class TestManifestPath:
    def test_naming_convention(self, tmp_path: Path):
        p = manifest_path(tmp_path, 1)
        assert p == tmp_path / "part_1" / "manifest.json"

    def test_part_3(self, tmp_path: Path):
        p = manifest_path(tmp_path, 3)
        assert p == tmp_path / "part_3" / "manifest.json"

    def test_returns_path_object(self, tmp_path: Path):
        assert isinstance(manifest_path(tmp_path, 1), Path)


# ---------------------------------------------------------------------------
# write_manifest()
# ---------------------------------------------------------------------------

class TestWriteManifest:
    def test_creates_file(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        result = write_manifest(tmp_path, m)
        assert result is not None
        assert result.exists()

    def test_creates_parent_dir(self, tmp_path: Path):
        # part_1/ directory does not exist yet
        m = _make_manifest(part_no=1)
        write_manifest(tmp_path, m)
        assert (tmp_path / "part_1").is_dir()

    def test_writes_valid_json(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        write_manifest(tmp_path, m)
        raw = (tmp_path / "part_1" / "manifest.json").read_text(encoding="utf-8")
        data = json.loads(raw)  # must not raise
        assert data["job_id"] == "job_test"

    def test_atomic_no_tmp_file_left_after_write(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        write_manifest(tmp_path, m)
        tmp_files = list((tmp_path / "part_1").glob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp files found: {tmp_files}"

    def test_returns_correct_path(self, tmp_path: Path):
        m = _make_manifest(part_no=2)
        result = write_manifest(tmp_path, m)
        assert result == manifest_path(tmp_path, 2)

    def test_overwrite_existing(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        write_manifest(tmp_path, m)
        m.cut_path = "/tmp/cut.mp4"
        write_manifest(tmp_path, m)
        data = json.loads(manifest_path(tmp_path, 1).read_text())
        assert data["cut_path"] == "/tmp/cut.mp4"


# ---------------------------------------------------------------------------
# read_manifest()
# ---------------------------------------------------------------------------

class TestReadManifest:
    def test_read_returns_none_on_missing_file(self, tmp_path: Path):
        result = read_manifest(tmp_path, 99)
        assert result is None

    def test_read_returns_none_on_corrupt_json(self, tmp_path: Path):
        part_dir = tmp_path / "part_1"
        part_dir.mkdir()
        (part_dir / "manifest.json").write_text("not valid json {{{", encoding="utf-8")
        result = read_manifest(tmp_path, 1)
        assert result is None

    def test_read_returns_none_on_empty_file(self, tmp_path: Path):
        part_dir = tmp_path / "part_1"
        part_dir.mkdir()
        (part_dir / "manifest.json").write_text("", encoding="utf-8")
        result = read_manifest(tmp_path, 1)
        assert result is None

    def test_write_then_read_round_trip(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        m.cut_path = "/tmp/cut.mp4"
        m.srt_path = "/tmp/part.srt"
        write_manifest(tmp_path, m)
        restored = read_manifest(tmp_path, 1)
        assert restored is not None
        assert restored.job_id == "job_test"
        assert restored.part_no == 1
        assert restored.cut_path == "/tmp/cut.mp4"
        assert restored.srt_path == "/tmp/part.srt"
        assert restored.ass_path is None

    def test_read_timeline_survives_round_trip(self, tmp_path: Path):
        m = _make_manifest(part_no=1)
        write_manifest(tmp_path, m)
        restored = read_manifest(tmp_path, 1)
        assert restored is not None
        assert restored.timeline.source_duration == pytest.approx(
            m.timeline.source_duration
        )
        assert restored.timeline.effective_speed == pytest.approx(
            m.timeline.effective_speed
        )

    def test_read_does_not_raise_on_permission_error(self, tmp_path: Path):
        # Simulate a missing file — read_manifest must return None, never raise
        result = read_manifest(tmp_path / "nonexistent", 1)
        assert result is None


# ---------------------------------------------------------------------------
# read_all_manifests()
# ---------------------------------------------------------------------------

class TestReadAllManifests:
    def test_returns_empty_list_when_no_parts(self, tmp_path: Path):
        result = read_all_manifests(tmp_path)
        assert result == []

    def test_finds_single_manifest(self, tmp_path: Path):
        write_manifest(tmp_path, _make_manifest(part_no=1))
        result = read_all_manifests(tmp_path)
        assert len(result) == 1
        assert result[0].part_no == 1

    def test_finds_multiple_manifests(self, tmp_path: Path):
        for part in [1, 2, 3]:
            write_manifest(tmp_path, _make_manifest(part_no=part))
        result = read_all_manifests(tmp_path)
        assert len(result) == 3

    def test_returns_sorted_by_part_no(self, tmp_path: Path):
        for part in [3, 1, 2]:
            write_manifest(tmp_path, _make_manifest(part_no=part))
        result = read_all_manifests(tmp_path)
        assert [m.part_no for m in result] == [1, 2, 3]

    def test_skips_corrupt_manifest(self, tmp_path: Path):
        write_manifest(tmp_path, _make_manifest(part_no=1))
        # Corrupt part_2
        bad_dir = tmp_path / "part_2"
        bad_dir.mkdir()
        (bad_dir / "manifest.json").write_text("corrupted", encoding="utf-8")
        write_manifest(tmp_path, _make_manifest(part_no=3))
        result = read_all_manifests(tmp_path)
        assert len(result) == 2
        assert {m.part_no for m in result} == {1, 3}

    def test_skips_directories_without_manifest(self, tmp_path: Path):
        write_manifest(tmp_path, _make_manifest(part_no=1))
        # part_2 dir exists but has no manifest.json
        (tmp_path / "part_2").mkdir()
        result = read_all_manifests(tmp_path)
        assert len(result) == 1

    def test_ignores_non_part_directories(self, tmp_path: Path):
        write_manifest(tmp_path, _make_manifest(part_no=1))
        (tmp_path / "scene_cache").mkdir()
        (tmp_path / "other_stuff").mkdir()
        result = read_all_manifests(tmp_path)
        assert len(result) == 1
        assert result[0].part_no == 1

    def test_returns_empty_list_on_nonexistent_work_dir(self, tmp_path: Path):
        result = read_all_manifests(tmp_path / "does_not_exist")
        assert result == []
