/**
 * usePlanHistory.ts — undo/redo command stack for the editable ContentPlan
 * (CM-10). The plan is already treated immutably (every edit is a fresh object),
 * so a past/present/future stack is cheap.
 *
 * Two distinct setters:
 *   - setPlan(next)   — an EDIT: pushes the current present onto `past` (undoable)
 *   - resetPlan(p)    — a NEW plan (generate / open draft / new video): clears
 *                       history so undo can't cross into a different plan
 */
import { useCallback, useState } from 'react'
import type { ContentPlan } from '../../api/content'

const _CAP = 50  // bound the past stack so a long editing session can't grow unbounded

interface History {
  past: ContentPlan[]
  present: ContentPlan | null
  future: ContentPlan[]
}

export interface PlanHistory {
  plan: ContentPlan | null
  setPlan: (next: ContentPlan) => void
  resetPlan: (p: ContentPlan | null) => void
  undo: () => void
  redo: () => void
  canUndo: boolean
  canRedo: boolean
}

export function usePlanHistory(): PlanHistory {
  const [h, setH] = useState<History>({ past: [], present: null, future: [] })

  const setPlan = useCallback((next: ContentPlan) => {
    setH((s) => ({
      past: (s.present ? [...s.past, s.present] : s.past).slice(-_CAP),
      present: next,
      future: [],
    }))
  }, [])

  const resetPlan = useCallback((p: ContentPlan | null) => {
    setH({ past: [], present: p, future: [] })
  }, [])

  const undo = useCallback(() => {
    setH((s) => {
      if (s.past.length === 0) return s
      const prev = s.past[s.past.length - 1]
      return {
        past: s.past.slice(0, -1),
        present: prev,
        future: s.present ? [s.present, ...s.future] : s.future,
      }
    })
  }, [])

  const redo = useCallback(() => {
    setH((s) => {
      if (s.future.length === 0) return s
      const next = s.future[0]
      return {
        past: s.present ? [...s.past, s.present] : s.past,
        present: next,
        future: s.future.slice(1),
      }
    })
  }, [])

  return {
    plan: h.present, setPlan, resetPlan, undo, redo,
    canUndo: h.past.length > 0, canRedo: h.future.length > 0,
  }
}
