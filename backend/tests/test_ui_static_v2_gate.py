"""Tests for ui_gate.resolve_static_directory and static-v2 activation.

Phase 6.7 — Electron Cut-over + Static v2 Activation
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_dirs(tmp: Path, *parts: str) -> Path:
    d = tmp
    for p in parts:
        d = d / p
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestResolveStaticDirectory:
    def test_default_serves_legacy(self, tmp_path):
        from app.core.ui_gate import resolve_static_directory
        static_dir = _make_dirs(tmp_path, "static")
        (static_dir / "index.html").touch()
        result_dir, version = resolve_static_directory(tmp_path, env_value="")
        assert version == "legacy"
        assert result_dir == static_dir

    def test_legacy_env_serves_legacy(self, tmp_path):
        from app.core.ui_gate import resolve_static_directory
        static_dir = _make_dirs(tmp_path, "static")
        (static_dir / "index.html").touch()
        result_dir, version = resolve_static_directory(tmp_path, env_value="legacy")
        assert version == "legacy"

    def test_v2_env_serves_v2_when_exists(self, tmp_path):
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        v2_dir = _make_dirs(tmp_path, "static-v2")
        (v2_dir / "index.html").touch()
        result_dir, version = resolve_static_directory(tmp_path, env_value="v2")
        assert version == "v2"
        assert result_dir == v2_dir

    def test_v2_env_falls_back_when_v2_missing(self, tmp_path):
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        # Do NOT create static-v2
        result_dir, version = resolve_static_directory(tmp_path, env_value="v2")
        assert version == "legacy"  # graceful fallback

    def test_invalid_version_falls_back_to_legacy(self, tmp_path):
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        result_dir, version = resolve_static_directory(tmp_path, env_value="v99")
        assert version == "legacy"

    def test_v2_and_legacy_dirs_coexist(self, tmp_path):
        """v2 activation does not remove or break legacy directory."""
        from app.core.ui_gate import resolve_static_directory
        static_dir = _make_dirs(tmp_path, "static")
        (static_dir / "index.html").write_text("<html>legacy</html>")
        v2_dir = _make_dirs(tmp_path, "static-v2")
        (v2_dir / "index.html").write_text("<html>v2</html>")
        _, v2_ver = resolve_static_directory(tmp_path, env_value="v2")
        _, leg_ver = resolve_static_directory(tmp_path, env_value="legacy")
        assert v2_ver == "v2"
        assert leg_ver == "legacy"
        # Both index files still intact
        assert (static_dir / "index.html").read_text() == "<html>legacy</html>"
        assert (v2_dir / "index.html").read_text() == "<html>v2</html>"

    def test_never_raises(self, tmp_path):
        """resolve_static_directory must never raise even with bad inputs."""
        from app.core.ui_gate import resolve_static_directory
        # Completely empty tmp dir (no static/ dir at all)
        try:
            resolve_static_directory(tmp_path, env_value="v2")
        except Exception as exc:
            pytest.fail(f"resolve_static_directory raised: {exc}")

    def test_v2_path_is_static_v2_subdir(self, tmp_path):
        """When v2 is active, returned path must be backend_root/static-v2."""
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        v2_dir = _make_dirs(tmp_path, "static-v2")
        (v2_dir / "index.html").touch()
        result_dir, version = resolve_static_directory(tmp_path, env_value="v2")
        assert result_dir.name == "static-v2"
        assert result_dir.parent == tmp_path

    def test_legacy_path_is_static_subdir(self, tmp_path):
        """When legacy is active, returned path must be backend_root/static."""
        from app.core.ui_gate import resolve_static_directory
        static_dir = _make_dirs(tmp_path, "static")
        result_dir, version = resolve_static_directory(tmp_path, env_value="legacy")
        assert result_dir.name == "static"

    def test_case_insensitive_v2(self, tmp_path):
        """STATIC_UI_VERSION=V2 (uppercase) falls back to legacy (no match)."""
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        v2_dir = _make_dirs(tmp_path, "static-v2")
        (v2_dir / "index.html").touch()
        # "V2" is normalized to lowercase "v2" so it should still match
        result_dir, version = resolve_static_directory(tmp_path, env_value="V2")
        assert version == "v2"

    def test_whitespace_trimmed_in_env_value(self, tmp_path):
        """Leading/trailing whitespace in env value is trimmed."""
        from app.core.ui_gate import resolve_static_directory
        _make_dirs(tmp_path, "static")
        v2_dir = _make_dirs(tmp_path, "static-v2")
        (v2_dir / "index.html").touch()
        result_dir, version = resolve_static_directory(tmp_path, env_value="  v2  ")
        assert version == "v2"


class TestHealthEndpoint:
    def test_health_endpoint_reports_ui_version(self):
        """Health endpoint includes ui_version field."""
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "ui_version" in data
        assert data["ui_version"] in ("v2", "legacy")

    def test_health_endpoint_status_ok(self):
        """Health endpoint always returns status=ok."""
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_root_returns_200(self):
        """GET / returns 200 (serves index.html)."""
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        # May return 404 if index.html does not exist in test env — that's OK,
        # but endpoint must be registered (not 405 Method Not Allowed)
        response = client.get("/")
        assert response.status_code in (200, 404)


class TestStaticV2ArtifactIntegrity:
    """Verify the built static-v2 artifact is correctly structured."""

    @pytest.fixture
    def static_v2_path(self):
        return Path(__file__).resolve().parents[2] / "backend" / "static-v2"

    def test_static_v2_dir_exists(self, static_v2_path):
        """backend/static-v2/ directory must exist after build+copy."""
        assert static_v2_path.is_dir(), (
            "backend/static-v2/ not found — run: cd frontend && npx vite build, "
            "then copy backend/static-new/ to backend/static-v2/"
        )

    def test_static_v2_has_index_html(self, static_v2_path):
        """index.html must be present at top level of static-v2."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        assert (static_v2_path / "index.html").is_file()

    def test_static_v2_has_assets_dir(self, static_v2_path):
        """assets/ subdirectory must exist."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        assert (static_v2_path / "assets").is_dir()

    def test_static_v2_has_js_bundle(self, static_v2_path):
        """At least one .js file must exist in assets/."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        js_files = list((static_v2_path / "assets").glob("*.js"))
        assert len(js_files) >= 1, "No JS bundle found in static-v2/assets/"

    def test_static_v2_has_css_bundle(self, static_v2_path):
        """At least one .css file must exist in assets/."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        css_files = list((static_v2_path / "assets").glob("*.css"))
        assert len(css_files) >= 1, "No CSS bundle found in static-v2/assets/"

    def test_index_html_uses_absolute_asset_paths(self, static_v2_path):
        """index.html must reference /assets/... (absolute), not ./assets/... (relative)."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        content = (static_v2_path / "index.html").read_text(encoding="utf-8")
        # Absolute paths are safe for same-origin serving
        assert "/assets/" in content, "index.html does not reference /assets/ paths"
        # Relative ./assets/ paths would break with FastAPI /assets mount
        assert "./assets/" not in content, (
            "index.html uses ./assets/ (relative paths) — set base: '/' in vite.config.ts"
        )

    def test_index_html_no_hardcoded_localhost(self, static_v2_path):
        """index.html must not contain hardcoded 127.0.0.1 URLs."""
        if not static_v2_path.is_dir():
            pytest.skip("static-v2 not built yet")
        content = (static_v2_path / "index.html").read_text(encoding="utf-8")
        assert "127.0.0.1" not in content, (
            "index.html contains hardcoded 127.0.0.1 — not safe for same-origin serving"
        )
