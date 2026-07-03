/**
 * topbar.test.tsx — Sprint 8 frontend test rewrite.
 *
 * The deleted navigation-polish.test.tsx asserted a "panel title" feature
 * in the Topbar (e.g. "New Render" / "History" / "Editor"). That feature
 * was removed when the Topbar was simplified. The current Topbar
 * (src/layouts/Topbar.tsx) renders: wordmark + AI warmup badge +
 * backend-connection dot. These tests cover what it actually does now.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// Mock apiFetch so the Topbar's /health + /api/warmup/status calls don't
// hit a real backend.
const apiFetchMock = vi.fn()

vi.mock('../src/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/api/client')>()
  return {
    ...original,
    apiFetch: (path: string) => apiFetchMock(path),
  }
})

import { Topbar } from '../src/layouts/Topbar'
import { useHealthStore } from '../src/hooks/useBackendHealth'

// AI text lives in a span alongside a status-dot element, so the text node is
// split ("AI " + "Ready"). Match on the element's whole textContent.
const wholeText = (want: string) => (_: string, el: Element | null) =>
  el?.textContent === want

beforeEach(() => {
  apiFetchMock.mockReset()
  // Default both endpoints to a polite "no backend"
  apiFetchMock.mockRejectedValue(new Error('no backend in tests'))
  // The health store is a shared singleton — reset it so warmup state from a
  // prior test (whisperReady latches true) doesn't leak into the next.
  useHealthStore.setState({ apiOk: null, whisperReady: null, warmupStatus: null, _refcount: 0, _intervalId: null })
})

afterEach(() => {
  vi.clearAllTimers()
})


describe('Topbar — wordmark', () => {
  it('renders the AI Clip Studio wordmark', () => {
    render(<Topbar />)
    expect(screen.getByText('AI Clip Studio')).toBeTruthy()
  })
})


describe('Topbar — backend connection dot', () => {
  it('renders the connection dot with disconnected color when /health fails', async () => {
    apiFetchMock.mockRejectedValue(new Error('no backend'))
    const { container } = render(<Topbar />)
    // The dot uses title="Backend disconnected" when /health throws.
    await waitFor(() => {
      const dot = container.querySelector('[title="Backend disconnected"]')
      expect(dot).toBeTruthy()
    })
  })

  it('flips to "Backend connected" once /health resolves', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/health') return Promise.resolve({ status: 'ok' })
      return Promise.reject(new Error('not configured'))
    })
    const { container } = render(<Topbar />)
    await waitFor(() => {
      const dot = container.querySelector('[title="Backend connected"]')
      expect(dot).toBeTruthy()
    })
  })
})


describe('Topbar — AI warmup badge', () => {
  it('shows "AI Ready" when warmup status reports loaded=true', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/health') return Promise.resolve({ status: 'ok' })
      if (path === '/api/warmup/status')
        return Promise.resolve({ loaded: true, status: 'ready' })
      return Promise.reject(new Error('not configured'))
    })
    render(<Topbar />)
    await waitFor(() => {
      expect(screen.getByText(wholeText('AI Ready'))).toBeTruthy()
    })
  })

  it('shows "AI Loading" when warmup is still in progress', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/health') return Promise.resolve({ status: 'ok' })
      if (path === '/api/warmup/status')
        return Promise.resolve({ loaded: false, ready: false, status: 'loading' })
      return Promise.reject(new Error('not configured'))
    })
    render(<Topbar />)
    await waitFor(() => {
      expect(screen.getByText(wholeText('AI Loading'))).toBeTruthy()
    })
  })

  it('omits the badge entirely when /api/warmup/status fails', async () => {
    apiFetchMock.mockRejectedValue(new Error('warmup down'))
    render(<Topbar />)
    // Wait for any state settle then assert absence
    await waitFor(() => {
      expect(screen.queryByText(/^AI (Ready|Loading)$/)).toBeNull()
    })
  })
})


describe('Topbar — does NOT render the removed "panel title" feature', () => {
  it('does not render the static "Render Studio" string anywhere', () => {
    render(<Topbar />)
    expect(screen.queryByText('Render Studio')).toBeNull()
  })

  it('does not render per-panel titles (e.g. "New Render", "History")', () => {
    render(<Topbar />)
    expect(screen.queryByText('New Render')).toBeNull()
    expect(screen.queryByText('History')).toBeNull()
    expect(screen.queryByText('Editor')).toBeNull()
  })
})
