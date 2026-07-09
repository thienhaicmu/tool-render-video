/**
 * UI store — sidebar state, active panel, notifications.
 */
import { create } from 'zustand'
import type { Lang } from '../i18n/translations'

export type ActivePanel =
  // Canonical navigation
  | 'home'
  | 'clip-studio'
  | 'content-studio'
  | 'story-studio'
  | 'queue'
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
  /** P1.4 — job this notification is about. History entries carrying a
   *  jobId become clickable in NotificationCenter (deep-link to the
   *  job's monitor / the download panel). */
  jobId?: string
  kind?: 'render' | 'download'
  /** P1.4 — when true, only a history entry is recorded; no toast is
   *  shown. Used by useJobCompletionNotifier, which already fires an OS
   *  notification — a simultaneous in-app toast would double up with
   *  the RenderWorkflow terminal toast for the attached job. */
  silent?: boolean
}

/** S4.7 — notification history entry. Same shape as `Notification`
 *  plus a `created_at` timestamp + a `read` flag. Stored separately
 *  from the live `notifications` array so dismissing a toast doesn't
 *  evict its history record. */
export interface NotificationHistoryEntry {
  id: string
  type: Notification['type']
  title: string
  message?: string
  created_at: number
  read: boolean
  jobId?: string
  kind?: 'render' | 'download'
}

export interface UIStore {
  sidebarOpen: boolean
  activePanel: ActivePanel
  notifications: Notification[]
  /** S4.7 — persistent history of past notifications (cap 50, newest
   *  first). Backed by localStorage so survives a tab reload. */
  notificationHistory: NotificationHistoryEntry[]
  lang: Lang
  /** S2.5 — jobId being duplicated, picked up by RenderWorkflow on
   *  mount to pre-fill cfg + source from the old job's payload_json.
   *  Cleared once consumed so a second visit to clip-studio doesn't
   *  re-apply stale state. */
  duplicateSeedJobId: string | null
  /** Pha 1.1 — absolute path of a finished download the user chose to
   *  "Send to Render". DownloadTab sets it; ClipStudio watches it to
   *  flip to the Render tab; RenderWorkflow consumes it to pre-fill the
   *  source on a clean Step 1, then clears it so a second visit doesn't
   *  re-apply a stale path. Mirrors the duplicateSeedJobId handshake. */
  sendToRenderSourcePath: string | null
  /** Pha 4 — explicit "open the Monitor (Step 3) for this job" signal.
   *  RenderWorkflow consumes + clears it. This is the ONLY way a
   *  background/other job opens the monitor now that the broad
   *  auto-reattach hijack is gone — set by dock/drawer/notification/409. */
  monitorJobId: string | null
  /** Content Studio's equivalent of monitorJobId — reattach an active
   *  content-mode render to the Content Studio monitor (a content job must
   *  NOT open in the Clip Studio). Set by the shared openRenderMonitor. */
  contentMonitorJobId: string | null
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
  setSendToRenderSourcePath: (path: string | null) => void
  setMonitorJobId: (jobId: string | null) => void
  setContentMonitorJobId: (jobId: string | null) => void
  requestNewRender: () => void
  /** S4.7 — mark a single history entry as read. */
  markNotificationRead: (id: string) => void
  /** S4.7 — mark every history entry as read. */
  markAllNotificationsRead: () => void
  /** S4.7 — drop all history entries (history panel "Clear" button). */
  clearNotificationHistory: () => void
}

let _notifCounter = 0

// S4.7 — localStorage persistence for notification history.
const NOTIF_HISTORY_KEY = 'ui:notif_history_v1'
const NOTIF_HISTORY_CAP = 50

function _loadHistory(): NotificationHistoryEntry[] {
  try {
    const raw = localStorage.getItem(NOTIF_HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.slice(0, NOTIF_HISTORY_CAP) as NotificationHistoryEntry[]
  } catch {
    return []
  }
}

function _saveHistory(entries: NotificationHistoryEntry[]) {
  try {
    localStorage.setItem(NOTIF_HISTORY_KEY, JSON.stringify(entries.slice(0, NOTIF_HISTORY_CAP)))
  } catch {
    // localStorage quota or disabled — silently drop.
  }
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'clip-studio',
  notifications: [],
  notificationHistory: _loadHistory(),
  lang: 'en' as Lang,
  duplicateSeedJobId: null,
  sendToRenderSourcePath: null,
  monitorJobId: null,
  contentMonitorJobId: null,
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
    set((s) => {
      const historyEntry: NotificationHistoryEntry = {
        id,
        type: notification.type,
        title: notification.title,
        message: notification.message,
        created_at: Date.now(),
        read: false,
        jobId: notification.jobId,
        kind: notification.kind,
      }
      const history = [historyEntry, ...s.notificationHistory].slice(0, NOTIF_HISTORY_CAP)
      _saveHistory(history)
      return {
        notifications: notification.silent
          ? s.notifications
          : [...s.notifications, { ...notification, id }],
        notificationHistory: history,
      }
    })
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

  setSendToRenderSourcePath: (path: string | null) => set({ sendToRenderSourcePath: path }),


  setMonitorJobId: (jobId: string | null) => set({ monitorJobId: jobId }),
  setContentMonitorJobId: (jobId: string | null) => set({ contentMonitorJobId: jobId }),

  requestNewRender: () => set((s) => ({ newRenderRequest: s.newRenderRequest + 1 })),

  markNotificationRead: (id: string) => set((s) => {
    const next = s.notificationHistory.map((n) => (n.id === id ? { ...n, read: true } : n))
    _saveHistory(next)
    return { notificationHistory: next }
  }),

  markAllNotificationsRead: () => set((s) => {
    const next = s.notificationHistory.map((n) => ({ ...n, read: true }))
    _saveHistory(next)
    return { notificationHistory: next }
  }),

  clearNotificationHistory: () => {
    _saveHistory([])
    set({ notificationHistory: [] })
  },
}))
