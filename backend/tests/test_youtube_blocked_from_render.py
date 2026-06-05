"""
Sprint 1.2 gate test — YouTube/remote sources MUST be blocked from the
render pipeline. The standalone Downloader feature handles remote fetching;
the render pipeline only accepts local files.

These tests assert the boundary, not a specific error message.
"""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestPrepareSourceYouTubeBlocked:
    def test_rejects_source_mode_youtube(self):
        """POST /api/render/prepare-source with source_mode='youtube' must reject."""
        resp = client.post(
            "/api/render/prepare-source",
            json={"source_mode": "youtube", "source_video_path": "x"},
        )
        assert resp.status_code == 400
        # Error message should mention the standalone Downloader as the alternative.
        body = resp.json()
        detail = str(body.get("detail", "")).lower()
        assert "downloader" in detail or "local" in detail

    def test_rejects_unknown_source_mode(self):
        """Any non-local source_mode must be rejected — generalisation gate."""
        resp = client.post(
            "/api/render/prepare-source",
            json={"source_mode": "tiktok", "source_video_path": "x"},
        )
        assert resp.status_code == 400

    def test_legacy_youtube_url_field_is_ignored(self):
        """Legacy payloads with youtube_url (no source_mode) must not 422.

        Backward-compat: stored job payloads from before Sprint 1.2 may still
        carry a youtube_url field. Pydantic extra='ignore' should drop it silently
        and treat the request as local (the default). Since source_video_path is
        missing, the route returns 400 "File not found" — NOT 422 validation error.
        """
        resp = client.post(
            "/api/render/prepare-source",
            json={"youtube_url": "https://youtube.com/watch?v=foo"},
        )
        # Must not be 422 validation error (extra=ignore worked).
        assert resp.status_code != 422
        # source_mode defaults to 'local' → falls through to file-not-found 400.
        assert resp.status_code in (400, 500)


class TestQuickProcessYouTubeBlocked:
    def test_rejects_source_youtube(self):
        """POST /api/render/quick-process with source='youtube' must reject."""
        resp = client.post(
            "/api/render/quick-process",
            json={"source": "youtube", "url": "https://youtube.com/watch?v=foo", "output": "/tmp/x.mp4"},
        )
        assert resp.status_code == 400
        body = resp.json()
        detail = str(body.get("detail", "")).lower()
        assert "downloader" in detail or "local" in detail

    def test_local_source_default_is_accepted(self):
        """With Sprint 1.2 defaults, source defaults to 'local'. Missing path → 400."""
        resp = client.post("/api/render/quick-process", json={})
        assert resp.status_code == 400  # missing path / output, NOT a YouTube reject
        body = resp.json()
        detail = str(body.get("detail", "")).lower()
        # Should complain about path or output, not about source mode.
        assert "path" in detail or "output" in detail
