/**
 * sidebar.test.tsx — WP2 nav redesign.
 *
 * The rail now shows a visible label under each icon (accessible name via
 * aria-label) and carries 5 main destinations — Studio · Queue · Library ·
 * Download · Editor — plus Settings in the bottom group. Editor gained a nav
 * home in WP2; there is no Publish/Home/Render/History nav item.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { Sidebar } from '../src/layouts/Sidebar'
import { useUIStore } from '../src/stores/uiStore'

const originalConfirm = window.confirm

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({ sidebarOpen: true, activePanel: 'home', notifications: [] })
  window.confirm = vi.fn(() => true)
})

afterEach(() => {
  window.confirm = originalConfirm
})

const btn = (name: string) => screen.getByRole('button', { name })

describe('Sidebar — nav item rendering', () => {
  it('renders the 5 main nav items by their i18n labels', () => {
    render(<Sidebar />)
    expect(btn('Studio')).toBeTruthy()
    expect(btn('Queue')).toBeTruthy()
    expect(btn('Library')).toBeTruthy()
    expect(btn('Download')).toBeTruthy()
    expect(btn('Editor')).toBeTruthy()
  })

  it('renders the Settings nav item in the bottom group', () => {
    render(<Sidebar />)
    expect(btn('Settings')).toBeTruthy()
  })
})

describe('Sidebar — active-item highlighting', () => {
  it('marks the currently active panel with aria-current="page"', () => {
    useUIStore.setState({ activePanel: 'clip-studio' })
    render(<Sidebar />)
    expect(btn('Studio').getAttribute('aria-current')).toBe('page')
  })

  it('does not set aria-current on inactive items', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    expect(btn('Library').getAttribute('aria-current')).toBeNull()
  })

  it('moves the active mark when activePanel changes', () => {
    useUIStore.setState({ activePanel: 'queue' })
    render(<Sidebar />)
    expect(btn('Queue').getAttribute('aria-current')).toBe('page')
    expect(btn('Studio').getAttribute('aria-current')).toBeNull()
  })
})

describe('Sidebar — click routes to setActivePanel', () => {
  const cases: Array<[string, string]> = [
    ['Studio', 'clip-studio'],
    ['Queue', 'queue'],
    ['Library', 'library'],
    ['Download', 'download'],
    ['Editor', 'editor'],
    ['Settings', 'settings'],
  ]
  for (const [label, panel] of cases) {
    it(`clicking ${label} sets activePanel to "${panel}"`, () => {
      useUIStore.setState({ activePanel: 'home' })
      render(<Sidebar />)
      fireEvent.click(btn(label))
      expect(useUIStore.getState().activePanel).toBe(panel)
    })
  }
})

describe('Sidebar — does NOT render retired nav items', () => {
  it('has no Render / History / Publish nav item', () => {
    render(<Sidebar />)
    expect(screen.queryByRole('button', { name: 'Render' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'History' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Publish' })).toBeNull()
  })
})
