"""Phase K — Batch Render from Asset Library QA tests.

Covers:
  - routes/batch_render.py: POST /api/render/batch
    - Empty asset_ids rejected
    - Asset not found → skipped
    - Source file missing → skipped
    - Preset not found → 404
    - Max batch size enforced (> 20)
    - Successful enqueue path (mocked)
    - Response shape: total/queued/skipped/jobs
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _asset(file_path: str, exists: bool = True):
    from app.domain.asset import Asset
    a = Asset(asset_id="aid1", file_path=file_path)
    return a


# ── validation ────────────────────────────────────────────────────────────────

def test_batch_render_empty_asset_ids_rejected():
    resp = _client().post("/api/render/batch", json={"asset_ids": []})
    assert resp.status_code == 422


def test_batch_render_too_many_assets_rejected():
    # More than 20 asset_ids should fail at pydantic validation
    resp = _client().post("/api/render/batch", json={
        "asset_ids": [f"id{i}" for i in range(21)],
        "output_dir": "/tmp/out",
    })
    assert resp.status_code == 422


def test_batch_render_missing_preset_returns_404():
    with patch("app.routes.batch_render.get_preset", return_value=None):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            "preset_id": "nonexistent_preset",
            "output_dir": "/tmp/out",
        })
    assert resp.status_code == 404


# ── skip logic ────────────────────────────────────────────────────────────────

def test_batch_render_asset_not_found_skipped():
    with patch("app.routes.batch_render.get_asset", return_value=None), \
         patch("app.routes.batch_render.get_preset", return_value=None):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["missing_id"],
            "output_dir": "/tmp/out",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] == 1
    assert body["queued"] == 0
    assert body["jobs"][0]["status"] == "skipped"
    assert body["jobs"][0]["error"] == "asset_not_found"


def test_batch_render_source_file_missing_skipped(tmp_path):
    asset = _asset("/nonexistent/video.mp4")
    with patch("app.routes.batch_render.get_asset", return_value=asset), \
         patch("app.routes.batch_render.get_preset", return_value=None):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            "output_dir": "/tmp/out",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs"][0]["status"] == "skipped"
    assert body["jobs"][0]["error"] == "source_file_missing"


# ── output_dir resolution ─────────────────────────────────────────────────────

def test_batch_render_requires_output_dir():
    """When no output_dir given and no saved default, must return 400."""
    with patch("app.routes.batch_render.get_asset", return_value=None), \
         patch("app.routes.batch_render.get_preset", return_value=None), \
         patch("app.db.creator_repo.get_default_output_dir", return_value=""):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            # No output_dir
        })

    assert resp.status_code in (400, 422)


# ── success path ──────────────────────────────────────────────────────────────

def test_batch_render_queues_jobs_successfully(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    asset = _asset(str(video))

    with patch("app.routes.batch_render.get_asset", return_value=asset), \
         patch("app.routes.batch_render.get_preset", return_value=None), \
         patch("app.routes.batch_render._queue_render_job") as mock_queue:
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            "output_dir": str(tmp_path),
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["queued"] == 1
    assert body["skipped"] == 0
    assert body["jobs"][0]["status"] == "queued"
    mock_queue.assert_called_once()


def test_batch_render_response_shape(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    asset = _asset(str(video))

    with patch("app.routes.batch_render.get_asset", return_value=asset), \
         patch("app.routes.batch_render.get_preset", return_value=None), \
         patch("app.routes.batch_render._queue_render_job"):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            "output_dir": str(tmp_path),
        })

    assert resp.status_code == 200
    body = resp.json()
    # Required top-level keys
    for key in ("total", "queued", "skipped", "jobs"):
        assert key in body
    assert body["total"] == 1
    # Per-job required keys
    job = body["jobs"][0]
    for key in ("asset_id", "job_id", "status"):
        assert key in job


def test_batch_render_mixed_skip_and_queue(tmp_path):
    """One asset found on disk, one not found — should get 1 queued + 1 skipped."""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    asset_ok = _asset(str(video))

    def get_asset_side_effect(asset_id):
        return asset_ok if asset_id == "found_id" else None

    with patch("app.routes.batch_render.get_asset",
               side_effect=get_asset_side_effect), \
         patch("app.routes.batch_render.get_preset", return_value=None), \
         patch("app.routes.batch_render._queue_render_job"):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["found_id", "missing_id"],
            "output_dir": str(tmp_path),
        })

    body = resp.json()
    assert body["total"] == 2
    assert body["queued"] == 1
    assert body["skipped"] == 1


def test_batch_render_preset_params_applied(tmp_path):
    """Preset params should be applied to all enqueued jobs."""
    from app.domain.render_preset import RenderPreset

    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    asset = _asset(str(video))
    preset = RenderPreset(
        preset_id="p1", name="Quick",
        params={"output_count": 5, "target_platform": "tiktok"},
    )

    captured_payloads = []

    def mock_queue(job_id, channel, payload, **kwargs):
        captured_payloads.append(payload)

    with patch("app.routes.batch_render.get_asset", return_value=asset), \
         patch("app.routes.batch_render.get_preset", return_value=preset), \
         patch("app.routes.batch_render._queue_render_job",
               side_effect=mock_queue):
        resp = _client().post("/api/render/batch", json={
            "asset_ids": ["aid1"],
            "preset_id": "p1",
            "output_dir": str(tmp_path),
        })

    assert resp.status_code == 200
    assert len(captured_payloads) == 1
    assert captured_payloads[0].output_count == 5
