# Story `scene_spec` — declarative procedural background (PASTE-JSON only)

> Instruction file for producing `scene_spec` input. A `scene_spec` lets a NEW scene be
> **described by drawing parameters** — the engine renders it to SVG and **banks it into
> the offline asset library** (reused next time). No AI, offline, $0. Only the paste-JSON
> render path (`story_source="paste_json"`) reads it; the AI never emits it.
>
> Renderer: `backend/app/features/render/engine/visual/svg_scene_spec.py`
> (`render_scene_spec` + `bank_scene_spec`). Wired in `story_pipeline_v2.py` (paste_json
> only) → sets `setting.asset = slug`; the existing `_bg_layer` flow is UNCHANGED.

---

## Where it goes

Inside each `settings[]` entry of a StoryPlan JSON. `scene_spec` is OPTIONAL:
- present → engine renders it + banks it as a background asset, and uses it;
- absent / `{}` → old flow (fuzzy `scene_kind` token → procedural) — untouched.

```jsonc
{
  "id": "station",
  "name": "雨が降る川口駅前",
  "scene_kind": "",          // ignored when scene_spec is present
  "asset": "",               // may hold the slug name instead of scene_spec.slug
  "scene_spec": { ...see below... }
}
```

## Canvas & rules
- Canvas is fixed **1536 × 1024** (16:9). Origin = top-left, **y grows downward**.
- All numbers are in canvas units; all colours are hex (`#rrggbb` / `#rgb`).
- `elements` are drawn **in order** — later elements paint on top.
- Any missing/invalid value is skipped safely (never breaks the SVG). `path.d` and colours
  are sanitised against injection.

## `scene_spec` shape

```jsonc
{
  "slug": "jp_hiendai_kawaguchi_station",   // REQUIRED to bank — the library file name you choose
                                            //   (falls back to setting.asset, then setting.id)
  "bg":    { "top": "#39435c", "bottom": "#20283a" },   // gradient top→bottom (solid: top==bottom)
  //  OR multi-stop:  "bg": { "stops": [[0,"#39435c"],[0.5,"#2a3348"],[1,"#20283a"]] }
  "floor": { "y": 700, "color": "#454d5e", "edge": "#f2c94a" },   // optional ground band + highlight edge
  "night": false,                                                 // optional dark-blue tint overlay
  "elements": [ /* see element types */ ]
}
```

## Element types (each object has `type`)

| `type` | Fields | Notes |
|--------|--------|-------|
| `rect` | `x,y,w,h,fill` · `rx?` (corner radius) · `opacity?` · `stroke?`,`width?` | walls, cars, tables, machines |
| `circle` | `cx,cy,r,fill` · `opacity?` | moon, round light |
| `ellipse` | `cx,cy,rx,ry,fill` · `opacity?` | glow, chandelier |
| `line` | `x1,y1,x2,y2,stroke` · `width?` · `opacity?` | rain, rails, wires |
| `path` | `d` (SVG path string) · `fill?`/`stroke?`,`width?` · `opacity?` | roofs, mountains, free shapes |
| `polygon` | `points: [[x,y],…]` · `fill` · `opacity?` · `stroke?`,`width?` | triangular/faceted shapes |
| `row` | `of: {element without x}` · `xs: [..]` · `y?` | repeat one element across x positions |
| `grid` | `of: {element}` · `xs: [..]` · `ys: [..]` | repeat across an x×y grid |
| `group` | `x?,y?,scale?` · `children: [elements]` | translate/scale a sub-drawing |

## Full example — rainy Kawaguchi station front

```jsonc
"scene_spec": {
  "slug": "jp_hiendai_kawaguchi_station",
  "bg":    { "top": "#39435c", "bottom": "#20283a" },
  "floor": { "y": 700, "color": "#454d5e", "edge": "#f2c94a" },
  "night": false,
  "elements": [
    { "type": "rect",    "x": 0,   "y": 170, "w": 1536, "h": 54,  "fill": "#2a3346" },
    { "type": "row",     "of": { "type": "rect", "y": 224, "w": 24, "h": 470, "fill": "#333d52" }, "xs": [188,508,828,1148,1468] },
    { "type": "rect",    "x": 120, "y": 470, "w": 1000, "h": 230, "rx": 20, "fill": "#6b7788" },
    { "type": "rect",    "x": 150, "y": 500, "w": 940,  "h": 86,  "rx": 10, "fill": "#a9cbe0", "opacity": 0.7 },
    { "type": "row",     "of": { "type": "rect", "y": 600, "w": 120, "h": 80, "fill": "#39435c" }, "xs": [190,400,610,820,1030] },
    { "type": "line",    "x1": 60, "y1": 200, "x2": 20, "y2": 700, "stroke": "#aeb8cc", "width": 2, "opacity": 0.22 }
  ]
}
```

## Banking (auto)
On a `paste_json` render, each setting's `scene_spec` is:
1. rendered → PNG (1536×1024),
2. saved to `ASSET_LIBRARY_DIR/background/{plan.region}/{plan.genre_key}/{slug}.png`,
3. registered in the `story_assets` DB (kind=`background`, your `slug`),
4. `setting.asset` is set to `slug` → the normal library/`_bg_layer` render uses it.

Idempotent: a slug already banked (file on disk) is reused, not re-rendered — so you can
build up a library of reusable named backgrounds by describing each scene once.

## Guidance for producing input
- Keep 4–8 elements per scene — flat, readable silhouettes (this is a stylised flat look,
  not a photo). Use `row`/`grid` for repetition (windows, columns, machines, rain).
- Pick a `bg` gradient that sets the mood (night blues, warm interior, grey rain).
- Name `slug` as `{region}_{genre}_{place}` (e.g. `jp_hiendai_pachinko`) so the growing
  library stays organised.
