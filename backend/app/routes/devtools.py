from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.dev_commands import execute_dev_command


router = APIRouter(prefix="/api/dev", tags=["devtools"])


class DevCommandRequest(BaseModel):
    command: str


@router.post("/command")
def run_dev_command(payload: DevCommandRequest):
    try:
        return execute_dev_command(payload.command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e}")

