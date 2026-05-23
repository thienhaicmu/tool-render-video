/**
 * UI store — sidebar state, active panel, notifications.
 */
import { create } from 'zustand'

export type ActivePanel =
  // Canonical navigation (Figma-locked — 5 top-level routes)
  | 'home'
  | 'studio'
  | 'library'
  | 'publish'
  | 'settings'
  // Deprecated aliases — preserved for backward compat, do not add new usage
  | 'render'   // JobEmptyState uses this
  | 'history'  // RenderForm, EditorEmptyState, EditorMetadataPanel use this
  | 'editor'   // JobDetailDrawer uses this

export type StudioStep =
  | 'source'
  | 'analyze'
  | 'plan'
  | 'edit'
  | 'render'
  | 'review'

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
  studioStep: StudioStep | null
  notifications: Notification[]

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setActivePanel: (panel: ActivePanel) => void
  setStudioStep: (step: StudioStep | null) => void
  addNotification: (notification: Omit<Notification, 'id'>) => string
  removeNotification: (id: string) => void
  clearNotifications: () => void
}

let _notifCounter = 0

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'home',
  studioStep: null as StudioStep | null,
  notifications: [],

  toggleSidebar: () => {
    set((s) => ({ sidebarOpen: !s.sidebarOpen }))
  },

  setSidebarOpen: (open: boolean) => {
    set({ sidebarOpen: open })
  },

  setActivePanel: (panel: ActivePanel) => {
    set({ activePanel: panel })
  },

  setStudioStep: (step: StudioStep | null) => set({ studioStep: step }),

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
}))
