# Visual Library V3 Active Catalog Handoff

This document records the boundary between approved artwork and future Story
Planner matching.

## Current migration status

- 124 character identities, 620 native framing masters, and 172 legacy artifacts.
- 78 scene identities, 190 scene variants, and 102 legacy artifacts.
- The remastered character and scene manifests pass the structural release gate.
- The explicit JP pilot approval contains 6 active characters and 6 active scenes.
- All other remastered items remain `review` until explicit art-direction approval.

## Handoff contract

`app.features.render.engine.visual.library_v3.active_catalog` loads a validated
manifest and exposes only identities with `quality_state=active`. Legacy aliases
are retained only when their target is active.

The handoff is read-only. It accepts direct identity IDs and exact legacy aliases,
but does not search, score, rank, or infer a Planner character. The existing Story
resolver and renderer remain unchanged until the V3 matching and artifact bridge
are enabled explicitly.

Validate the pilot handoff locally:

```powershell
cd backend
.\\.venv\\Scripts\\python.exe -c "from app.features.render.engine.visual.library_v3 import load_active_catalog; from pathlib import Path; r=Path('..')/'data'; c=load_active_catalog(r/'visual_library_v3_legacy_characters_approved_pilot.json'); s=load_active_catalog(r/'visual_library_v3_legacy_scenes_approved_pilot.json'); print(len(c.characters), len(s.scenes))"
```

Expected output:

```text
6 6
```

## Planner matcher

`library_v3.planner_matcher.match_characters` is the next opt-in stage. It reads
only the active catalog and matches Planner fields such as `archetype`,
`canonical_desc`, `gender` and `age` against the identity metadata.

Matching rules:

- explicit identity ID, legacy alias and existing V3 identity are exact matches;
- gender and age are hard compatibility filters when both sides provide them;
- each active identity can be assigned only once per plan;
- weak matches become `needs_approval`; no candidate becomes `missing`;
- `apply=False` is the default; `apply=True` writes `visual_identity_id` while
  leaving the legacy `asset` slug untouched.

The matcher is not wired into the production Story render yet. The remaining
step is an explicit artifact bridge from V3 identity masters/previews to the
current compositor, followed by an opt-in runtime flag and end-to-end tests.

The exact bridge now exists as
`library_v3.artifact_bridge.resolve_character_preview`. It accepts only an
active identity from the configured manifest and returns its existing preview
path for the requested framing. It does not infer an identity and it returns an
empty result for review or unknown IDs.

Runtime wiring now defaults to the approved JP pilot manifest when it exists:

```text
STORY_V3_MATCHING=1
STORY_V3_CHARACTER_MANIFEST=<absolute path to approved character manifest>
STORY_V3_SCENE_MANIFEST=<absolute path to approved scene manifest>
```

The Story pipeline runs V3 matching before the legacy resolver. Existing legacy
locks and slugs remain compatible, while a matched V3 identity is rendered from
its approved preview. Set `STORY_V3_MATCHING=0` to rollback to legacy matching;
if no approved manifest exists, the legacy path remains the automatic fallback.

Character assignments are stored in `visual_identity_id`; scene assignments are
stored in `visual_scene_identity_id`. Both bridges require an active identity
and return to the legacy path when no approved artifact is available.

## Clone and rebuild

Generated binaries are intentionally not committed. A fresh clone restores the
same library by running:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/materialize_visual_library_v3.py
```

The source manifests live in `assets/visual_library_v3/`; the command rebuilds
all 620 character masters and 190 scene variants under `data/`. Existing
machines can remove the obsolete library and stale database rows with:

```powershell
.\.venv\Scripts\python.exe scripts/clean_legacy_visual_library.py --confirm --prune-db
```
