import os
import sys
from pathlib import Path

import uvicorn


def _ensure_packaged_import_paths():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

    candidates = [
        base,
        base.parent,
        Path(__file__).resolve().parent,
        Path.cwd(),
    ]

    for p in candidates:
        if (p / "app").exists():
            sys.path.insert(0, str(p))
            return


_ensure_packaged_import_paths()

from app.main import app  # noqa: E402


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()