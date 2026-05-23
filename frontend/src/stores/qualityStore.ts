/**
 * Quality store — on-demand quality reports and summaries.
 * Do NOT fetch these in polling loops — they hit the filesystem.
 */
import { create } from 'zustand'
import { getJobPartQuality, getJobQualitySummary } from '../api/jobs'
import type { QualityReport, QualitySummary } from '../types/api'

export interface QualityStore {
  /** Key: `${jobId}_${partNo}` */
  reports: Record<string, QualityReport>
  summaries: Record<string, QualitySummary>
  loading: Record<string, boolean>
  errors: Record<string, string>

  fetchPartQuality: (jobId: string, partNo: number) => Promise<void>
  fetchJobSummary: (jobId: string, includeReports?: boolean) => Promise<void>
  clearJob: (jobId: string) => void

  /** Re-fetch summary even if already cached — clears cached data first. */
  refreshJobSummary: (jobId: string) => Promise<void>
  /** Re-fetch a single part report even if already cached. */
  refreshPartQuality: (jobId: string, partNo: number) => Promise<void>
}

export const useQualityStore = create<QualityStore>((set, get) => ({
  reports: {},
  summaries: {},
  loading: {},
  errors: {},

  fetchPartQuality: async (jobId: string, partNo: number) => {
    const key = `${jobId}_${partNo}`
    if (get().loading[key]) return

    set((s) => ({ loading: { ...s.loading, [key]: true } }))
    try {
      const report = await getJobPartQuality(jobId, partNo)
      set((s) => ({
        reports: { ...s.reports, [key]: report },
        loading: { ...s.loading, [key]: false },
        errors: { ...s.errors, [key]: '' },
      }))
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      set((s) => ({
        loading: { ...s.loading, [key]: false },
        errors: { ...s.errors, [key]: message },
      }))
    }
  },

  fetchJobSummary: async (jobId: string, includeReports = false) => {
    if (get().loading[jobId]) return

    set((s) => ({ loading: { ...s.loading, [jobId]: true } }))
    try {
      const summary = await getJobQualitySummary(jobId, includeReports)
      set((s) => ({
        summaries: { ...s.summaries, [jobId]: summary },
        loading: { ...s.loading, [jobId]: false },
        errors: { ...s.errors, [jobId]: '' },
      }))
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      set((s) => ({
        loading: { ...s.loading, [jobId]: false },
        errors: { ...s.errors, [jobId]: message },
      }))
    }
  },

  clearJob: (jobId: string) => {
    set((s) => {
      const reports = { ...s.reports }
      const errors = { ...s.errors }
      // Remove all part keys for this job
      Object.keys(reports).forEach((k) => {
        if (k.startsWith(`${jobId}_`)) delete reports[k]
      })
      const { [jobId]: _summ, ...summaries } = s.summaries
      delete errors[jobId]
      return { reports, summaries, errors }
    })
  },

  refreshJobSummary: async (jobId: string) => {
    // Clear loading state so fetchJobSummary guard does not block
    set((s) => {
      const loading = { ...s.loading }
      delete loading[jobId]
      return { loading }
    })
    get().clearJob(jobId)
    await get().fetchJobSummary(jobId)
  },

  refreshPartQuality: async (jobId: string, partNo: number) => {
    const key = `${jobId}_${partNo}`
    set((s) => {
      const loading = { ...s.loading }
      const reports = { ...s.reports }
      delete loading[key]
      delete reports[key]
      return { loading, reports }
    })
    await get().fetchPartQuality(jobId, partNo)
  },
}))
