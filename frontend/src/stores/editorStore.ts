/**
 * Editor store — tracks selected job/part for the editor preview screen.
 * Trim state is UI-only — no backend calls.
 */
import { create } from 'zustand'

export interface EditorStore {
  // Selection
  selectedJobId: string | null
  selectedPartNo: number | null
  mediaUrl: string | null

  // Video state (set by VideoPreview on metadata load)
  durationSec: number

  // Trim state (UI only — not sent to backend)
  trimStartSec: number
  trimEndSec: number
  isDirty: boolean

  // Actions
  openEditor: (jobId: string, partNo: number) => void
  setDuration: (durationSec: number) => void
  setTrim: (start: number, end: number) => void
  resetTrim: () => void
  closeEditor: () => void
}

// Build media URL from job/part
function buildMediaUrl(jobId: string, partNo: number): string {
  return `/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`
}

export const useEditorStore = create<EditorStore>((set, _get) => ({
  selectedJobId: null,
  selectedPartNo: null,
  mediaUrl: null,
  durationSec: 0,
  trimStartSec: 0,
  trimEndSec: 0,
  isDirty: false,

  openEditor: (jobId: string, partNo: number) => {
    set({
      selectedJobId: jobId,
      selectedPartNo: partNo,
      mediaUrl: buildMediaUrl(jobId, partNo),
      durationSec: 0,
      trimStartSec: 0,
      trimEndSec: 0,
      isDirty: false,
    })
  },

  setDuration: (durationSec: number) => {
    set((s) => ({
      durationSec,
      // Set trimEnd to duration only if still at default (0)
      trimEndSec: s.trimEndSec === 0 ? durationSec : s.trimEndSec,
    }))
  },

  setTrim: (start: number, end: number) => {
    set({ trimStartSec: start, trimEndSec: end, isDirty: true })
  },

  resetTrim: () => {
    set((s) => ({
      trimStartSec: 0,
      trimEndSec: s.durationSec,
      isDirty: false,
    }))
  },

  closeEditor: () => {
    set({
      selectedJobId: null,
      selectedPartNo: null,
      mediaUrl: null,
      durationSec: 0,
      trimStartSec: 0,
      trimEndSec: 0,
      isDirty: false,
    })
  },
}))
