/**
 * UI store — sidebar state, active panel, notifications.
 */
import { create } from 'zustand'

export type ActivePanel = 'render' | 'history' | 'editor' | 'settings'

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

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setActivePanel: (panel: ActivePanel) => void
  addNotification: (notification: Omit<Notification, 'id'>) => string
  removeNotification: (id: string) => void
  clearNotifications: () => void
}

let _notifCounter = 0

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'render',
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
