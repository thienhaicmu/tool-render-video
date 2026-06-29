VOICE_PROFILES = {
    "vi-VN": {
        "language": "vi-VN",
        "label": "Vietnamese",
        "female_voice": "vi-VN-HoaiMyNeural",
        "male_voice": "vi-VN-NamMinhNeural",
    },
    "ja-JP": {
        "language": "ja-JP",
        "label": "Japanese",
        "female_voice": "ja-JP-NanamiNeural",
        "male_voice": "ja-JP-KeitaNeural",
    },
    "en-US": {
        "language": "en-US",
        "label": "English US",
        "female_voice": "en-US-JennyNeural",
        "male_voice": "en-US-GuyNeural",
    },
    "en-GB": {
        "language": "en-GB",
        "label": "English UK",
        "female_voice": "en-GB-SoniaNeural",
        "male_voice": "en-GB-RyanNeural",
    },
    "ko-KR": {
        "language": "ko-KR",
        "label": "Korean",
        "female_voice": "ko-KR-SunHiNeural",
        "male_voice": "ko-KR-InJoonNeural",
    },
}

VOICE_LIST = {
    "vi-VN": [
        {"id": "vi-VN-HoaiMyNeural",  "label": "HoaiMy",  "gender": "female", "recommended_use": "natural, storytelling"},
        {"id": "vi-VN-NamMinhNeural", "label": "NamMinh", "gender": "male",   "recommended_use": "authoritative, news"},
    ],
    "ja-JP": [
        {"id": "ja-JP-NanamiNeural", "label": "Nanami", "gender": "female", "recommended_use": "warm, conversational"},
        {"id": "ja-JP-AoiNeural",    "label": "Aoi",    "gender": "female", "recommended_use": "bright, casual"},
        {"id": "ja-JP-MayuNeural",   "label": "Mayu",   "gender": "female", "recommended_use": "gentle, narration"},
        {"id": "ja-JP-KeitaNeural",  "label": "Keita",  "gender": "male",   "recommended_use": "professional"},
        {"id": "ja-JP-DaichiNeural", "label": "Daichi", "gender": "male",   "recommended_use": "energetic, casual"},
        {"id": "ja-JP-NaokiNeural",  "label": "Naoki",  "gender": "male",   "recommended_use": "calm, news"},
    ],
    "en-US": [
        # Newer conversational neural voices — markedly more natural / less
        # robotic than the older Jenny/Guy. Listed first as the recommended set.
        {"id": "en-US-AvaNeural",    "label": "Ava",    "gender": "female", "recommended_use": "natural, expressive (recommended)"},
        {"id": "en-US-AndrewNeural", "label": "Andrew", "gender": "male",   "recommended_use": "natural, warm (recommended)"},
        {"id": "en-US-EmmaNeural",   "label": "Emma",   "gender": "female", "recommended_use": "casual, friendly"},
        {"id": "en-US-BrianNeural",  "label": "Brian",  "gender": "male",   "recommended_use": "calm, conversational"},
        # Multilingual variants — same natural timbre, handle code-switching.
        {"id": "en-US-AvaMultilingualNeural",    "label": "Ava (Multilingual)",    "gender": "female", "recommended_use": "natural, multilingual"},
        {"id": "en-US-AndrewMultilingualNeural", "label": "Andrew (Multilingual)", "gender": "male",   "recommended_use": "natural, multilingual"},
        # Original voices — kept for backward compatibility / preference.
        {"id": "en-US-JennyNeural", "label": "Jenny", "gender": "female", "recommended_use": "friendly, conversational"},
        {"id": "en-US-AriaNeural",  "label": "Aria",  "gender": "female", "recommended_use": "expressive, engaging"},
        {"id": "en-US-GuyNeural",   "label": "Guy",   "gender": "male",   "recommended_use": "professional"},
        {"id": "en-US-DavisNeural", "label": "Davis", "gender": "male",   "recommended_use": "podcast, documentary"},
    ],
    "en-GB": [
        {"id": "en-GB-SoniaNeural",  "label": "Sonia",  "gender": "female", "recommended_use": "clear, authoritative"},
        {"id": "en-GB-LibbyNeural",  "label": "Libby",  "gender": "female", "recommended_use": "casual, warm"},
        {"id": "en-GB-MaisieNeural", "label": "Maisie", "gender": "female", "recommended_use": "youthful, friendly"},
        {"id": "en-GB-RyanNeural",   "label": "Ryan",   "gender": "male",   "recommended_use": "documentary, narration"},
        {"id": "en-GB-ThomasNeural", "label": "Thomas", "gender": "male",   "recommended_use": "calm, measured"},
        {"id": "en-GB-OliverNeural", "label": "Oliver", "gender": "male",   "recommended_use": "formal, professional"},
    ],
    "ko-KR": [
        {"id": "ko-KR-SunHiNeural",  "label": "SunHi",  "gender": "female", "recommended_use": "warm, conversational"},
        {"id": "ko-KR-JiMinNeural",  "label": "JiMin",  "gender": "female", "recommended_use": "bright, casual"},
        {"id": "ko-KR-SeoHyeonNeural", "label": "SeoHyeon", "gender": "female", "recommended_use": "soft, narration"},
        {"id": "ko-KR-InJoonNeural", "label": "InJoon", "gender": "male",   "recommended_use": "professional"},
        {"id": "ko-KR-HyunsuMultilingualNeural", "label": "Hyunsu (Multilingual)", "gender": "male", "recommended_use": "natural, multilingual"},
        {"id": "ko-KR-GookMinNeural", "label": "GookMin", "gender": "male",  "recommended_use": "energetic, casual"},
    ],
}

# Flat lookup: voice_id → voice entry (all languages)
_ALL_VOICES: dict[str, dict] = {
    v["id"]: v
    for lang_voices in VOICE_LIST.values()
    for v in lang_voices
}


def get_voice_profiles() -> dict:
    return VOICE_PROFILES


def get_voice_list() -> dict:
    return VOICE_LIST


def resolve_voice_profile(language: str, gender: str, voice_id: str | None = None) -> dict:
    profile = VOICE_PROFILES.get(str(language or "").strip())
    if not profile:
        raise ValueError(f"Unsupported narration language: {language!r}")

    if voice_id:
        voice_id = str(voice_id).strip()
        matched = _ALL_VOICES.get(voice_id)
        if not matched:
            valid = ", ".join(sorted(_ALL_VOICES))
            raise ValueError(f"Unsupported voice_id {voice_id!r}. Valid options: {valid}")
        return {
            "language": profile["language"],
            "label": profile["label"],
            "gender": matched["gender"],
            "voice_id": voice_id,
        }

    # Fallback: existing language + gender behavior (backward compat)
    normalized_gender = str(gender or "").strip().lower()
    if normalized_gender not in {"female", "male"}:
        raise ValueError("Unsupported narration voice gender")
    voice_key = f"{normalized_gender}_voice"
    return {
        "language": profile["language"],
        "label": profile["label"],
        "gender": normalized_gender,
        "voice_id": profile[voice_key],
    }
