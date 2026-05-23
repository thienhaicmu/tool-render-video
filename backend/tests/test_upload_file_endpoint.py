"""
test_upload_file_endpoint.py — Tests for POST /api/upload-file endpoint.

Phase 5.1 — Task 1

Coverage:
- Route exists and returns 200 for a valid file upload
- Accepts a safe file and returns {"path": ...} response shape
- Rejects path traversal filenames (sanitised to safe name, NOT accepted as-is)
- Does NOT restore /api/upload/* domain
- _safe_filename sanitisation behaviour
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------

class TestImport:
    def test_files_router_importable(self):
        from app.routes.files import router
        assert router is not None

    def test_safe_filename_importable(self):
        from app.routes.files import _safe_filename
        assert callable(_safe_filename)


# ---------------------------------------------------------------------------
# _safe_filename unit tests
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def _fn(self, name):
        from app.routes.files import _safe_filename
        return _safe_filename(name)

    def test_normal_name_unchanged(self):
        assert self._fn("bgm_track.mp3") == "bgm_track.mp3"

    def test_spaces_collapsed_to_underscore(self):
        result = self._fn("my bgm file.mp3")
        assert " " not in result
        assert result.endswith(".mp3")

    def test_path_traversal_stripped(self):
        result = self._fn("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result.split("_")[0] or "_" in result

    def test_windows_path_traversal_stripped(self):
        result = self._fn("..\\..\\Windows\\system32\\evil.exe")
        assert "\\" not in result
        assert "/" not in result

    def test_null_bytes_stripped(self):
        result = self._fn("evil\x00file.mp3")
        assert "\x00" not in result

    def test_empty_string_returns_fallback(self):
        assert self._fn("") == "upload"

    def test_none_like_empty(self):
        # _safe_filename("") returns "upload"
        from app.routes.files import _safe_filename
        assert _safe_filename("") == "upload"

    def test_leading_dots_stripped(self):
        result = self._fn(".bashrc")
        assert not result.startswith(".")

    def test_absolute_unix_path_stripped(self):
        result = self._fn("/etc/shadow")
        assert "/" not in result

    def test_absolute_windows_path_stripped(self):
        result = self._fn("C:\\Windows\\System32\\cmd.exe")
        assert "\\" not in result
        assert "/" not in result

    def test_normal_mp3_filename_preserved(self):
        result = self._fn("background_music.mp3")
        assert result == "background_music.mp3"

    def test_unicode_normalised(self):
        # Should not raise
        result = self._fn("audio​file.mp3")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Route integration tests (no real I/O)
# ---------------------------------------------------------------------------

class TestUploadFileRoute:
    """Test the /api/upload-file endpoint via FastAPI TestClient."""

    def _get_client(self):
        """Import FastAPI app and return a TestClient instance."""
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_upload_file_route_exists(self):
        """POST /api/upload-file must exist (not 404/405)."""
        client = self._get_client()
        # We patch the file write so no disk I/O needed
        with patch("app.routes.files._EDITOR_UPLOADS_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(
                exists=MagicMock(return_value=False),
                open=MagicMock(return_value=MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(write=MagicMock())),
                    __exit__=MagicMock(return_value=False),
                )),
                __str__=MagicMock(return_value="/fake/path/test.mp3"),
            ))
            mock_dir.mkdir = MagicMock()
            response = client.post(
                "/api/upload-file",
                files={"file": ("test.mp3", io.BytesIO(b"fake audio data"), "audio/mpeg")},
            )
        # Must not be 404 (route missing) or 405 (method not allowed)
        assert response.status_code != 404, "Route /api/upload-file not found"
        assert response.status_code != 405, "Method POST not allowed on /api/upload-file"

    def test_upload_returns_path_key(self, tmp_path):
        """Successful upload returns JSON with a 'path' key."""
        import app.routes.files as files_mod
        original_dir = files_mod._EDITOR_UPLOADS_DIR
        files_mod._EDITOR_UPLOADS_DIR = tmp_path

        try:
            client = self._get_client()
            response = client.post(
                "/api/upload-file",
                files={"file": ("bgm.mp3", io.BytesIO(b"fake audio data for test"), "audio/mpeg")},
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "path" in data, f"Response missing 'path' key: {data}"
            assert str(tmp_path) in data["path"] or "bgm" in data["path"]
        finally:
            files_mod._EDITOR_UPLOADS_DIR = original_dir

    def test_upload_file_field_name_is_file(self, tmp_path):
        """Frontend sends field name 'file' — must be accepted."""
        import app.routes.files as files_mod
        original_dir = files_mod._EDITOR_UPLOADS_DIR
        files_mod._EDITOR_UPLOADS_DIR = tmp_path

        try:
            client = self._get_client()
            response = client.post(
                "/api/upload-file",
                files={"file": ("music.mp3", io.BytesIO(b"audio"), "audio/mpeg")},
            )
            assert response.status_code == 200
        finally:
            files_mod._EDITOR_UPLOADS_DIR = original_dir

    def test_upload_path_traversal_filename_sanitised(self, tmp_path):
        """Path traversal filename must be sanitised — not stored at the traversal path."""
        import app.routes.files as files_mod
        original_dir = files_mod._EDITOR_UPLOADS_DIR
        files_mod._EDITOR_UPLOADS_DIR = tmp_path

        try:
            client = self._get_client()
            response = client.post(
                "/api/upload-file",
                files={"file": ("../../etc/passwd", io.BytesIO(b"evil"), "application/octet-stream")},
            )
            # Request must succeed (sanitised name) OR be rejected — but NOT save to parent dir
            if response.status_code == 200:
                data = response.json()
                saved_path = Path(data["path"])
                # The saved path must be inside tmp_path, not a parent escape
                assert saved_path.resolve().is_relative_to(tmp_path.resolve()), (
                    f"Path traversal escaped upload dir: {saved_path}"
                )
        finally:
            files_mod._EDITOR_UPLOADS_DIR = original_dir

    def test_upload_windows_path_traversal_sanitised(self, tmp_path):
        """Windows-style path traversal must also be sanitised."""
        import app.routes.files as files_mod
        original_dir = files_mod._EDITOR_UPLOADS_DIR
        files_mod._EDITOR_UPLOADS_DIR = tmp_path

        try:
            client = self._get_client()
            response = client.post(
                "/api/upload-file",
                files={"file": ("..\\..\\system32\\evil.dll", io.BytesIO(b"evil"), "application/octet-stream")},
            )
            if response.status_code == 200:
                data = response.json()
                saved_path = Path(data["path"])
                assert saved_path.resolve().is_relative_to(tmp_path.resolve()), (
                    f"Windows path traversal escaped upload dir: {saved_path}"
                )
        finally:
            files_mod._EDITOR_UPLOADS_DIR = original_dir


# ---------------------------------------------------------------------------
# Upload domain removal safety — /api/upload/* must not exist
# ---------------------------------------------------------------------------

class TestUploadDomainNotRestored:
    """Verify the old /api/upload/* domain is NOT restored by Task 1."""

    def _get_routes(self):
        from app.main import app
        return {r.path for r in app.routes}

    def test_upload_star_routes_absent(self):
        """No /api/upload/* routes must exist."""
        routes = self._get_routes()
        upload_routes = [r for r in routes if r.startswith("/api/upload/")]
        assert len(upload_routes) == 0, (
            f"Old /api/upload/* routes found: {upload_routes}. "
            "Task 1 must not restore the upload domain."
        )

    def test_routes_upload_py_still_deleted(self):
        """routes/upload.py must still be deleted (not restored)."""
        from pathlib import Path
        backend_root = Path(__file__).resolve().parents[1]
        upload_route = backend_root / "app" / "routes" / "upload.py"
        assert not upload_route.exists(), (
            "routes/upload.py has been restored — must remain deleted"
        )

    def test_upload_file_is_different_from_upload_domain(self):
        """/api/upload-file is a single endpoint, not a domain restoration."""
        routes = self._get_routes()
        # /api/upload-file must exist
        assert "/api/upload-file" in routes, (
            "/api/upload-file route not registered — Task 1 incomplete"
        )
        # But /api/upload/* must not
        upload_domain = [r for r in routes if r.startswith("/api/upload/")]
        assert len(upload_domain) == 0, (
            f"Old /api/upload/* domain restored alongside /api/upload-file: {upload_domain}"
        )
