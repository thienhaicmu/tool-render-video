/**
 * render-validate.test.ts — god-file slice 1.
 *
 * Pins the submit-time validation extracted from RenderWorkflow so the
 * decomposition has a real, passing safety net (the component's own tests
 * do not currently run green).
 */
import { describe, it, expect } from 'vitest'
import { validateSources, validateConfig } from '../src/features/clip-studio/render/validate'
import type { ConfigState, Source } from '../src/features/clip-studio/render/types'

const cfg = (over: Partial<ConfigState>): ConfigState =>
  ({ outputDir: 'D:\\out', minSec: 30, maxSec: 60, outputCount: 1, ...over } as unknown as ConfigState)
const src = (...vals: string[]): Source[] => vals.map((value) => ({ value }))

describe('validateSources', () => {
  it('flags an empty source list', () => {
    expect(validateSources([], 'EN')).toBe('No source file selected.')
    expect(validateSources([], 'VI')).toBe('Chưa chọn file nguồn.')
  })

  it('flags a blank source path', () => {
    expect(validateSources(src('  '), 'EN')).toBe('A source file path is empty.')
    expect(validateSources(src('a.mp4', ''), 'VI')).toBe('File nguồn rỗng.')
  })

  it('passes valid sources', () => {
    expect(validateSources(src('a.mp4', 'b.mp4'), 'EN')).toBeNull()
  })
})

describe('validateConfig', () => {
  it('flags an empty output dir', () => {
    expect(validateConfig(cfg({ outputDir: '' }), 'EN')).toBe('Save folder is empty.')
  })

  it('flags min > max', () => {
    const msg = validateConfig(cfg({ minSec: 90, maxSec: 60 }), 'EN')
    expect(msg).toContain('90s')
    expect(msg).toContain('60s')
  })

  it('flags output count < 1', () => {
    expect(validateConfig(cfg({ outputCount: 0 }), 'EN')).toBe('Output count must be ≥ 1.')
    expect(validateConfig(cfg({ outputCount: 0 }), 'VI')).toBe('Số clip xuất ra phải ≥ 1.')
  })

  it('passes a valid config', () => {
    expect(validateConfig(cfg({}), 'EN')).toBeNull()
  })
})
