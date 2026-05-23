"""Phase 4F.5C: verify upload domain code (route file, platform_repo, upload DB functions) removed."""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
STATIC_DIR = BACKEND_ROOT / "static"


# ── Deleted files ─────────────────────────────────────────────────────────────

class TestUploadFilesDeleted:
    def test_routes_upload_py_deleted(self):
        assert not (APP_ROOT / "routes" / "upload.py").exists(), (
            "routes/upload.py still exists — expected deleted in Phase 4F.5C"
        )

    def test_upload_engine_py_deleted(self):
        assert not (APP_ROOT / "services" / "upload_engine.py").exists(), (
            "services/upload_engine.py still exists — expected deleted in Phase 4F.5B"
        )

    def test_platform_repo_py_deleted(self):
        assert not (APP_ROOT / "db" / "platform_repo.py").exists(), (
            "app/db/platform_repo.py still exists — expected deleted in Phase 4F.5C"
        )


# ── services/db.py no longer exposes upload functions ─────────────────────────

class TestServicesDbNoUploadFunctions:
    _upload_symbols = [
        "_default_upload_profiles_root",
        "normalize_profile_path_value",
        "build_default_upload_profile_path",
        "ensure_upload_account_profile_path_fields",
        "_normalize_upload_account_row",
        "_normalize_upload_video_row",
        "_normalize_upload_queue_row",
        "_normalize_upload_history_row",
        "_normalize_upload_scheduler_state_row",
        "_active_profile_conflict_statuses",
        "list_active_runtime_locks",
        "_set_account_lock_state",
        "release_upload_runtime_locks_for_queue",
        "acquire_upload_runtime_lock",
        "enrich_upload_account_runtime_state",
        "list_upload_account_rows",
        "get_upload_account_row",
        "get_upload_account",
        "find_upload_account_profile_conflict",
        "create_upload_account_row",
        "update_upload_account_row",
        "disable_upload_account_row",
        "get_upload_scheduler_state",
        "update_upload_scheduler_state",
        "increment_upload_scheduler_running_count",
        "create_upload_video_row",
        "list_upload_video_rows",
        "get_upload_video_row",
        "get_upload_video",
        "update_upload_video_row",
        "disable_upload_video_row",
        "add_upload_queue_item",
        "list_upload_queue",
        "get_upload_queue_item",
        "update_upload_queue_item",
        "set_upload_queue_last_error",
        "update_upload_queue_status",
        "mark_upload_queue_uploading",
        "mark_upload_queue_success",
        "mark_upload_queue_failed",
        "cancel_upload_queue_item",
        "insert_upload_history",
        "list_upload_history",
    ]

    _proxy_symbols = [
        "_normalize_proxy_pool_row",
        "create_proxy_pool_row",
        "delete_proxy_pool_row",
        "get_proxy_pool_row",
        "list_proxy_pool_rows",
        "update_proxy_pool_row",
    ]

    @classmethod
    def setup_class(cls):
        import app.services.db as db_mod
        cls._db_mod = db_mod

    def test_no_upload_symbols_in_services_db(self):
        for sym in self._upload_symbols:
            assert not hasattr(self._db_mod, sym), (
                f"services/db.py still exposes upload symbol: {sym}"
            )

    def test_no_proxy_symbols_in_services_db(self):
        for sym in self._proxy_symbols:
            assert not hasattr(self._db_mod, sym), (
                f"services/db.py still exposes proxy/platform symbol: {sym}"
            )

    def test_upload_constants_not_in_services_db(self):
        assert not hasattr(self._db_mod, "UPLOAD_PROFILE_LOCK_TTL_MINUTES"), (
            "services/db.py still re-exports UPLOAD_PROFILE_LOCK_TTL_MINUTES"
        )
        assert not hasattr(self._db_mod, "UPLOAD_SCHEDULER_STATE_ID"), (
            "services/db.py still re-exports UPLOAD_SCHEDULER_STATE_ID"
        )

    def test_live_symbols_still_present(self):
        """Non-upload re-exports must still exist in services/db.py."""
        for sym in ("get_conn", "init_db", "close_thread_conn",
                    "upsert_job", "get_job", "list_jobs", "delete_job",
                    "get_creator_prefs", "upsert_creator_prefs"):
            assert hasattr(self._db_mod, sym), (
                f"services/db.py is missing live symbol: {sym}"
            )


# ── No app code imports dead modules ─────────────────────────────────────────

class TestNoAppImportsDeadModules:
    def test_routes_upload_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.routes.upload")
            raise AssertionError("app.routes.upload imported successfully — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass

    def test_upload_engine_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.services.upload_engine")
            raise AssertionError("app.services.upload_engine imported successfully — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass

    def test_platform_repo_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.db.platform_repo")
            raise AssertionError("app.db.platform_repo imported successfully — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass


# ── /api/upload routes remain absent ─────────────────────────────────────────

class TestUploadRoutesAbsent:
    def test_no_upload_routes_registered(self):
        """Verify old /api/upload/* domain routes are absent.

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
            f"Found {len(upload_routes)} /api/upload/ route(s) still registered"
        )


# ── Static files: no /api/upload fetch calls ─────────────────────────────────

class TestStaticNoUploadApiFetches:
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

