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
- BGM, uploads, Story plan runs, state, backups, and asset library files.

It excludes derived caches, logs, temporary files, downloaded model caches,
installers, and cookies. This is the recommended profile for a second clone.

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
