"""Phase 4F.5B: verify upload_engine is removed and channels.py no longer depends on it."""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
STATIC_DIR = BACKEND_ROOT / "static"


# ── upload_engine.py deleted ─────────────────────────────────────────────────

class TestUploadEngineFileDeleted:
    def test_upload_engine_py_deleted(self):
        assert not (APP_ROOT / "services" / "upload_engine.py").exists(), (
            "upload_engine.py still exists — expected deleted in Phase 4F.5B"
        )


# ── channels.py has no upload_engine import ──────────────────────────────────

class TestChannelsNoUploadEngineImport:
    _src: str = ""

    @classmethod
    def setup_class(cls):
        channels_path = APP_ROOT / "routes" / "channels.py"
        assert channels_path.exists(), f"channels.py not found at {channels_path}"
        cls._src = channels_path.read_text(encoding="utf-8")

    def test_no_upload_engine_import(self):
        assert "upload_engine" not in self._src, (
            "channels.py still references upload_engine"
        )

    def test_no_load_upload_settings(self):
        assert "load_upload_settings" not in self._src, (
            "channels.py still calls load_upload_settings from upload_engine"
        )

    def test_no_save_upload_settings(self):
        assert "save_upload_settings" not in self._src, (
            "channels.py still calls save_upload_settings from upload_engine"
        )

    def test_no_ensure_upload_account_profile(self):
        assert "ensure_upload_account_profile" not in self._src, (
            "channels.py still calls ensure_upload_account_profile from upload_engine"
        )

    def test_no_bootstrap_portable_runtime(self):
        assert "bootstrap_portable_runtime_for_channel" not in self._src, (
            "channels.py still calls bootstrap_portable_runtime_for_channel from upload_engine"
        )


# ── No app code imports upload_engine ────────────────────────────────────────

class TestNoAppImportsUploadEngine:
    def test_channels_py_does_not_import_upload_engine(self):
        """Import channels module; must not raise ImportError from upload_engine."""
        import importlib
        try:
            mod = importlib.import_module("app.routes.channels")
        except ImportError as e:
            raise AssertionError(f"app.routes.channels raised ImportError: {e}")
        # upload_engine must not be present in channels module namespace
        assert not hasattr(mod, "load_upload_settings"), (
            "load_upload_settings leaked into channels module namespace"
        )
        assert not hasattr(mod, "bootstrap_portable_runtime_for_channel"), (
            "bootstrap_portable_runtime_for_channel leaked into channels module namespace"
        )

    def test_upload_engine_not_importable(self):
        """app.services.upload_engine must not be importable (file deleted)."""
        import importlib
        try:
            importlib.import_module("app.services.upload_engine")
            raise AssertionError(
                "app.services.upload_engine imported successfully — file should be deleted"
            )
        except (ImportError, ModuleNotFoundError):
            pass  # expected


# ── /api/upload routes still absent ──────────────────────────────────────────

class TestUploadRoutesStillAbsent:
    def test_no_upload_routes_registered(self):
        import app.main as main_mod
        upload_routes = [
            r for r in main_mod.app.routes
            if hasattr(r, "path") and r.path.startswith("/api/upload")
        ]
        assert upload_routes == [], (
            f"Found {len(upload_routes)} /api/upload route(s) still registered"
        )


# ── Frontend static: no /api/upload fetch calls in render-engine / render-ui ─

class TestFrontendNoUploadApiFetches:
    def _read(self, filename: str) -> str:
        p = STATIC_DIR / "js" / filename
        assert p.exists(), f"{filename} not found at {p}"
        return p.read_text(encoding="utf-8")

    def test_render_engine_no_upload_api_calls(self):
        src = self._read("render-engine.js")
        assert "/api/upload/" not in src, (
            "render-engine.js still contains /api/upload/ fetch calls"
        )

    def test_render_ui_no_upload_api_calls(self):
        src = self._read("render-ui.js")
        assert "/api/upload/" not in src, (
            "render-ui.js still contains /api/upload/ fetch calls"
        )
