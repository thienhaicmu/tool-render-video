/**
 * Zustand store tests
 * - uiStore toggleSidebar
 * - uiStore setActivePanel
 * - uiStore addNotification / removeNotification
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useUIStore } from '../src/stores/uiStore'

// Reset store state between tests
function resetUIStore() {
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'render',
    notifications: [],
  })
}

describe('uiStore — toggleSidebar', () => {
  beforeEach(resetUIStore)

  it('toggles sidebarOpen from true to false', () => {
    expect(useUIStore.getState().sidebarOpen).toBe(true)
    useUIStore.getState().toggleSidebar()
    expect(useUIStore.getState().sidebarOpen).toBe(false)
  })

  it('toggles sidebarOpen from false to true', () => {
    useUIStore.setState({ sidebarOpen: false })
    useUIStore.getState().toggleSidebar()
    expect(useUIStore.getState().sidebarOpen).toBe(true)
  })

  it('toggles twice returns to original state', () => {
    const initial = useUIStore.getState().sidebarOpen
    useUIStore.getState().toggleSidebar()
    useUIStore.getState().toggleSidebar()
    expect(useUIStore.getState().sidebarOpen).toBe(initial)
  })
})

describe('uiStore — setSidebarOpen', () => {
  beforeEach(resetUIStore)

  it('sets sidebarOpen to false explicitly', () => {
    useUIStore.getState().setSidebarOpen(false)
    expect(useUIStore.getState().sidebarOpen).toBe(false)
  })

  it('sets sidebarOpen to true explicitly', () => {
    useUIStore.setState({ sidebarOpen: false })
    useUIStore.getState().setSidebarOpen(true)
    expect(useUIStore.getState().sidebarOpen).toBe(true)
  })
})

describe('uiStore — setActivePanel', () => {
  beforeEach(resetUIStore)

  it('sets activePanel to "history"', () => {
    useUIStore.getState().setActivePanel('history')
    expect(useUIStore.getState().activePanel).toBe('history')
  })

  it('sets activePanel to "editor"', () => {
    useUIStore.getState().setActivePanel('editor')
    expect(useUIStore.getState().activePanel).toBe('editor')
  })

  it('sets activePanel to "settings"', () => {
    useUIStore.getState().setActivePanel('settings')
    expect(useUIStore.getState().activePanel).toBe('settings')
  })

  it('sets activePanel back to "render"', () => {
    useUIStore.getState().setActivePanel('settings')
    useUIStore.getState().setActivePanel('render')
    expect(useUIStore.getState().activePanel).toBe('render')
  })
})

describe('uiStore — addNotification / removeNotification', () => {
  beforeEach(resetUIStore)

  it('adds a notification and returns an id', () => {
    const id = useUIStore.getState().addNotification({
      type: 'success',
      title: 'Render complete',
    })
    expect(typeof id).toBe('string')
    expect(id).toBeTruthy()
    const { notifications } = useUIStore.getState()
    expect(notifications).toHaveLength(1)
    expect(notifications[0].id).toBe(id)
    expect(notifications[0].title).toBe('Render complete')
    expect(notifications[0].type).toBe('success')
  })

  it('adds multiple notifications', () => {
    useUIStore.getState().addNotification({ type: 'info', title: 'Info 1' })
    useUIStore.getState().addNotification({ type: 'warning', title: 'Warning 1' })
    expect(useUIStore.getState().notifications).toHaveLength(2)
  })

  it('removes a notification by id', () => {
    const id = useUIStore.getState().addNotification({ type: 'error', title: 'Error' })
    expect(useUIStore.getState().notifications).toHaveLength(1)
    useUIStore.getState().removeNotification(id)
    expect(useUIStore.getState().notifications).toHaveLength(0)
  })

  it('removes only the specified notification', () => {
    const id1 = useUIStore.getState().addNotification({ type: 'info', title: 'First' })
    const id2 = useUIStore.getState().addNotification({ type: 'success', title: 'Second' })
    useUIStore.getState().removeNotification(id1)
    const { notifications } = useUIStore.getState()
    expect(notifications).toHaveLength(1)
    expect(notifications[0].id).toBe(id2)
    expect(notifications[0].title).toBe('Second')
  })

  it('clearNotifications removes all', () => {
    useUIStore.getState().addNotification({ type: 'info', title: 'A' })
    useUIStore.getState().addNotification({ type: 'info', title: 'B' })
    useUIStore.getState().clearNotifications()
    expect(useUIStore.getState().notifications).toHaveLength(0)
  })

  it('notification has correct type field', () => {
    useUIStore.getState().addNotification({ type: 'warning', title: 'Heads up', message: 'Check this' })
    const notif = useUIStore.getState().notifications[0]
    expect(notif.type).toBe('warning')
    expect(notif.message).toBe('Check this')
  })
})
