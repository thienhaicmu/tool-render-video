/**
 * navigation-polish.test.tsx — Phase 6.6 navigation + UI polish tests.
 *
 * Tests:
 * - Sidebar renders all 4 nav items
 * - Active panel changes when nav item clicked
 * - Topbar title changes with active panel
 * - Notifications component exists in AppShell output
 * - EditorEmptyState "Go to History" button sets panel to 'history' (not 'jobs')
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useUIStore } from '../src/stores/uiStore'

// ── Mocks ─────────────────────────────────────────────────────────────────────

// Mock API calls that Topbar and screens would trigger
vi.mock('../src/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/api/client')>()
  return {
    ...original,
    apiFetch: vi.fn().mockRejectedValue(new Error('no backend in tests')),
  }
})

vi.mock('../src/api/jobs', () => ({
  getJobHistory: vi.fn().mockResolvedValue({ items: [], limit: 20, offset: 0, has_more: false }),
  deleteJob: vi.fn(),
  getJob: vi.fn(),
  getJobParts: vi.fn().mockResolvedValue([]),
}))

vi.mock('../src/api/render', () => ({
  submitRender: vi.fn(),
  cancelRender: vi.fn(),
  retryRender: vi.fn(),
  resumeRender: vi.fn(),
}))

vi.mock('../src/stores/qualityStore', () => ({
  useQualityStore: (selector: (s: unknown) => unknown) =>
    selector({
      summaries: {},
      reports: {},
      loading: {},
      errors: {},
      fetchJobSummary: vi.fn().mockResolvedValue(undefined),
      refreshJobSummary: vi.fn(),
      fetchPartQuality: vi.fn(),
      refreshPartQuality: vi.fn(),
      clearJob: vi.fn(),
    }),
}))

vi.mock('../src/hooks/useRenderSocket', () => ({
  useRenderSocket: () => ({
    stage: null,
    jobStatus: null,
    jobMessage: null,
    progress: null,
    isConnected: false,
    isTerminal: true,
    error: null,
  }),
}))

// ── Import after mocks ────────────────────────────────────────────────────────

import { Sidebar } from '../src/layouts/Sidebar'
import { Topbar } from '../src/layouts/Topbar'
import { AppShell } from '../src/layouts/AppShell'
import { EditorEmptyState } from '../src/features/editor/EditorEmptyState'

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({ sidebarOpen: true, activePanel: 'render', notifications: [] })
})

// ── Sidebar tests ─────────────────────────────────────────────────────────────

describe('navigation-polish — Sidebar', () => {
  it('renders all 4 nav items', () => {
    render(<Sidebar />)
    expect(screen.getByTitle('Render')).toBeTruthy()
    expect(screen.getByTitle('History')).toBeTruthy()
    expect(screen.getByTitle('Editor')).toBeTruthy()
    expect(screen.getByTitle('Settings')).toBeTruthy()
  })

  it('active item has aria-current="page"', () => {
    useUIStore.setState({ activePanel: 'render' })
    render(<Sidebar />)
    const activeBtn = screen.getByTitle('Render')
    expect(activeBtn.getAttribute('aria-current')).toBe('page')
  })

  it('inactive items do not have aria-current="page"', () => {
    useUIStore.setState({ activePanel: 'render' })
    render(<Sidebar />)
    const historyBtn = screen.getByTitle('History')
    expect(historyBtn.getAttribute('aria-current')).toBeNull()
  })

  it('clicking History nav item sets activePanel to "history"', async () => {
    const user = userEvent.setup()
    render(<Sidebar />)
    await user.click(screen.getByTitle('History'))
    expect(useUIStore.getState().activePanel).toBe('history')
  })

  it('clicking Editor nav item sets activePanel to "editor"', async () => {
    const user = userEvent.setup()
    render(<Sidebar />)
    await user.click(screen.getByTitle('Editor'))
    expect(useUIStore.getState().activePanel).toBe('editor')
  })

  it('clicking Settings nav item sets activePanel to "settings"', async () => {
    const user = userEvent.setup()
    render(<Sidebar />)
    await user.click(screen.getByTitle('Settings'))
    expect(useUIStore.getState().activePanel).toBe('settings')
  })

  it('nav item labels are exactly Render, History, Editor, Settings (no stale text)', () => {
    render(<Sidebar />)
    // Expanded sidebar shows labels
    expect(screen.getByText('Render')).toBeTruthy()
    expect(screen.getByText('History')).toBeTruthy()
    expect(screen.getByText('Editor')).toBeTruthy()
    expect(screen.getByText('Settings')).toBeTruthy()
    // No stale labels from previous phases
    expect(screen.queryByText(/Phase 6\./)).toBeNull()
  })
})

// ── Topbar panel title tests ──────────────────────────────────────────────────

describe('navigation-polish — Topbar panel title', () => {
  it('shows "New Render" when activePanel is render', () => {
    useUIStore.setState({ activePanel: 'render' })
    render(<Topbar />)
    expect(screen.getByText('New Render')).toBeTruthy()
  })

  it('shows "History" when activePanel is history', () => {
    useUIStore.setState({ activePanel: 'history' })
    render(<Topbar />)
    expect(screen.getByText('History')).toBeTruthy()
  })

  it('shows "Editor" when activePanel is editor', () => {
    useUIStore.setState({ activePanel: 'editor' })
    render(<Topbar />)
    expect(screen.getByText('Editor')).toBeTruthy()
  })

  it('shows "Settings" when activePanel is settings', () => {
    useUIStore.setState({ activePanel: 'settings' })
    render(<Topbar />)
    expect(screen.getByText('Settings')).toBeTruthy()
  })

  it('does NOT show static "Render Studio" as title anymore', () => {
    useUIStore.setState({ activePanel: 'render' })
    render(<Topbar />)
    // The h1 title should be "New Render", not the old "Render Studio"
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.textContent).toBe('New Render')
    expect(h1.textContent).not.toBe('Render Studio')
  })
})

// ── AppShell Notifications presence ──────────────────────────────────────────

describe('navigation-polish — AppShell includes Notifications', () => {
  it('AppShell renders children', () => {
    render(
      <AppShell>
        <div data-testid="shell-child">test</div>
      </AppShell>,
    )
    expect(screen.getByTestId('shell-child')).toBeTruthy()
  })

  it('AppShell renders aria-live region for notifications', () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    )
    // Notifications container has aria-live="polite"
    const liveRegion = document.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeTruthy()
  })

  it('AppShell notification container is present even with no notifications', () => {
    useUIStore.setState({ notifications: [] })
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    )
    const liveRegion = document.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeTruthy()
  })
})

// ── EditorEmptyState navigation ───────────────────────────────────────────────

describe('navigation-polish — EditorEmptyState', () => {
  it('renders "Go to History" button', () => {
    render(<EditorEmptyState />)
    expect(screen.getByTestId('go-to-history-btn')).toBeTruthy()
  })

  it('"Go to History" button sets activePanel to "history" (not "jobs")', async () => {
    const user = userEvent.setup()
    useUIStore.setState({ activePanel: 'editor' })
    render(<EditorEmptyState />)
    await user.click(screen.getByTestId('go-to-history-btn'))
    expect(useUIStore.getState().activePanel).toBe('history')
  })

  it('"Go to History" button does NOT set activePanel to "jobs"', async () => {
    const user = userEvent.setup()
    render(<EditorEmptyState />)
    await user.click(screen.getByTestId('go-to-history-btn'))
    expect(useUIStore.getState().activePanel).not.toBe('jobs')
  })
})
