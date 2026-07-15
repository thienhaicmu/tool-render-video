# Visual Library V3 Portable Package

This directory stores the binary-free V3 source manifests. Generated SVG/PNG
artifacts stay in `data/`, which is runtime data and is intentionally ignored by
Git.

After cloning the repository, run from `backend/`:

```powershell
.\.venv\Scripts\python.exe scripts/materialize_visual_library_v3.py
```

The command recreates the V3 character and scene artifacts and writes the
validated runtime manifests under `data/visual_library_v3*`. Story Mode then
uses those manifests through the relative paths in `.env.example`.

The default runtime is V3-only:

```text
STORY_V3_MATCHING=1
STORY_V3_ONLY=1
```

The old `data/asset_library` is not required. To remove it from an existing
machine after materialization, run:

```powershell
.\.venv\Scripts\python.exe scripts/clean_legacy_visual_library.py --confirm --prune-db
```
