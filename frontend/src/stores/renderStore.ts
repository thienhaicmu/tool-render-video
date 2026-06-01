/**
 * Render store — tracks active jobs and their status.
 */
import { create } from 'zustand'
import { submitRender as apiSubmitRender } from '../api/render'
import { submitRenderV2 as apiSubmitRenderV2 } from '../api/render-v2'
import type { RenderRequest, JobStatus } from '../types/api'
import type { V2RenderRequest } from '../api/render-v2'

export interface RenderStore {
  jobs: Record<string, JobStatus>
  activeJobId: string | null

  submitRender:   (payload: RenderRequest)   => Promise<string>
  submitRenderV2: (payload: V2RenderRequest) => Promise<string>
  updateJobStatus: (jobId: string, status: string) => void
}

const _makeJobEntry = (jobId: string): JobStatus =>
  ({
    job_id:           jobId,
    kind:             'render',
    status:           'queued',
    stage:            '',
    progress_percent: 0,
    message:          'Job queued',
    payload_json:     '',
    result_json:      '',
    created_at:       new Date().toISOString(),
    updated_at:       new Date().toISOString(),
  }) as JobStatus

export const useRenderStore = create<RenderStore>((set) => ({
  jobs: {},
  activeJobId: null,

  submitRender: async (payload: RenderRequest): Promise<string> => {
    const response = await apiSubmitRender(payload)
    const jobId = response.job_id
    set((state) => ({
      activeJobId: jobId,
      jobs: { ...state.jobs, [jobId]: _makeJobEntry(jobId) },
    }))
    return jobId
  },

  submitRenderV2: async (payload: V2RenderRequest): Promise<string> => {
    const jobId = await apiSubmitRenderV2(payload)
    set((state) => ({
      activeJobId: jobId,
      jobs: { ...state.jobs, [jobId]: _makeJobEntry(jobId) },
    }))
    return jobId
  },

  updateJobStatus: (jobId: string, status: string) => {
    set((state) => {
      const existing = state.jobs[jobId]
      if (!existing) return state
      return {
        jobs: {
          ...state.jobs,
          [jobId]: { ...existing, status: status as JobStatus['status'], updated_at: new Date().toISOString() },
        },
      }
    })
  },
}))
