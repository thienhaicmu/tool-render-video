"""Phase 4F.5A: verify upload entry points are removed from main.py and static frontend."""
import importlib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = BACKEND_ROOT / "static"


# ── Backend: router registration ─────────────────────────────────────────────

class TestMainNoUploadRouter:
    def test_upload_router_not_imported(self):
        """routes.upload must not be imported by main."""
        import app.main as main_mod
        assert not hasattr(main_mod, "upload_router"), (
            "upload_router should have been removed from main.py"
        )

    def test_upload_router_not_registered(self):
        """FastAPI app must not expose any /api/upload/* domain routes.

        NOTE: /api/upload-file (POST, Phase 5.1) is intentionally excluded from
        this check — it is a single editor utility endpoint, NOT a restoration of
        the old /api/upload/* upload domain. Only routes under /api/upload/ (with
        trailing slash) constitute the old domain.
        """
        import app.main as main_mod
        upload_routes = [
            r for r in main_mod.app.routes
            if hasattr(r, "path") and r.path.startswith("/api/upload/")
        ]
        assert upload_routes == [], (
            f"Found {len(upload_routes)} /api/upload/ route(s) still registered: "
            + ", ".join(r.path for r in upload_routes)
        )

    def test_non_upload_routers_still_registered(self):
        """Render, jobs, channels, and other core routes must still be present."""
        import app.main as main_mod
        paths = {r.path for r in main_mod.app.routes if hasattr(r, "path")}
        expected_prefixes = ["/api/render", "/api/jobs", "/api/channels"]
        for prefix in expected_prefixes:
            assert any(p.startswith(prefix) for p in paths), (
                f"Expected route prefix {prefix!r} missing from app routes"
            )


# ── Frontend: index.html script tags ─────────────────────────────────────────

class TestIndexHtmlNoUploadScripts:
    _html: str = ""

    @classmethod
    def setup_class(cls):
        index_path = STATIC_DIR / "index.html"
        assert index_path.exists(), f"index.html not found at {index_path}"
        cls._html = index_path.read_text(encoding="utf-8")

    def test_upload_manager_js_not_loaded(self):
        assert "upload-manager.js" not in self._html, (
            "upload-manager.js script tag still present in index.html"
        )

    def test_upload_config_js_not_loaded(self):
        assert "upload-config.js" not in self._html, (
            "upload-config.js script tag still present in index.html"
        )

    def test_upload_engine_js_not_loaded(self):
        assert "upload-engine.js" not in self._html, (
            "upload-engine.js script tag still present in index.html"
        )


# ── Frontend: JS files deleted ───────────────────────────────────────────────

class TestUploadJsFilesDeleted:
    def test_upload_manager_js_deleted(self):
        assert not (STATIC_DIR / "js" / "upload-manager.js").exists(), (
            "upload-manager.js still exists on disk — expected deleted"
        )

    def test_upload_config_js_deleted(self):
        assert not (STATIC_DIR / "js" / "upload-config.js").exists(), (
            "upload-config.js still exists on disk — expected deleted"
        )

    def test_upload_engine_js_deleted(self):
        assert not (STATIC_DIR / "js" / "upload-engine.js").exists(), (
            "upload-engine.js still exists on disk — expected deleted"
        )
