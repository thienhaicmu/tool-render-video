/**
 * sidebar.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Replaces the deleted navigation-polish.test.tsx which asserted the old
 * 4-item ("Render/History/Editor/Settings") sidebar. The current sidebar
 * has 5 main nav items (home/studio/library/download/publish) + 1 bottom
 * item (settings), all labeled via i18n. This file tests the current shape
 * + the panel-switching behavior that Sprint 5.6 affected.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { Sidebar } from '../src/layouts/Sidebar'
import { useUIStore } from '../src/stores/uiStore'

// Sidebar uses a "Render job đang chạy" confirm dialog when leaving an
// active render. Mock window.confirm so it doesn't block the test.
const originalConfirm = window.confirm

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'home',
    notifications: [],
  })
  window.confirm = vi.fn(() => true)
})

afterEach(() => {
  window.confirm = originalConfirm
})


describe('Sidebar — nav item rendering', () => {
  it('renders 5 main nav items by their i18n labels', () => {
    render(<Sidebar />)
    // Default lang is 'en', so labels come from translations.en
    expect(screen.getByTitle('Home')).toBeTruthy()
    expect(screen.getByTitle('Studio')).toBeTruthy()
    expect(screen.getByTitle('Library')).toBeTruthy()
    expect(screen.getByTitle('Download')).toBeTruthy()
    expect(screen.getByTitle('Publish')).toBeTruthy()
  })

  it('renders the Settings nav item in the bottom group', () => {
    render(<Sidebar />)
    expect(screen.getByTitle('Settings')).toBeTruthy()
  })

  it('renders the AI Clip Studio wordmark', () => {
    render(<Sidebar />)
    expect(screen.getByText('AI Clip Studio')).toBeTruthy()
  })
})


describe('Sidebar — active-item highlighting', () => {
  it('marks the currently active panel with aria-current="page"', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    const activeBtn = screen.getByTitle('Home')
    expect(activeBtn.getAttribute('aria-current')).toBe('page')
  })

  it('does not set aria-current on inactive items', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    const inactiveBtn = screen.getByTitle('Library')
    expect(inactiveBtn.getAttribute('aria-current')).toBeNull()
  })

  it('moves the active mark when activePanel changes', () => {
    useUIStore.setState({ activePanel: 'library' })
    render(<Sidebar />)
    expect(screen.getByTitle('Library').getAttribute('aria-current')).toBe('page')
    expect(screen.getByTitle('Home').getAttribute('aria-current')).toBeNull()
  })
})


describe('Sidebar — click handler routes to setActivePanel', () => {
  it('clicking Studio sets activePanel to "clip-studio"', () => {
    // Sprint 5.6 + followup_2 bug fix: Studio nav now points at clip-studio
    // (not the deleted 'studio' panel). This test guards against the bug
    // recurring.
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    fireEvent.click(screen.getByTitle('Studio'))
    expect(useUIStore.getState().activePanel).toBe('clip-studio')
  })

  it('clicking Settings sets activePanel to "settings"', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    fireEvent.click(screen.getByTitle('Settings'))
    expect(useUIStore.getState().activePanel).toBe('settings')
  })

  it('clicking Library sets activePanel to "library"', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    fireEvent.click(screen.getByTitle('Library'))
    expect(useUIStore.getState().activePanel).toBe('library')
  })

  it('clicking Download sets activePanel to "download"', () => {
    useUIStore.setState({ activePanel: 'home' })
    render(<Sidebar />)
    fireEvent.click(screen.getByTitle('Download'))
    expect(useUIStore.getState().activePanel).toBe('download')
  })
})


describe('Sidebar — does NOT render deleted nav items', () => {
  it('has no "Render" nav item (renamed via Sprint 5.6 retire)', () => {
    render(<Sidebar />)
    expect(screen.queryByTitle('Render')).toBeNull()
  })

  it('has no "History" nav item (consolidated into Home/Library)', () => {
    render(<Sidebar />)
    expect(screen.queryByTitle('History')).toBeNull()
  })

  it('has no "Editor" nav item', () => {
    render(<Sidebar />)
    expect(screen.queryByTitle('Editor')).toBeNull()
  })
})
