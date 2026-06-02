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

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setActivePanel: (panel: ActivePanel) => void
  addNotification: (notification: Omit<Notification, 'id'>) => string
  removeNotification: (id: string) => void
  clearNotifications: () => void
  setLang: (lang: Lang) => void
}

let _notifCounter = 0

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'clip-studio',
  notifications: [],
  lang: 'en' as Lang,

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
}))
