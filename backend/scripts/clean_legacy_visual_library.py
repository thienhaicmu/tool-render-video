"""Safely remove the obsolete on-disk asset library after V3 materialization."""
from __future__ import annotations

import argparse
import sqlite3
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LEGACY = DATA / "asset_library"
CHAR_MANIFEST = DATA / "visual_library_v3_legacy_characters_approved_pilot.json"
SCENE_MANIFEST = DATA / "visual_library_v3_legacy_scenes_approved_pilot.json"
DB_PATH = DATA / "app.db"


def _legacy_db_rows() -> int:
    if not DB_PATH.is_file():
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        marker = "%asset_library%"
        return int(conn.execute(
            "SELECT COUNT(*) FROM story_assets WHERE path LIKE ?", (marker,)
        ).fetchone()[0])


def _prune_db() -> int:
    if not DB_PATH.is_file():
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        marker = "%asset_library%"
        cursor = conn.execute("DELETE FROM story_assets WHERE path LIKE ?", (marker,))
        return int(cursor.rowcount)


def clean(*, confirm: bool = False, prune_db: bool = False) -> None:
    if not LEGACY.exists():
        print(f"legacy_library=absent path={LEGACY}")
    else:
        for path in (CHAR_MANIFEST, SCENE_MANIFEST):
            if not path.is_file():
                raise RuntimeError(f"refusing cleanup; missing V3 manifest: {path}")
            load_manifest(path)
        resolved = LEGACY.resolve()
        if resolved.parent != DATA.resolve() or resolved.name != "asset_library":
            raise RuntimeError(f"refusing cleanup outside data/asset_library: {resolved}")
        files = list(resolved.rglob("*"))
        print(f"legacy_library=ready path={resolved} entries={len(files)}")
        if confirm:
            shutil.rmtree(resolved)
            print(f"removed={resolved}")
    db_rows = _legacy_db_rows()
    if db_rows:
        print(f"legacy_db_rows={db_rows} db={DB_PATH}")
        if confirm and prune_db:
            print(f"removed_db_rows={_prune_db()}")
    if not confirm:
        print("dry_run=true pass --confirm to remove the legacy library")
    elif prune_db is False and db_rows:
        print("db_prune_skipped=true pass --prune-db to remove stale asset rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove the obsolete data/asset_library after V3 validation")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--prune-db", action="store_true", help="remove story_assets rows pointing to asset_library")
    args = parser.parse_args()
    clean(confirm=args.confirm, prune_db=args.prune_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
