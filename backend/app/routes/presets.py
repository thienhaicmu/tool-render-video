"""
routes/presets.py — Render Preset REST endpoints.

GET    /api/presets                        list (filter: platform, channel_code)
GET    /api/presets/{preset_id}            get one
POST   /api/presets                        create custom preset
PUT    /api/presets/{preset_id}            update custom preset
DELETE /api/presets/{preset_id}            delete custom preset (403 for built-ins)

Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.presets_repo import (
    create_preset,
    delete_preset,
    get_preset,
    list_presets,
    update_preset,
)
from app.domain.render_preset import PRESET_ALLOWED_PARAMS

router = APIRouter(prefix="/api/presets", tags=["presets"])


# ── Request schemas ───────────────────────────────────────────────────────────

class PresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=300)
    platform: str = Field("", max_length=40)
    channel_code: str = Field("", max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)


class PresetUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=300)
    params: dict[str, Any] = Field(default_factory=dict)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def get_presets(platform: str = "", channel_code: str = ""):
    """List all presets matching the optional platform/channel filters."""
    presets = list_presets(platform=platform.strip(), channel_code=channel_code.strip())
    return {"presets": [p.to_dict() for p in presets]}


@router.get("/{preset_id}")
def get_preset_by_id(preset_id: str):
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")
    return preset.to_dict()


@router.post("", status_code=201)
def create_new_preset(body: PresetCreate):
    _validate_params(body.params)
    preset_id = str(uuid.uuid4())
    create_preset(
        preset_id=preset_id,
        name=body.name.strip(),
        params=body.params,
        description=body.description.strip(),
        channel_code=body.channel_code.strip(),
        platform=body.platform.strip(),
    )
    preset = get_preset(preset_id)
    return preset.to_dict() if preset else {"preset_id": preset_id}


@router.put("/{preset_id}")
def update_existing_preset(preset_id: str, body: PresetUpdate):
    existing = get_preset(preset_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")
    if existing.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in presets cannot be modified")
    _validate_params(body.params)
    update_preset(
        preset_id=preset_id,
        name=body.name.strip(),
        params=body.params,
        description=body.description.strip(),
    )
    preset = get_preset(preset_id)
    return preset.to_dict() if preset else {}


@router.delete("/{preset_id}", status_code=204)
def remove_preset(preset_id: str):
    existing = get_preset(preset_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")
    if existing.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in presets cannot be deleted")
    delete_preset(preset_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_params(params: dict) -> None:
    unknown = set(params.keys()) - PRESET_ALLOWED_PARAMS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown preset params: {sorted(unknown)}. "
                   f"Allowed: {sorted(PRESET_ALLOWED_PARAMS)}",
        )
