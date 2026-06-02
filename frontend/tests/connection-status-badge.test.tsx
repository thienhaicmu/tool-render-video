/**
 * connection-status-badge.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Tests the current ConnectionStatusBadge component
 * (features/progress/ConnectionStatusBadge.tsx). The old test file
 * (job-progress-panel.test.tsx) was deleted in commit 839752e because it
 * asserted obsolete labels ('Live', 'Disconnected', 'Connecting') tied to
 * the wrong WS state shape. This file covers the current 5-state shape:
 *   connecting | live | reconnecting | disconnected | terminal
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ConnectionStatusBadge } from '../src/features/progress/ConnectionStatusBadge'


describe('ConnectionStatusBadge — label per status', () => {
  it('renders "Connecting" for connecting state', () => {
    render(<ConnectionStatusBadge status="connecting" />)
    expect(screen.getByText('Connecting')).toBeTruthy()
  })

  it('renders "Live" for live state', () => {
    render(<ConnectionStatusBadge status="live" />)
    expect(screen.getByText('Live')).toBeTruthy()
  })

  it('renders "Reconnecting" for reconnecting state', () => {
    render(<ConnectionStatusBadge status="reconnecting" />)
    expect(screen.getByText('Reconnecting')).toBeTruthy()
  })

  it('renders "Disconnected" for disconnected state', () => {
    render(<ConnectionStatusBadge status="disconnected" />)
    expect(screen.getByText('Disconnected')).toBeTruthy()
  })

  it('renders "Done" for terminal state', () => {
    render(<ConnectionStatusBadge status="terminal" />)
    expect(screen.getByText('Done')).toBeTruthy()
  })
})


describe('ConnectionStatusBadge — size prop', () => {
  it('accepts size="sm" without crashing', () => {
    const { container } = render(<ConnectionStatusBadge status="live" size="sm" />)
    expect(container.textContent).toBe('Live')
  })

  it('accepts size="md" without crashing', () => {
    const { container } = render(<ConnectionStatusBadge status="live" size="md" />)
    expect(container.textContent).toBe('Live')
  })

  it('defaults to sm when size omitted', () => {
    const { container } = render(<ConnectionStatusBadge status="live" />)
    expect(container.textContent).toBe('Live')
  })
})
