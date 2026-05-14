# Premium Creator Workstation V1 SVG Import

This folder contains an importable SVG mockup for the frontend rebuild direction.

## Files

- `premium_creator_workstation_v1.svg` - large SVG canvas with the product mockup frames.
- `design_tokens_v1.json` - visual token reference used by the SVG.

## How To Import Into Figma

1. Open Figma.
2. Create or open a design file.
3. Drag `premium_creator_workstation_v1.svg` onto the Figma canvas.
4. Wait for Figma to finish importing the grouped SVG layers.
5. Review the frames in the imported canvas.

Alternative:

1. In Figma, choose `File -> Place image`.
2. Select `premium_creator_workstation_v1.svg`.
3. Click on the canvas to place it.

## What The SVG Contains

The SVG includes twelve 1440x900 desktop frames arranged in a grid:

1. Cover / Product Principles
2. Source
3. Studio
4. Monitor
5. Results
6. Library
7. Downloads
8. Publish Advanced
9. System
10. States + Errors
11. Engineering Handoff
12. Out of Scope

The mockup follows the locked rebuild contracts:

- Source prepares source sessions.
- Studio owns `RenderRequest` draft creation.
- Monitor owns `Job` and `JobPart` progress.
- Results owns `ResultPackage`, ranked outputs, best clip, summaries, warnings, and recovery.
- Library owns history re-entry.
- Downloads owns standalone download jobs.
- Publish Advanced owns implemented upload automation only.
- System owns local runtime readiness.

## Limitations

- This is a visual SVG mockup.
- It is not a true Figma component library.
- It does not contain Figma auto-layout.
- It is not frontend implementation code.
- SVG text and shapes may import differently depending on Figma import behavior.
- Interactive states are represented visually, not wired as prototypes.

## Next Step

Review the visual direction and product hierarchy. After approval, convert the accepted frames into real Figma components, variants, auto-layout frames, and implementation handoff specs.
