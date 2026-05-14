# Premium Creator Workstation V1 Figma JS Generator

This file is a rerunnable Figma Plugin API generator for the Premium Creator Workstation V1 design direction.

## Files

- `premium_creator_workstation_v1.figma.js` - Figma Plugin API script.
- `design_tokens_v1.json` - token reference shared with the SVG mockup.
- `premium_creator_workstation_v1.svg` - static importable SVG mockup.

## How To Run In Figma

Use this as plugin code inside a Figma plugin development setup:

1. In Figma Desktop, create a local plugin manifest.
2. Set the plugin `main` script to `premium_creator_workstation_v1.figma.js`, or paste the script content into your local plugin main file.
3. Run the plugin from `Plugins -> Development`.
4. The script creates pages, design tokens, component frames, screen frames, states, and annotation panels.

For Codex/Figma MCP use, the script can also be adapted by removing the final `figma.closePlugin(...)` call and returning the `result` object from the MCP wrapper.

## What It Generates

The generator creates:

- Cover / Product Principles
- Source
- Studio
- Monitor
- Results
- Library
- Downloads
- Publish Advanced
- System
- States + Errors
- Engineering Handoff
- Out of Scope

It also creates visual component groups for:

- Navigation
- Workspace Shell
- Media Preview
- Source Components
- Studio Controls
- Monitor Components
- Result Components
- Ranking Components
- Library Components
- Download Components
- Publish Components
- System Components
- Forms
- Feedback
- Errors
- Progress
- AI State Indicators
- Diagnostics
- Status Chips
- Output Cards
- Result Ranking Cards

## Limitations

- This is a Figma generator, not production frontend code.
- It does not create live application behavior.
- It does not call backend APIs.
- It does not use external images or fonts beyond Figma font loading.
- If the connected Figma plan limits page count, run with `PAGE_MODE = "sections"` in the script.

## Implementation Mapping

The generated annotations map screen ownership to implemented contracts:

- Source -> `SourceSession`, `/api/render/prepare-source`
- Studio -> `RenderDraft`, `RenderRequest`, subtitle/voice/viral preview APIs
- Monitor -> `Job`, `JobPart`, WebSocket plus polling fallback
- Results -> `ResultPackage`, `OutputClip`, `AIInsightSummary`
- Library -> history job references
- Downloads -> download job and item statuses
- Publish Advanced -> upload automation only
- System -> warmup, AI diagnostics, desktop adapter readiness

Unsupported features are generated only on the Out of Scope page.
