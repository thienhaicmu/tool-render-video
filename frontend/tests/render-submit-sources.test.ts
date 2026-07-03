/**
 * render-submit-sources.test.ts — god-file slice 4b.
 *
 * Pins the multi-source batch submit loop: collects submitted job ids in order
 * and the source values that failed to submit.
 */
import { describe, it, expect, vi } from 'vitest'
import { submitSources } from '../src/features/clip-studio/render/submitSources'
import type { RenderRequest } from '../src/types/api'

const src = (...vals: string[]) => vals.map((value) => ({ value }))
const buildPayload = (value: string) => ({ source_video_path: value } as unknown as RenderRequest)

describe('submitSources', () => {
  it('submits each source and collects job ids in order', async () => {
    const submit = vi.fn()
      .mockResolvedValueOnce('job-a')
      .mockResolvedValueOnce('job-b')
    const r = await submitSources(src('a.mp4', 'b.mp4'), buildPayload, submit)
    expect(r.submitted).toEqual(['job-a', 'job-b'])
    expect(r.failed).toEqual([])
    expect(submit).toHaveBeenCalledTimes(2)
  })

  it('records the source value of a submit that throws', async () => {
    const submit = vi.fn()
      .mockResolvedValueOnce('job-a')
      .mockRejectedValueOnce(new Error('409'))
      .mockResolvedValueOnce('job-c')
    const r = await submitSources(src('a.mp4', 'b.mp4', 'c.mp4'), buildPayload, submit)
    expect(r.submitted).toEqual(['job-a', 'job-c'])
    expect(r.failed).toEqual(['b.mp4'])
  })

  it('handles an all-fail batch', async () => {
    const submit = vi.fn().mockRejectedValue(new Error('down'))
    const r = await submitSources(src('a.mp4', 'b.mp4'), buildPayload, submit)
    expect(r.submitted).toEqual([])
    expect(r.failed).toEqual(['a.mp4', 'b.mp4'])
  })
})
