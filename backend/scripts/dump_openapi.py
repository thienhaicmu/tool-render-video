"""dump_openapi.py — emit the FastAPI app's OpenAPI schema to disk.

Sprint 5.1 (audit 2026-06-02 P1 type-drift follow-up): the frontend
RenderRequest type has historically drifted from the backend Pydantic
schema (audit ledger followup_2, P3-E). This script dumps the live
app.openapi() output so a downstream codegen step (openapi-typescript)
can produce a TypeScript declaration file that the frontend commits.

Drift detection in CI:
  1. Run this script (regenerates backend/openapi.json)
  2. Run `npx openapi-typescript backend/openapi.json -o frontend/src/types/openapi-generated.ts`
  3. `git diff --exit-code frontend/src/types/openapi-generated.ts` — fail
     if the file changed; the engineer must commit the regenerated types.

This script is deliberately side-effect-light — it imports the FastAPI
app, calls .openapi(), writes JSON. No DB writes, no FFmpeg, no warmup.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "openapi.json"),
        help="Output path for the OpenAPI JSON document",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (use 0 or negative for compact output)",
    )
    args = parser.parse_args()

    # Ensure the backend package root is on sys.path when invoked from repo root.
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    # Importing app.main has startup-time side effects (config loading, env
    # var defaults, log handler registration). It does NOT call init_db()
    # or any @app.on_event("startup") hooks — those only fire under uvicorn.
    from app.main import app

    schema = app.openapi()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    indent = args.indent if args.indent and args.indent > 0 else None
    out_path.write_text(
        json.dumps(schema, indent=indent, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"openapi schema written: {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
