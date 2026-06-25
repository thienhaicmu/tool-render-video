/**
 * UI store — sidebar state, active panel, notifications.
 */
import { create } from 'zustand'
import type { Lang } from '../i18n/translations'

export type ActivePanel =
  // Canonical navigation
  | 'home'
  | 'clip-studio'
  | 'library'
  | 'publish'
  | 'settings'
  | 'download'
  // Deprecated aliases — preserved for backward compat, do not add new usage
  | 'render'   // JobEmptyState uses this
  | 'history'  // EditorEmptyState, EditorMetadataPanel use this
  | 'editor'   // JobDetailDrawer uses this

// Sprint 5.6: StudioStep + studioStep state removed alongside features/studio/.

export interface Notification {
  id: string
  type: 'success' | 'warning' | 'error' | 'info'
  title: string
  message?: string
  duration?: number
}

export interface UIStore {
  sidebarOpen: boolean
  activePanel: ActivePanel
  notifications: Notification[]
  lang: Lang
  /** S2.5 — jobId being duplicated, picked up by RenderWorkflow on
   *  mount to pre-fill cfg + source from the old job's payload_json.
   *  Cleared once consumed so a second visit to clip-studio doesn't
   *  re-apply stale state. */
  duplicateSeedJobId: string | null
  /** S3.2/S3.5 — monotonic counter incremented every time the user
   *  asks for a fresh render (⌘N, palette action, or future "+ New"
   *  button). RenderWorkflow watches this counter and force-resets to
   *  Step 1, ignoring auto-reattach. A counter beats a boolean because
   *  React's useEffect deduplicates on identical values. */
  newRenderRequest: number

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setActivePanel: (panel: ActivePanel) => void
  addNotification: (notification: Omit<Notification, 'id'>) => string
  removeNotification: (id: string) => void
  clearNotifications: () => void
  setLang: (lang: Lang) => void
  setDuplicateSeedJobId: (jobId: string | null) => void
  requestNewRender: () => void
}

let _notifCounter = 0

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'clip-studio',
  notifications: [],
  lang: 'en' as Lang,
  duplicateSeedJobId: null,
  newRenderRequest: 0,

  toggleSidebar: () => {
    set((s) => ({ sidebarOpen: !s.sidebarOpen }))
  },

  setSidebarOpen: (open: boolean) => {
    set({ sidebarOpen: open })
  },

  setActivePanel: (panel: ActivePanel) => {
    set({ activePanel: panel })
  },

  addNotification: (notification: Omit<Notification, 'id'>): string => {
    const id = `notif_${Date.now()}_${++_notifCounter}`
    set((s) => ({
      notifications: [
        ...s.notifications,
        { ...notification, id },
      ],
    }))
    return id
  },

  removeNotification: (id: string) => {
    set((s) => ({
      notifications: s.notifications.filter((n) => n.id !== id),
    }))
  },

  clearNotifications: () => {
    set({ notifications: [] })
  },

  setLang: (lang: Lang) => set({ lang }),

  setDuplicateSeedJobId: (jobId: string | null) => set({ duplicateSeedJobId: jobId }),

  requestNewRender: () => set((s) => ({ newRenderRequest: s.newRenderRequest + 1 })),
}))
