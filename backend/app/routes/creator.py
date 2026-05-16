from fastapi import APIRouter
from pydantic import BaseModel
from app.services.db import get_creator_prefs, upsert_creator_prefs

router = APIRouter()


class _PrefsBody(BaseModel):
    prefs: dict = {}


@router.get("/api/creator/preferences")
def api_get_creator_prefs():
    return {"prefs": get_creator_prefs()}


@router.put("/api/creator/preferences")
def api_put_creator_prefs(body: _PrefsBody):
    saved = upsert_creator_prefs(body.prefs)
    return {"prefs": saved}
