"""CLIP semantic scene scoring (OQ-5.3).

OpenCLIP ViT-B-32 — additive semantic signal per scene.
Gate: CLIP_SCORING_ENABLED=0 fully disables and returns scenes unchanged.
"""
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CLIP_SCORING_ENABLED: bool = os.environ.get("CLIP_SCORING_ENABLED", "1") == "1"
CLIP_SCORER_VERSION = "1"  # bump when prompts or model change to bust score cache

_POSITIVE_PROMPTS = [
    "a person reacting with surprise or excitement",
    "a product demonstration showing how something works",
    "a before and after transformation reveal",
    "a person showing strong positive emotion",
    "a presentation or screen reveal moment",
    "close-up of an interesting product or object",
    "an energetic action-filled moment",
    "a person looking directly at the camera with engagement",
]

_NEGATIVE_PROMPTS = [
    "an empty room with nothing happening",
    "a static or frozen frame with no action",
    "a dark underexposed blurry shot",
    "a person looking away with no engagement",
]

_CLIP_BONUS_SCALE = 30.0
_CLIP_BONUS_MIN = -8.0
_CLIP_BONUS_MAX = 20.0

# Lazy singleton state — populated on first call to _load_clip_model().
_clip_state: dict = {
    "loaded": False,
    "model": None,
    "preprocess": None,
    "device": None,
    "pos_feats": None,
    "neg_feats": None,
}


def _load_clip_model() -> dict:
    if _clip_state["loaded"]:
        return _clip_state
    _clip_state["loaded"] = True
    if not CLIP_SCORING_ENABLED:
        return _clip_state
    try:
        import torch
        import open_clip  # type: ignore[import]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        model.eval()
        model = model.half().to(device) if device == "cuda" else model.to(device)

        with torch.no_grad():
            pos_tokens = tokenizer(_POSITIVE_PROMPTS).to(device)
            neg_tokens = tokenizer(_NEGATIVE_PROMPTS).to(device)
            pos_feats = model.encode_text(pos_tokens)
            pos_feats = pos_feats / pos_feats.norm(dim=-1, keepdim=True)
            neg_feats = model.encode_text(neg_tokens)
            neg_feats = neg_feats / neg_feats.norm(dim=-1, keepdim=True)

        _clip_state.update({
            "model": model,
            "preprocess": preprocess,
            "device": device,
            "pos_feats": pos_feats,
            "neg_feats": neg_feats,
        })
        logger.info(
            "clip_scorer_loaded model=ViT-B-32 device=%s pos=%d neg=%d",
            device, len(_POSITIVE_PROMPTS), len(_NEGATIVE_PROMPTS),
        )
    except Exception as exc:
        logger.info("clip_scorer_unavailable reason=%s", exc)
    return _clip_state


def _score_frame_clip(frame_bgr, state: dict) -> Optional[float]:
    """Score one BGR frame. Returns cosine similarity delta in [-1, 1] or None."""
    try:
        import torch
        from PIL import Image  # type: ignore[import]

        frame_rgb = Image.fromarray(frame_bgr[..., ::-1])
        img_tensor = state["preprocess"](frame_rgb).unsqueeze(0).to(state["device"])
        if state["device"] == "cuda":
            img_tensor = img_tensor.half()
        with torch.no_grad():
            img_feat = state["model"].encode_image(img_tensor)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            pos_sim = (img_feat @ state["pos_feats"].T).mean().item()
            neg_sim = (img_feat @ state["neg_feats"].T).mean().item()
        return float(pos_sim - neg_sim)
    except Exception:
        return None


def _sample_scene_frames(video_path: str, start: float, end: float, n_frames: int) -> list:
    """Extract n_frames BGR frames evenly spaced across [start, end]."""
    import cv2  # type: ignore[import]

    frames: list = []
    duration = max(end - start, 0.1)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return frames
    try:
        for i in range(n_frames):
            t = start + duration * (i + 1) / (n_frames + 1)
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)
    finally:
        cap.release()
    return frames


def score_scenes_clip(video_path: str, scenes: List[Dict]) -> List[Dict]:
    """Enrich scene dicts with ``clip_semantic_score`` in [−8, +20].

    Returns scenes unchanged when CLIP_SCORING_ENABLED=0 or on any load failure.
    Per-frame and per-scene failures degrade gracefully to 0.0.
    """
    if not CLIP_SCORING_ENABLED or not scenes:
        return scenes

    state = _load_clip_model()
    if state["model"] is None:
        return scenes

    enriched: List[Dict] = []
    for sc in scenes:
        start = float(sc.get("start", 0.0))
        end = float(sc.get("end", start))
        duration = end - start
        n = 1 if duration < 3.0 else (2 if duration < 8.0 else 3)
        frames = _sample_scene_frames(video_path, start, end, n_frames=n)
        if not frames:
            enriched.append({**sc, "clip_semantic_score": 0.0})
            continue
        raw_scores = [_score_frame_clip(f, state) for f in frames]
        valid = [s for s in raw_scores if s is not None]
        if not valid:
            enriched.append({**sc, "clip_semantic_score": 0.0})
            continue
        raw = sum(valid) / len(valid)
        bonus = max(_CLIP_BONUS_MIN, min(_CLIP_BONUS_MAX, raw * _CLIP_BONUS_SCALE))
        enriched.append({**sc, "clip_semantic_score": round(bonus, 3)})

    _clip_active = any(sc.get("clip_semantic_score", 0.0) != 0.0 for sc in enriched)
    logger.info("clip_scoring_complete scenes=%d active=%s", len(enriched), _clip_active)
    return enriched
