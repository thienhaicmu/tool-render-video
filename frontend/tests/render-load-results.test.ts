/**
 * render-load-results.test.ts — god-file slice 3.
 *
 * Pins loadTerminalResults: collects parts + quality (scores/reports) + ranking,
 * and marks qualityLoadFailed when the quality fetch throws.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/jobs', () => ({
  getJobParts: vi.fn(),
  getJobQualitySummary: vi.fn(),
  getJobRanking: vi.fn(),
}))

import { loadTerminalResults } from '../src/features/clip-studio/render/loadResults'
import { getJobParts, getJobQualitySummary, getJobRanking } from '@/api/jobs'

beforeEach(() => vi.clearAllMocks())

describe('loadTerminalResults', () => {
  it('collects parts, quality scores/reports and ranking', async () => {
    vi.mocked(getJobParts).mockResolvedValue([{ part_no: 1 }] as never)
    vi.mocked(getJobQualitySummary).mockResolvedValue({
      parts: [{ part_no: 1, score: 87, report: { issues: [] } }],
    } as never)
    vi.mocked(getJobRanking).mockResolvedValue({ 1: { output_rank: 1 } } as never)

    const r = await loadTerminalResults('job-1')
    expect(r.parts).toHaveLength(1)
    expect(r.quality?.scores[1]).toBe(87)
    expect(r.quality?.reports[1]).toEqual({ issues: [] })
    expect(r.partRanks?.[1]).toEqual({ output_rank: 1 })
    expect(r.qualityLoadFailed).toBeUndefined()
  })

  it('flags qualityLoadFailed when the quality fetch throws', async () => {
    vi.mocked(getJobParts).mockResolvedValue([] as never)
    vi.mocked(getJobQualitySummary).mockRejectedValue(new Error('boom'))
    vi.mocked(getJobRanking).mockResolvedValue({} as never)

    const r = await loadTerminalResults('job-1')
    expect(r.qualityLoadFailed).toBe(true)
    expect(r.quality).toBeUndefined()
  })

  it('leaves ranking undefined when it throws (kept as previous)', async () => {
    vi.mocked(getJobParts).mockResolvedValue([] as never)
    vi.mocked(getJobQualitySummary).mockResolvedValue({ parts: [] } as never)
    vi.mocked(getJobRanking).mockRejectedValue(new Error('no rank'))

    const r = await loadTerminalResults('job-1')
    expect(r.partRanks).toBeUndefined()
  })
})
