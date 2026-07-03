/**
 * render-submit-error.test.ts — god-file slice 4a.
 *
 * Pins parseSubmitError: verbatim message surfacing + 409 dedup job-id extraction.
 */
import { describe, it, expect } from 'vitest'
import { parseSubmitError } from '../src/features/clip-studio/render/submitError'

const UUID = 'fab6af2b-1234-5678-9abc-def012345678'

describe('parseSubmitError', () => {
  it('extracts the dedup job id from a 409 detail', () => {
    const r = parseSubmitError({
      status: 409,
      detail: `A render job for this source is already in progress (job_id=${UUID}). Wait for it to finish.`,
    })
    expect(r.dedupJobId).toBe(UUID)
    expect(r.message).toContain('already in progress')
  })

  it('surfaces a non-409 detail string with no dedup id', () => {
    const r = parseSubmitError({ status: 500, detail: 'Internal error' })
    expect(r.message).toBe('Internal error')
    expect(r.dedupJobId).toBeNull()
  })

  it('stringifies a non-string detail and finds no dedup id', () => {
    const r = parseSubmitError({ status: 409, detail: { loc: ['body'], msg: 'bad' } })
    expect(r.message).toContain('bad')
    expect(r.dedupJobId).toBeNull()
  })

  it('uses Error.message for a plain Error', () => {
    expect(parseSubmitError(new Error('network down')).message).toBe('network down')
  })

  it('falls back to a default for an unknown throwable', () => {
    const r = parseSubmitError('nope')
    expect(r.message).toBe('Failed to start render')
    expect(r.dedupJobId).toBeNull()
  })
})
