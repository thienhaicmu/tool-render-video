/**
 * render-status-banner-priority.test.tsx — Pha 1.3 coverage.
 *
 * The four render-screen advisories (cancelling / stuck / watchdog / WS)
 * were consolidated into one adaptive status line that shows exactly one
 * status by severity priority:
 *   cancelling > stuck > watchdog > ws-error > ws-reconnecting > ws-polling
 *
 * These tests feed prop combinations and assert the higher-priority
 * status wins and lower ones are suppressed. (The watchdog tier is
 * elapsed-time gated via internal state, so it's exercised manually
 * rather than here.)
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepRendering } from '../src/features/clip-studio/render/steps/StepRendering'
import { useT } from '../src/features/clip-studio/render/i18n'
import type { WsProgressSummary } from '../src/types/api'

const t = useT('EN')

type Props = Parameters<typeof StepRendering>[0]

function renderBanner(overrides: Partial<Props>) {
  const base: Props = {
    jobId: 'job-1',
    stage: 'render',
    jobStatus: 'running',
    progress: null,
    jobMessage: '',
    isTerminal: false,
    liveParts: [],
    liveEvents: [],
    wsError: null,
    wsReconnecting: false,
    wsPolling: false,
    t,
    aspectRatio: '9:16',
  }
  return render(<StepRendering {...base} {...overrides} />)
}

const stuckProgress = {
  total_parts: 1, completed_parts: 0, failed_parts: 0, pending_parts: 0,
  processing_parts: 1, in_progress_count: 1, active_parts: [],
  stuck_parts: [{ part_no: 1, status: 'rendering', stuck_seconds: 130 }],
  current_part: 1, current_stage: 'render',
  overall_progress_percent: 40, parts_percent: 0,
} as unknown as WsProgressSummary

describe('Pha 1.3 — render status line priority', () => {
  it('cancelling outranks ws-polling', () => {
    renderBanner({ jobStatus: 'cancelling', wsPolling: true })
    expect(screen.getByText(/Cancelling render/i)).toBeInTheDocument()
    expect(screen.queryByText(/Refreshing every 5s/i)).not.toBeInTheDocument()
  })

  it('stuck outranks ws-reconnecting', () => {
    renderBanner({ progress: stuckProgress, wsReconnecting: true })
    expect(screen.getByText(/Clip #1 looks unusually slow/i)).toBeInTheDocument()
    expect(screen.queryByText(/Reconnecting/i)).not.toBeInTheDocument()
  })

  it('ws-error outranks reconnecting and polling', () => {
    renderBanner({ wsError: 'boom', wsReconnecting: true, wsPolling: true })
    expect(screen.getByText(/Connection lost/i)).toBeInTheDocument()
    expect(screen.queryByText(/Reconnecting/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Refreshing every 5s/i)).not.toBeInTheDocument()
  })

  it('ws-reconnecting outranks ws-polling', () => {
    renderBanner({ wsReconnecting: true, wsPolling: true })
    expect(screen.getByText(/Reconnecting/i)).toBeInTheDocument()
    expect(screen.queryByText(/Refreshing every 5s/i)).not.toBeInTheDocument()
  })

  it('shows nothing when terminal', () => {
    renderBanner({ isTerminal: true, jobStatus: 'completed', wsError: 'boom' })
    expect(screen.queryByText(/Connection lost/i)).not.toBeInTheDocument()
  })
})
