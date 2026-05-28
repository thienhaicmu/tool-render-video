/**
 * Render store — tracks active jobs and their status.
 */
import { create } from 'zustand'
import { submitRender as apiSubmitRender } from '../api/render'
import type { RenderRequest, JobStatus } from '../types/api'

export interface RenderStore {
  jobs: Record<string, JobStatus>
  activeJobId: string | null

  submitRender: (payload: RenderRequest) => Promise<string>
  updateJobStatus: (jobId: string, status: string) => void
}

export const useRenderStore = create<RenderStore>((set) => ({
  jobs: {},
  activeJobId: null,

  submitRender: async (payload: RenderRequest): Promise<string> => {
    const response = await apiSubmitRender(payload)
    const jobId = response.job_id
    set((state) => ({
      activeJobId: jobId,
      jobs: {
        ...state.jobs,
        [jobId]: {
          job_id: jobId,
          kind: 'render',
          status: 'queued',
          stage: '',
          progress_percent: 0,
          message: 'Job queued',
          payload_json: '',
          result_json: '',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as JobStatus,
      },
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
          [jobId]: { ...existing, status, updated_at: new Date().toISOString() },
        },
      }
    })
  },
}))
