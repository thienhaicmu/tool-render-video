"""
lottie_pack.py — LOTTIE character-pack engine (GĐ2 Visual Foundation, hướng A).

A style pack = a folder of designer-made Lottie JSON animations (bought/downloaded,
e.g. LottieFiles character packs) + a ``pack.json`` manifest that maps them onto the
engine's vocabulary:

    STYLE_PACKS_DIR/{pack_id}/
      pack.json           # manifest (see docs/STYLE_PACK_SPEC.md)
      anims/*.json        # the Lottie files

The engine RECOLORS each animation per character identity (CharacterLook) by
replacing the pack's declared palette colours (solid fills/strokes; static colors),
then renders offline via rlottie-python:

  * ``render_master``  — one still RGBA PNG (Review preview / static composite)
  * ``render_frames``  — an RGBA PNG sequence for a cue's duration (looped/held),
                         content-addressed cache under CACHE_DIR/lottie_renders

rlottie-python is an OPTIONAL dependency: everything degrades to None/[] when it is
missing (Sacred Contract #3 spirit — a missing renderer never breaks startup).
NOT wired into the render pipeline yet (GĐ2 gate: sample approval first).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from app.core.config import APP_DATA_DIR, CACHE_DIR
from app.features.render.engine.visual.v2.look_spec import CharacterLook, derive_look, shade

logger = logging.getLogger("app.render.visual.lottie_pack")

_RENDER_CACHE = CACHE_DIR / "lottie_renders"

try:
    from rlottie_python import LottieAnimation as _LottieAnimation
    _RLOTTIE = True
except Exception:                                     # pragma: no cover - env dependent
    _LottieAnimation = None  # type: ignore[assignment]
    _RLOTTIE = False


def available() -> bool:
    return _RLOTTIE


def packs_dir() -> Path:
    return Path(os.getenv("STYLE_PACKS_DIR", str(APP_DATA_DIR / "style_packs")))


# ── manifest ──────────────────────────────────────────────────────────────────
class LottiePack:
    def __init__(self, pack_id: str, root: Path, manifest: dict) -> None:
        self.id = pack_id
        self.root = root
        self.name = str(manifest.get("name") or pack_id)
        self.desc = str(manifest.get("desc") or "")
        self.fps = float(manifest.get("fps") or 30.0)
        self.actions: dict = manifest.get("actions") if isinstance(manifest.get("actions"), dict) else {}
        self.emotions: dict = manifest.get("emotions") if isinstance(manifest.get("emotions"), dict) else {}
        self.colors: dict = manifest.get("colors") if isinstance(manifest.get("colors"), dict) else {}

    def resolve_action(self, pose: str, emotion: str) -> "Optional[dict]":
        """emotion override → pose action → '*' fallback. Entry: {file, loop?}."""
        for key in ((emotion or "").strip().lower(), ""):
            e = self.emotions.get(key) if key else None
            if isinstance(e, dict) and e.get("file"):
                return e
        for key in ((pose or "").strip().lower(), "*"):
            a = self.actions.get(key)
            if isinstance(a, dict) and a.get("file"):
                return a
        return None


def list_packs() -> "list[dict]":
    """[{id, name, desc}] for every installed pack with a readable manifest."""
    out: list = []
    try:
        base = packs_dir()
        if not base.exists():
            return out
        for d in sorted(base.iterdir()):
            mf = d / "pack.json"
            if not (d.is_dir() and mf.exists()):
                continue
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                out.append({"id": d.name, "name": str(m.get("name") or d.name),
                            "desc": str(m.get("desc") or "")})
            except Exception as exc:
                logger.warning("lottie_pack: bad manifest %s: %s", mf, exc)
    except Exception as exc:
        logger.warning("lottie_pack: list failed: %s", exc)
    return out


def load_pack(pack_id: str) -> Optional[LottiePack]:
    try:
        pid = (pack_id or "").strip()
        root = packs_dir() / pid
        mf = root / "pack.json"
        if not mf.exists():
            return None
        return LottiePack(pid, root, json.loads(mf.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning("lottie_pack: load %s failed: %s", pack_id, exc)
        return None


# ── recolor ───────────────────────────────────────────────────────────────────
def _hex_of(rgb: "list[float]") -> str:
    try:
        r, g, b = (max(0.0, min(1.0, float(x))) for x in rgb[:3])
        return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"
    except Exception:
        return ""


def _rgb_of(hex_color: str) -> "list[float]":
    h = (hex_color or "").lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _slot_color(look: CharacterLook, slot: str) -> str:
    return {
        "hair": look.hair_color, "skin": look.skin, "eye": look.eye_color,
        "outfit_primary": look.outfit_primary, "outfit_secondary": look.outfit_secondary,
        "accent": look.accent,
    }.get(slot, "")


def _build_replacements(colors: dict, look: CharacterLook) -> "dict[str, list[float]]":
    """pack palette hex → target rgb floats. Entry: hex → [slot, factor] | slot."""
    rep: dict = {}
    for src, spec in (colors or {}).items():
        try:
            if isinstance(spec, (list, tuple)) and spec:
                slot, factor = str(spec[0]), float(spec[1] if len(spec) > 1 else 1.0)
            else:
                slot, factor = str(spec), 1.0
            base = _slot_color(look, slot)
            if not base:
                continue
            rep[str(src).strip().lower()] = _rgb_of(shade(base, factor))
        except Exception:
            continue
    return rep


def _recolor_node(node: Any, rep: dict) -> None:
    """Walk a Lottie tree replacing STATIC solid fill/stroke colours ("c":{"k":[r,g,b,(a)]})
    whose value matches a declared pack colour. Animated colours and gradients are left
    untouched (v1 — most character kits use flat fills)."""
    if isinstance(node, dict):
        c = node.get("c")
        if (node.get("ty") in ("fl", "st") and isinstance(c, dict)
                and not c.get("a") and isinstance(c.get("k"), list) and len(c["k"]) >= 3
                and all(isinstance(x, (int, float)) for x in c["k"][:3])):
            tgt = rep.get(_hex_of(c["k"]))
            if tgt:
                alpha = c["k"][3:4]
                c["k"] = list(tgt) + list(alpha)
        for v in node.values():
            _recolor_node(v, rep)
    elif isinstance(node, list):
        for v in node:
            _recolor_node(v, rep)


def _load_recolored(pack: LottiePack, entry: dict, look: CharacterLook) -> "Optional[tuple[str, dict]]":
    """(recolored json string, meta) for an action entry. None on any failure."""
    try:
        f = pack.root / str(entry.get("file") or "")
        if not f.exists():
            logger.warning("lottie_pack[%s]: missing anim %s", pack.id, f)
            return None
        data = json.loads(f.read_text(encoding="utf-8"))
        rep = _build_replacements(pack.colors, look)
        if rep:
            _recolor_node(data, rep)
        return json.dumps(data, separators=(",", ":")), data
    except Exception as exc:
        logger.warning("lottie_pack[%s]: recolor failed: %s", pack.id, exc)
        return None


# ── rendering ─────────────────────────────────────────────────────────────────
def _cache_key(pack: LottiePack, entry: dict, look: CharacterLook,
               width: int, height: int, fps: float, duration_sec: float) -> str:
    try:
        f = pack.root / str(entry.get("file") or "")
        mt = f.stat().st_mtime_ns if f.exists() else 0
        raw = json.dumps([pack.id, str(entry.get("file")), mt, look.to_dict(),
                          width, height, round(fps, 3), round(duration_sec, 3)],
                         sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    except Exception:
        return hashlib.sha1(os.urandom(8)).hexdigest()[:20]


def render_master(pack_id: str, look, *, emotion: str = "neutral", pose: str = "stand",
                  out_path: "str | Path", width: int = 1024, height: int = 1536,
                  frame: "int | None" = None) -> Optional[str]:
    """One still RGBA PNG of the (recolored) character — Review master / static
    composite / contact sheet. ``frame=None`` → the animation's mid frame (usually a
    representative extended pose). Never raises."""
    if not _RLOTTIE:
        return None
    try:
        lk = look if isinstance(look, CharacterLook) else derive_look(0, base=dict(look or {}))
        pack = load_pack(pack_id)
        if pack is None:
            return None
        entry = pack.resolve_action(pose, emotion)
        if entry is None:
            return None
        rc = _load_recolored(pack, entry, lk)
        if rc is None:
            return None
        anim = _LottieAnimation.from_data(rc[0])
        try:
            total = max(1, int(anim.lottie_animation_get_totalframe()))
            fno = (total // 2) if frame is None else max(0, min(total - 1, int(frame)))
            im = anim.render_pillow_frame(frame_num=fno, width=int(width), height=int(height))
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(str(out))
        finally:
            try:
                anim.lottie_animation_destroy()
            except Exception:
                pass
        return str(out) if Path(out_path).exists() else None
    except Exception as exc:
        logger.warning("lottie_pack[%s]: render_master failed: %s", pack_id, exc)
        return None


def render_frames(pack_id: str, look, *, pose: str = "stand", emotion: str = "neutral",
                  duration_sec: float, fps: float = 30.0,
                  width: int = 512, height: int = 768) -> "list[str]":
    """RGBA PNG sequence covering ``duration_sec`` at ``fps`` (looped when the entry
    says so, else held on the last frame). Content-addressed cache — a cue re-render
    with the same identity/size reuses the frames. Returns [] on any failure."""
    if not _RLOTTIE:
        return []
    try:
        lk = look if isinstance(look, CharacterLook) else derive_look(0, base=dict(look or {}))
        pack = load_pack(pack_id)
        if pack is None:
            return []
        entry = pack.resolve_action(pose, emotion)
        if entry is None:
            return []
        n_out = max(1, int(round(float(duration_sec) * float(fps))))
        key = _cache_key(pack, entry, lk, width, height, fps, duration_sec)
        seq_dir = _RENDER_CACHE / f"{pack.id}_{key}"
        done_flag = seq_dir / ".done"
        if done_flag.exists():
            frames = sorted(str(p) for p in seq_dir.glob("f_*.png"))
            if len(frames) >= n_out:
                return frames[:n_out]
        rc = _load_recolored(pack, entry, lk)
        if rc is None:
            return []
        anim = _LottieAnimation.from_data(rc[0])
        try:
            total = max(1, int(anim.lottie_animation_get_totalframe()))
            src_fps = float(anim.lottie_animation_get_framerate() or pack.fps or 30.0)
            loop = bool(entry.get("loop", True))
            seq_dir.mkdir(parents=True, exist_ok=True)
            rendered: dict[int, "Any"] = {}
            for i in range(n_out):
                src = int(round(i * src_fps / float(fps)))
                fno = (src % total) if loop else min(src, total - 1)
                if fno not in rendered:
                    rendered[fno] = anim.render_pillow_frame(
                        frame_num=fno, width=int(width), height=int(height))
                rendered[fno].save(str(seq_dir / f"f_{i:05d}.png"))
            done_flag.write_text("ok", encoding="utf-8")
        finally:
            try:
                anim.lottie_animation_destroy()
            except Exception:
                pass
        return sorted(str(p) for p in seq_dir.glob("f_*.png"))[:n_out]
    except Exception as exc:
        logger.warning("lottie_pack[%s]: render_frames failed: %s", pack_id, exc)
        return []


def char_image_inner(pack_id: str, look, emotion: str = "neutral", pose: str = "stand",
                     facing: str = "front") -> str:
    """styles.py contract adapter: the character as an embedded <image> on the
    1024×1536 frame (base64 PNG master) so Lottie packs plug into every existing
    SVG composite / preview path. '' on failure. Never raises."""
    try:
        import base64
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = render_master(pack_id, look, emotion=emotion, pose=pose,
                              out_path=Path(td) / "m.png", width=1024, height=1536)
            if not p:
                return ""
            b64 = base64.b64encode(Path(p).read_bytes()).decode("ascii")
        img = (f'<image href="data:image/png;base64,{b64}" x="0" y="0" '
               f'width="1024" height="1536"/>')
        if facing == "left":
            img = f'<g transform="translate(1024,0) scale(-1,1)">{img}</g>'
        return img
    except Exception as exc:
        logger.warning("lottie_pack[%s]: char_image_inner failed: %s", pack_id, exc)
        return ""


__all__ = ["available", "packs_dir", "list_packs", "load_pack", "LottiePack",
           "render_master", "render_frames", "char_image_inner"]
