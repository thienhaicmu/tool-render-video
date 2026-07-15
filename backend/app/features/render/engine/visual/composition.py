"""
composition.py — GĐ4a: deterministic character COMPOSITION geometry.

One shared source of layout truth for both places that put characters on screen:
  * svg_compose.compose_visual  — characters composed INTO a key-visual
  * beat_render                 — per-beat/per-line character OVERLAYS over the base

What it decides (pure math, no AI, no I/O):
  * layout templates  — per character-count slots (x-fraction, scale, flip)
  * FACING            — side characters are MIRRORED to face the scene centre, so a
                        two-character dialogue looks AT each other instead of both
                        staring at the camera
  * aspect reflow     — portrait (9:16) tightens x and shrinks characters so two
                        figures don't collide in the narrow frame
  * hook safe-anchor  — the on-screen hook text picks the top corner FURTHEST from
                        the occupied character slots (never covers a face)

Never raises; unknown inputs fall back to the landscape defaults.
"""
from __future__ import annotations

# slot: (x_frac, scale_mult, flip). ``scale_mult`` multiplies the caller's base
# character height fraction; ``flip`` mirrors horizontally (face the centre).
_LAYOUTS_LANDSCAPE: dict = {
    1: [(0.50, 1.00, False)],
    2: [(0.34, 0.86, False), (0.66, 0.86, True)],
    3: [(0.18, 0.70, False), (0.50, 0.74, False), (0.82, 0.70, True)],
}
_LAYOUTS_PORTRAIT: dict = {
    1: [(0.50, 1.00, False)],
    2: [(0.29, 0.74, False), (0.71, 0.74, True)],
    3: [(0.17, 0.58, False), (0.50, 0.64, False), (0.83, 0.58, True)],
}

# overlay anchor slot → (x_frac, flip). Right-anchored characters mirror so a
# left/right dialogue pair faces inward.
_ANCHOR_LANDSCAPE = {"left": (0.20, False), "center": (0.50, False), "right": (0.80, True)}
_ANCHOR_PORTRAIT = {"left": (0.25, False), "center": (0.50, False), "right": (0.75, True)}

# portrait frames can't hold landscape-sized figures side by side.
PORTRAIT_SCALE_MULT = 0.85


def is_portrait(width: int, height: int) -> bool:
    try:
        return int(height) > int(width)
    except Exception:
        return False


def layout_slots(n_chars: int, width: int, height: int) -> "list[tuple]":
    """[(x_frac, scale_mult, flip)] for ``n_chars`` figures composed into a scene."""
    table = _LAYOUTS_PORTRAIT if is_portrait(width, height) else _LAYOUTS_LANDSCAPE
    n = max(1, min(3, int(n_chars or 1)))
    return list(table.get(n, table[3]))


def anchor_slot(anchor: str, width: int, height: int) -> "tuple[float, bool]":
    """(x_frac, flip) for an overlay anchor token (left|center|right)."""
    table = _ANCHOR_PORTRAIT if is_portrait(width, height) else _ANCHOR_LANDSCAPE
    return table.get((anchor or "center").strip().lower(), table["center"])


def overlay_scale_mult(width: int, height: int) -> float:
    """Multiplier applied to the overlay char-height fraction (portrait reflow)."""
    return PORTRAIT_SCALE_MULT if is_portrait(width, height) else 1.0


def choose_hook_anchor(occupied: "set[str]", requested: str = "auto") -> str:
    """Pick where the hook text sits given the character slots in use.

    An EXPLICIT author choice (top/bottom/left/right) is respected. ``auto`` (and
    ``bottom`` — characters stand on the ground there) resolves to the top corner
    furthest from the occupied slots:
      only left occupied  → top_right;  only right → top_left;
      centre (or both sides) occupied → top (centre);  nothing occupied → auto.
    Returns one of: auto | top | bottom | left | right | top_left | top_right —
    the extended tokens are RENDER-INTERNAL (beat_render._anchor_xy), never stored
    on the plan (TEXT_ANCHOR enum unchanged)."""
    req = (requested or "auto").strip().lower()
    occ = {a for a in (occupied or set()) if a in ("left", "center", "right")}
    if req in ("top", "left", "right"):
        return req
    if not occ:
        return req if req == "auto" else "top"
    if occ == {"left"}:
        return "top_right"
    if occ == {"right"}:
        return "top_left"
    return "top"


__all__ = ["layout_slots", "anchor_slot", "overlay_scale_mult", "choose_hook_anchor",
           "is_portrait", "PORTRAIT_SCALE_MULT"]
