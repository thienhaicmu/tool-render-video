# AI Clip Studio Figma Template

Generated from `D:\ai_clip_studio_v2_redesign_figma.js` as a cleaner reusable template.

## Output

- `ai_clip_studio_figma_template.js`

## What Changed From The Original

- Converted the one-off generator into a smaller editable template.
- Added a clear `CONFIG` block.
- Added reusable `TOKENS`.
- Added `SCREENS` data so frames can be added/removed without rewriting drawing logic.
- Added component-style helper functions:
  - `mkFrame`
  - `rect`
  - `text`
  - `mkPanel`
  - `rowItem`
  - `noteCard`
  - `previewPanel`
- Preserved the intent of:
  - cover
  - tokens
  - components
  - source
  - studio
  - monitor
  - results
  - engineering handoff

## How To Use

1. Open Figma Desktop.
2. Create a development plugin.
3. Use `ai_clip_studio_figma_template.js` as the plugin `code.js`.
4. Run the plugin.

## MCP Notes

For Figma MCP `use_figma`, adjust:

- Remove the outer `(async () => { ... })();` wrapper if the MCP runner wraps code.
- Replace `figma.currentPage = page` with `await figma.setCurrentPageAsync(page)`.
- Replace `figma.notify(...)` with `return { ... }`.

## Why This Template Exists

The original file is good for generating a complete visual pass, but it is large and hard to edit. This template is better for future iteration because the product screens are data-driven and the visual helpers are centralized.
