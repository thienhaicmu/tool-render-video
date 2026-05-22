"""Phase 4F.6: DB import audit — verify post-upload-removal module structure is clean."""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"


# ── Module imports succeed ─────────────────────────────────────────────────────

class TestDbModulesImportClean:
    def test_connection_imports(self):
        import app.db.connection  # noqa: F401

    def test_jobs_repo_imports(self):
        import app.db.jobs_repo  # noqa: F401

    def test_creator_repo_imports(self):
        import app.db.creator_repo  # noqa: F401

    def test_services_db_imports(self):
        import app.services.db  # noqa: F401


# ── services/db.py live symbol surface ────────────────────────────────────────

class TestServicesDbLiveSymbols:
    _expected = [
        # connection
        "get_conn", "init_db", "close_thread_conn",
        # jobs_repo
        "upsert_job", "get_job", "list_jobs", "list_jobs_page",
        "delete_job", "update_job_progress",
        "upsert_job_part", "list_job_parts", "list_job_parts_bulk",
        # creator_repo
        "get_creator_prefs", "upsert_creator_prefs",
    ]

    @classmethod
    def setup_class(cls):
        import app.services.db as db_mod
        cls._db = db_mod

    def test_all_live_symbols_present(self):
        for sym in self._expected:
            assert hasattr(self._db, sym), f"services/db.py missing live symbol: {sym}"


# ── services/db.py exposes no upload / proxy / platform names ─────────────────

class TestServicesDbNoDeadSymbols:
    _upload_prefixes = ("upload", "Upload", "UPLOAD")
    _proxy_prefixes = ("proxy", "Proxy")
    _platform_prefixes = ("platform", "Platform")

    @classmethod
    def setup_class(cls):
        import app.services.db as db_mod
        cls._names = [n for n in dir(db_mod) if not n.startswith("__")]

    def test_no_upload_names(self):
        hits = [n for n in self._names if any(n.startswith(p) or p.lower() in n.lower()
                for p in ("upload",))]
        assert hits == [], f"services/db.py exposes upload symbols: {hits}"

    def test_no_proxy_names(self):
        hits = [n for n in self._names if any(n.startswith(p) for p in self._proxy_prefixes)]
        assert hits == [], f"services/db.py exposes proxy symbols: {hits}"

    def test_no_platform_names_from_upload_domain(self):
        # platform_repo was the upload-domain proxy pool module; must be absent
        assert not hasattr(__import__("app.services.db", fromlist=["x"]), "platform_repo"), (
            "services/db.py still re-exports platform_repo"
        )
        platform_hits = [n for n in self._names if "platform_repo" in n]
        assert platform_hits == [], f"services/db.py exposes platform_repo symbols: {platform_hits}"

    def test_no_upload_constants(self):
        import app.services.db as db_mod
        assert not hasattr(db_mod, "UPLOAD_PROFILE_LOCK_TTL_MINUTES"), (
            "UPLOAD_PROFILE_LOCK_TTL_MINUTES still in services/db.py"
        )
        assert not hasattr(db_mod, "UPLOAD_SCHEDULER_STATE_ID"), (
            "UPLOAD_SCHEDULER_STATE_ID still in services/db.py"
        )


# ── Deleted files are absent (filesystem + import) ────────────────────────────

class TestDeletedFilesAbsent:
    def test_platform_repo_file_deleted(self):
        assert not (APP_ROOT / "db" / "platform_repo.py").exists(), (
            "app/db/platform_repo.py exists — expected deleted in Phase 4F.5C"
        )

    def test_routes_upload_file_deleted(self):
        assert not (APP_ROOT / "routes" / "upload.py").exists(), (
            "app/routes/upload.py exists — expected deleted in Phase 4F.5C"
        )

    def test_upload_engine_file_deleted(self):
        assert not (APP_ROOT / "services" / "upload_engine.py").exists(), (
            "app/services/upload_engine.py exists — expected deleted in Phase 4F.5B"
        )

    def test_platform_repo_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.db.platform_repo")
            raise AssertionError("app.db.platform_repo imported — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass

    def test_routes_upload_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.routes.upload")
            raise AssertionError("app.routes.upload imported — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass

    def test_upload_engine_not_importable(self):
        import importlib
        try:
            importlib.import_module("app.services.upload_engine")
            raise AssertionError("app.services.upload_engine imported — file should be deleted")
        except (ImportError, ModuleNotFoundError):
            pass
