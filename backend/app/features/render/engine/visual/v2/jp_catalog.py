"""Curated Japanese character/background starter library for offline Story Mode.

This module is data-first: the role id is stable, the visual identity is derived
from that id, and the scene recommendation is explicit.  Japanese keywords are
primary; English and Chinese aliases support the two secondary markets.
"""
from __future__ import annotations

import re

from app.features.render.engine.visual.v2.look_spec import derive_look, stable_seed


def _role(role_id: str, era: str, label_ja: str, label_en: str, gender: str,
          outfit: str, scene_id: str, *, age: str = "adult", keywords=()) -> dict:
    return {
        "id": role_id, "era": era, "label_ja": label_ja, "label_en": label_en,
        "gender": gender, "age": age, "outfit": outfit, "scene_id": scene_id,
        "keywords": tuple(keywords),
    }


JP_ROLES = (
    _role("jp_police_man", "modern", "男性警察官", "Male police officer", "male", "police_uniform", "police_office", keywords=("警察", "警官", "police", "officer", "警察官")),
    _role("jp_police_woman", "modern", "女性警察官", "Female police officer", "female", "police_uniform", "police_office", keywords=("警察", "婦警", "policewoman", "officer", "女警")),
    _role("jp_doctor_man", "modern", "男性医師", "Male doctor", "male", "doctor_coat", "hospital", keywords=("医師", "医者", "doctor", "physician", "医生")),
    _role("jp_doctor_woman", "modern", "女性医師", "Female doctor", "female", "doctor_coat", "hospital", keywords=("医師", "女医", "doctor", "physician", "医生")),
    _role("jp_engineer_man", "modern", "男性エンジニア", "Male engineer", "male", "engineer_workwear", "laboratory", keywords=("技師", "エンジニア", "engineer", "technician", "工程师")),
    _role("jp_engineer_woman", "modern", "女性エンジニア", "Female engineer", "female", "engineer_workwear", "laboratory", keywords=("技師", "エンジニア", "engineer", "technician", "工程师")),
    _role("jp_student_boy", "modern", "男子高校生", "Male student", "male", "school_uniform", "classroom", keywords=("高校生", "学生", "student", "schoolboy", "男学生")),
    _role("jp_student_girl", "modern", "女子高校生", "Female student", "female", "school_uniform", "classroom", keywords=("高校生", "学生", "student", "schoolgirl", "女学生")),
    _role("jp_ceo_man", "modern", "男性社長", "Male CEO", "male", "office_suit", "executive_office", keywords=("社長", "会長", "ceo", "president", "总裁", "总经理")),
    _role("jp_ceo_woman", "modern", "女性社長", "Female CEO", "female", "office_suit", "executive_office", keywords=("社長", "女性経営者", "ceo", "director", "女总裁")),
    _role("jp_mother_in_law", "modern", "義母", "Mother-in-law", "female", "kimono", "living_room", age="elder", keywords=("義母", "姑", "mother-in-law", "mother in law", "婆婆")),
    _role("jp_daughter_in_law", "modern", "嫁", "Daughter-in-law", "female", "dress", "living_room", keywords=("嫁", "義理の娘", "daughter-in-law", "daughter in law", "儿媳")),
    _role("jp_teacher_man", "modern", "男性教師", "Male teacher", "male", "office_suit", "classroom", keywords=("教師", "先生", "teacher", "professor", "老师")),
    _role("jp_teacher_woman", "modern", "女性教師", "Female teacher", "female", "office_suit", "classroom", keywords=("教師", "先生", "teacher", "professor", "老师")),
    _role("jp_cafe_owner", "modern", "喫茶店の店主", "Cafe owner", "female", "apron_staff", "cafe", age="elder", keywords=("喫茶店", "店主", "cafe owner", "barista", "咖啡店老板")),
    _role("jp_store_clerk", "modern", "コンビニ店員", "Convenience-store clerk", "male", "apron_staff", "convenience_store", keywords=("コンビニ", "店員", "clerk", "cashier", "便利店店员")),
    _role("jp_samurai", "historical", "侍", "Samurai", "male", "armor_light", "traditional_house", keywords=("侍", "武士", "samurai", "warrior", "武士")),
    _role("jp_onna_bugeisha", "historical", "女武芸者", "Onna-musha", "female", "armor_light", "shrine", keywords=("女武芸者", "女武者", "onna-musha", "woman warrior", "女武士")),
    _role("jp_daimyo", "historical", "大名", "Daimyo", "male", "kimono", "castle_hall", age="elder", keywords=("大名", "殿様", "daimyo", "lord", "领主")),
    _role("jp_miko", "historical", "巫女", "Shrine maiden", "female", "kimono", "shrine", keywords=("巫女", "神社", "miko", "shrine maiden", "巫女")),
    _role("jp_geisha", "historical", "芸者", "Geisha", "female", "kimono", "traditional_house", keywords=("芸者", "芸妓", "geisha", "performer", "艺伎")),
    _role("jp_merchant", "historical", "商人", "Merchant", "male", "kimono", "street", keywords=("商人", "問屋", "merchant", "trader", "商人")),
    _role("jp_innkeeper", "historical", "旅籠の女将", "Innkeeper", "female", "apron_staff", "traditional_house", age="elder", keywords=("女将", "旅籠", "innkeeper", "hostess", "旅店老板娘")),
    _role("jp_ninja", "historical", "忍者", "Ninja", "male", "coat_long", "forest", keywords=("忍者", "忍び", "ninja", "shinobi", "忍者")),
)


JP_BACKGROUNDS = (
    {"id": "jp_urban_street", "scene": "street", "era": "modern", "label_ja": "日本の街路", "keywords": ("道路", "街", "street", "road", "街道")},
    {"id": "jp_police_office", "scene": "police_office", "era": "modern", "label_ja": "警察署", "keywords": ("警察署", "交番", "police station", "警察局")},
    {"id": "jp_hospital", "scene": "hospital", "era": "modern", "label_ja": "病院", "keywords": ("病院", "診察室", "hospital", "clinic", "医院")},
    {"id": "jp_engineering_lab", "scene": "laboratory", "era": "modern", "label_ja": "研究室", "keywords": ("研究室", "実験室", "laboratory", "workshop", "实验室")},
    {"id": "jp_classroom", "scene": "classroom", "era": "modern", "label_ja": "教室", "keywords": ("教室", "学校", "classroom", "school", "教室")},
    {"id": "jp_family_living_room", "scene": "living_room", "era": "modern", "label_ja": "居間", "keywords": ("居間", "リビング", "living room", "home", "客厅")},
    {"id": "jp_executive_office", "scene": "executive_office", "era": "modern", "label_ja": "社長室", "keywords": ("社長室", "役員室", "executive office", "ceo office", "总裁办公室")},
    {"id": "jp_train_station", "scene": "train_station", "era": "modern", "label_ja": "駅", "keywords": ("駅", "ホーム", "station", "platform", "车站")},
    {"id": "jp_convenience_store", "scene": "convenience_store", "era": "modern", "label_ja": "コンビニ", "keywords": ("コンビニ", "売店", "convenience store", "shop", "便利店")},
    {"id": "jp_cafe", "scene": "cafe", "era": "modern", "label_ja": "喫茶店", "keywords": ("喫茶店", "カフェ", "cafe", "coffee shop", "咖啡店")},
    {"id": "jp_shrine", "scene": "shrine", "era": "historical", "label_ja": "神社", "keywords": ("神社", "鳥居", "shrine", "temple", "神社")},
    {"id": "jp_traditional_house", "scene": "traditional_house", "era": "historical", "label_ja": "和室", "keywords": ("和室", "古民家", "traditional house", "ryokan", "和室")},
)

_ROLE_BY_ID = {item["id"]: item for item in JP_ROLES}
_BG_BY_ID = {item["id"]: item for item in JP_BACKGROUNDS}


def get_role(role_id: str) -> dict | None:
    return _ROLE_BY_ID.get((role_id or "").strip().lower())


def role_look(role_id: str):
    spec = get_role(role_id) or JP_ROLES[0]
    seed = stable_seed(spec["id"])
    natural_hair = ("#26221f", "#302720", "#3a2c24", "#4a352a", "#5a4030")
    elder_hair = ("#817e79", "#a7a39d", "#d5d1ca", "#e8e6e2")
    eyes = ("#2e2620", "#3b2d24", "#4a3524", "#5a4030")
    base = {
        "hair_color": (elder_hair if spec["age"] == "elder" else natural_hair)[
            seed % (len(elder_hair) if spec["age"] == "elder" else len(natural_hair))
        ],
        "eye_color": eyes[(seed // 7) % len(eyes)],
    }
    return derive_look(spec["id"], gender=spec["gender"], age=spec["age"],
                       outfit=spec["outfit"], base=base)


def background_for_role(role_id: str) -> dict:
    spec = get_role(role_id) or JP_ROLES[0]
    for bg in JP_BACKGROUNDS:
        if bg["scene"] == spec["scene_id"]:
            return bg
    return {"id": f'jp_{spec["scene_id"]}', "scene": spec["scene_id"],
            "era": spec["era"], "label_ja": spec["scene_id"], "keywords": ()}


def search_roles(query: str, *, era: str = "", limit: int = 8) -> list[dict]:
    """Small deterministic JA/EN/ZH offline matcher used before any AI call."""
    q = re.sub(r"\s+", " ", (query or "").strip().lower())
    tokens = tuple(x for x in re.split(r"[\s,;/|]+", q) if x)
    ranked = []
    for idx, item in enumerate(JP_ROLES):
        if era and item["era"] != era:
            continue
        hay = " ".join((item["id"], item["label_ja"], item["label_en"], *item["keywords"])).lower()
        score = sum(5 if token == item["id"] else 2 if token in hay else 0 for token in tokens)
        if not q or q in hay:
            score += 4 if q else 1
        if score:
            ranked.append((-score, idx, item))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [item for _, _, item in ranked[:max(1, int(limit or 8))]]


__all__ = [
    "JP_ROLES", "JP_BACKGROUNDS", "get_role", "role_look", "background_for_role",
    "search_roles",
]
