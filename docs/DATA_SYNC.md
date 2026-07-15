# Runtime Data Sync

`data/` is runtime state and is intentionally excluded from Git. This means a
clone can have identical code but different Story projects, SQLite state, and
V3 artwork. Use `scripts/sync_data.py` to copy that state without importing the
application or starting a server.

## Portable sync

Stop the app on both machines, then run from the source clone:

```powershell
python scripts/sync_data.py `
  --source D:\tool-render-video `
  --destination D:\tool-render-video-other `
  --profile portable
```

Portable sync includes:

- `data/visual_library_v3/` and all V3 manifests;
- `data/app.db` and `data/ai_memory.db` using a consistent SQLite snapshot;
- BGM, uploads, state, AI memory, and asset library files.

It excludes render history, Story plan runs, database backups, derived caches,
logs, temporary files, downloaded model caches, installers, and cookies. This
is the recommended profile for a clean second clone.

## Full sync

```powershell
python scripts/sync_data.py `
  --source D:\tool-render-video `
  --destination D:\tool-render-video-other `
  --profile full
```

Add `--include-sensitive` only when cookies are intentionally transferable:

```powershell
python scripts/sync_data.py --source D:\tool-render-video `
  --destination D:\tool-render-video-other --profile full --include-sensitive
```

The tool never copies `.env`, API keys, virtual environments, Node modules,
frontend builds, or files outside `data/`. It writes a checksum manifest at
`<destination>\data\.data-sync-manifest.json`. Use `--no-verify` only when a
full multi-gigabyte model copy makes checksum verification impractical.

The source and destination must be different project roots. Existing files at
the destination are replaced atomically one by one; files excluded by the
selected profile are left untouched.

## Clean runtime history first

To keep only master/project data on the source machine before syncing:

```powershell
python scripts/clean_runtime_data.py --project D:\tool-render-video
python scripts/clean_runtime_data.py --project D:\tool-render-video --confirm
```

The first command is a dry run. The confirmed command deletes render jobs,
job parts, download history, scores, feedback, runtime cache, temp/log/report
directories, old database backups, and Story plan-run traces. It preserves the
V3 library, manifests, asset library, BGM, Story projects, and AI memory. A
SQLite backup is created in `.runtime-cleanup-backups/`, outside `data/`, before
the database is cleaned. Use `--include-model-caches` to also remove large
Whisper/HuggingFace/Torch/font caches.
