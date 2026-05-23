/**
 * job-status.test.tsx — tests for JobStatusBadge component.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { JobStatusBadge } from '../src/features/jobs/JobStatusBadge'

describe('JobStatusBadge', () => {
  it('renders "Complete" for completed', () => {
    render(<JobStatusBadge status="completed" />)
    expect(screen.getByText('Complete')).toBeTruthy()
  })

  it('renders "Rendering" for running', () => {
    render(<JobStatusBadge status="running" />)
    expect(screen.getByText('Rendering')).toBeTruthy()
  })

  it('renders "Failed" for failed', () => {
    render(<JobStatusBadge status="failed" />)
    expect(screen.getByText('Failed')).toBeTruthy()
  })

  it('renders "Partial" for partial', () => {
    render(<JobStatusBadge status="partial" />)
    expect(screen.getByText('Partial')).toBeTruthy()
  })

  it('renders "Queued" for queued', () => {
    render(<JobStatusBadge status="queued" />)
    expect(screen.getByText('Queued')).toBeTruthy()
  })

  it('renders "Canceled" for cancelled (UK spelling)', () => {
    render(<JobStatusBadge status="cancelled" />)
    expect(screen.getByText('Canceled')).toBeTruthy()
  })

  it('renders "Canceled" for canceled (US spelling)', () => {
    render(<JobStatusBadge status="canceled" />)
    expect(screen.getByText('Canceled')).toBeTruthy()
  })

  it('renders "Interrupted" for interrupted', () => {
    render(<JobStatusBadge status="interrupted" />)
    expect(screen.getByText('Interrupted')).toBeTruthy()
  })

  it('renders "Canceling" for cancelling', () => {
    render(<JobStatusBadge status="cancelling" />)
    expect(screen.getByText('Canceling')).toBeTruthy()
  })

  it('renders "Unknown" for an unknown status', () => {
    render(<JobStatusBadge status="some_future_status" />)
    expect(screen.getByText('Unknown')).toBeTruthy()
  })
})
