from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request

from app.core.devtools_safety import is_loopback_client
from app.services.dev_commands import execute_dev_command


router = APIRouter(prefix="/api/dev", tags=["devtools"])


class DevCommandRequest(BaseModel):
    command: str


@router.post("/command")
def run_dev_command(payload: DevCommandRequest, request: Request):
    # Layer 2 defense-in-depth: reject requests that did not originate from a
    # loopback peer. The primary gate is in app.main (refuses to mount the
    # router on non-loopback bind), but this request-time check covers any
    # future code path that bypasses the import-time gate.
    client = request.client
    if not is_loopback_client(client.host if client else None):
        raise HTTPException(
            status_code=403,
            detail="devtools is loopback-only; refusing non-localhost origin",
        )
    try:
        return execute_dev_command(payload.command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e}")
