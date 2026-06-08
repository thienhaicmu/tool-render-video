/**
 * T1.4 closure regression guard — Audit 2026-06-08 (Batch A V8-B5 +
 * UP26 + UP27 + v2-dead).
 *
 * T1.4 (commit 0a20349) + T1.4 follow-up (commit f2b035f) stripped 21
 * dead intent fields from the wire surface:
 *
 *   Phase-G zombies (11) — ai_director_enabled, ai_auto_cut,
 *     ai_use_semantic_hooks, ai_render_influence_enabled,
 *     ai_beat_pulse_enabled, ai_cloud_enabled, ai_cloud_provider,
 *     ai_cloud_api_key, ai_cloud_model, ai_analysis_mode,
 *     ai_content_driven_selection.
 *
 *   UP26 dead (4) — clip_lock, clip_exclude, structure_bias,
 *     subtitle_emphasis.
 *
 *   UP27 dead (1) — asset_music_profile.
 *
 *   v2 dead (3) — energy_style, output_language, narration_style.
 *
 *   T1.4 follow-up (2) — max_export_parts, part_order.
 *
 * The first 4 Phase-G fields + all 4 UP26 + the UP27 field + the 3 v2
 * dead + the 2 follow-up fields (12 total) were sent by
 * RenderWorkflow.tsx's `buildPayload`. T1.4 removed those lines. This
 * test pins the removals so a future refactor can't silently restore
 * them.
 *
 * The BE-side guard
 * `backend/tests/test_render_request_public_no_dead_fields.py` already
 * pins the Public allow-list. This FE-side guard is complementary:
 * even if the BE Public surface gained the field back, the FE wouldn't
 * send it.
 *
 * (target_duration is KEPT in the FE payload — T2.4 wired it to the
 * LLM prompt. The test explicitly verifies it's still there.)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const WORKFLOW_PATH = join(
  __dirname,
  '..',
  'src',
  'features',
  'clip-studio',
  'render',
  'RenderWorkflow.tsx',
)

const API_TYPES_PATH = join(__dirname, '..', 'src', 'types', 'api.ts')

function readWorkflow(): string {
  return readFileSync(WORKFLOW_PATH, 'utf-8')
}

function readApiTypes(): string {
  return readFileSync(API_TYPES_PATH, 'utf-8')
}

/**
 * Find the `buildPayload`'s payload object body. We scope the search
 * to `const payload: RenderRequest = { ... }` so commits to OTHER
 * parts of the file (e.g., a hint string mentioning a dead field
 * name in passing) don't spuriously fail this guard.
 */
function extractPayloadBody(source: string): string {
  // Match `const payload: RenderRequest = {` then balance braces until
  // the matching `}`. Naive but the payload object doesn't contain
  // nested object literals at the depth this regex traverses, so the
  // first balanced `{...}` block IS the payload.
  const startIdx = source.indexOf('const payload: RenderRequest = {')
  if (startIdx === -1) {
    throw new Error(
      'Could not locate `const payload: RenderRequest = {` in ' +
        'RenderWorkflow.tsx. The buildPayload structure may have ' +
        'been refactored — update this test to match the new shape.',
    )
  }
  // Find the matching close brace by depth counting.
  let depth = 0
  let i = source.indexOf('{', startIdx)
  if (i === -1) throw new Error('Open brace not found after const payload')
  for (; i < source.length; i++) {
    const ch = source[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) {
        return source.slice(startIdx, i + 1)
      }
    }
  }
  throw new Error('Unbalanced braces — could not find end of payload literal')
}

// The fields stripped by T1.4 + follow-up. Each MUST NOT appear as a
// key in `buildPayload`.
const STRIPPED_FIELDS_PHASE_G = [
  'ai_director_enabled',
  'ai_auto_cut',
  'ai_use_semantic_hooks',
  'ai_render_influence_enabled',
  'ai_beat_pulse_enabled',
  // The cloud_* + analysis_mode + content_driven were in the TS
  // interface but never sent by buildPayload. Still guard to catch a
  // future regression.
  'ai_cloud_enabled',
  'ai_cloud_provider',
  'ai_cloud_api_key',
  'ai_cloud_model',
  'ai_analysis_mode',
  'ai_content_driven_selection',
]

// Strategic-1 — Audit 2026-06-08 closure. clip_lock and clip_exclude
// were RESTORED to the wire because the LLM prompt now consumes them
// (ai/llm/prompts.py:_format_range_section). The still-stripped UP26
// dead fields are structure_bias and subtitle_emphasis only.
const STRIPPED_FIELDS_UP26 = [
  'structure_bias',
  'subtitle_emphasis',
]

const STRIPPED_FIELDS_UP27 = ['asset_music_profile']

const STRIPPED_FIELDS_V2 = [
  'energy_style',
  'output_language',
  'narration_style',
]

const STRIPPED_FIELDS_FOLLOWUP = ['max_export_parts', 'part_order']

const ALL_STRIPPED = [
  ...STRIPPED_FIELDS_PHASE_G,
  ...STRIPPED_FIELDS_UP26,
  ...STRIPPED_FIELDS_UP27,
  ...STRIPPED_FIELDS_V2,
  ...STRIPPED_FIELDS_FOLLOWUP,
]

describe('T1.4 — RenderWorkflow.buildPayload omits dead fields', () => {
  it.each(ALL_STRIPPED)(
    'never includes %s as a payload key',
    (field: string) => {
      const payloadBody = extractPayloadBody(readWorkflow())
      // The dead key MUST NOT appear as `<field>:` inside the payload
      // literal. The regex anchors on `<field>:` to ignore the
      // possibility that the field name appears in a comment string
      // (the T1.4 commit kept descriptive comments mentioning the
      // removed names — those are documentation, not payload keys).
      const keyRegex = new RegExp(`(^|\\s|,)${field}\\s*:`)
      // Strip comments first so descriptive comment text doesn't trip
      // the assertion. Single-line `//` comments are the only kind
      // inside the payload literal.
      const codeOnly = payloadBody
        .split('\n')
        .map((line) => {
          const slashIdx = line.indexOf('//')
          return slashIdx === -1 ? line : line.slice(0, slashIdx)
        })
        .join('\n')
      expect(codeOnly).not.toMatch(keyRegex)
    },
  )

  it('still sends target_duration (T2.4 wired it to the LLM)', () => {
    const payloadBody = extractPayloadBody(readWorkflow())
    expect(payloadBody).toMatch(/(^|\s|,)target_duration\s*:/)
  })

  it('still sends the live intent fields the engine consumes', () => {
    const payloadBody = extractPayloadBody(readWorkflow())
    // These are the surviving "user intent" fields confirmed wired in
    // the audit. If any disappears from buildPayload, the BE-side
    // guard `test_render_request_public_no_dead_fields` would still
    // pass but the wire would silently degrade.
    expect(payloadBody).toMatch(/(^|\s|,)target_platform\s*:/)
    expect(payloadBody).toMatch(/(^|\s|,)output_count\s*:/)
    expect(payloadBody).toMatch(/(^|\s|,)min_part_sec\s*:/)
    expect(payloadBody).toMatch(/(^|\s|,)max_part_sec\s*:/)
    expect(payloadBody).toMatch(/(^|\s|,)hook_strength\s*:/)
    expect(payloadBody).toMatch(/(^|\s|,)video_type\s*:/)
  })
})

describe('T1.4 — `RenderRequest` TS interface omits dead fields', () => {
  it.each(ALL_STRIPPED)(
    'never declares %s as an interface property',
    (field: string) => {
      const source = readApiTypes()
      // Find the `RenderRequest` interface body.
      const startIdx = source.indexOf('export interface RenderRequest {')
      expect(startIdx).toBeGreaterThan(-1)
      // Naive scan until matching `}` at depth 0.
      let depth = 0
      let i = source.indexOf('{', startIdx)
      let endIdx = -1
      for (; i < source.length; i++) {
        const ch = source[i]
        if (ch === '{') depth++
        else if (ch === '}') {
          depth--
          if (depth === 0) {
            endIdx = i
            break
          }
        }
      }
      expect(endIdx).toBeGreaterThan(startIdx)
      const interfaceBody = source.slice(startIdx, endIdx + 1)
      // Strip line comments before matching so the T1.4 commentary
      // text doesn't trip the assertion.
      const codeOnly = interfaceBody
        .split('\n')
        .map((line) => {
          const slashIdx = line.indexOf('//')
          return slashIdx === -1 ? line : line.slice(0, slashIdx)
        })
        .join('\n')
      // A field declaration in a TS interface is `name?:` or `name:`.
      const declRegex = new RegExp(`(^|\\s|,|;)${field}\\s*\\?\\s*:`)
      expect(codeOnly).not.toMatch(declRegex)
    },
  )
})
