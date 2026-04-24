from fastapi import APIRouter

from app.services.voice_profiles import get_voice_profiles, get_voice_list


router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/profiles")
def get_voice_profile_catalog():
    profiles = get_voice_profiles()
    voice_list = get_voice_list()
    items = []
    for lang_code, profile in profiles.items():
        items.append({
            **profile,
            "voices": voice_list.get(lang_code, []),
        })
    return {"items": items}
