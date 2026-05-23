/**
 * job-progress-panel.test.tsx — rendering and behaviour tests for JobProgressPanel
 * and the JobDetailDrawer integration.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Mock useRenderSocket ───────────────────────────────────────────────────────

const mockUseRenderSocket = vi.fn()

vi.mock('../src/hooks/useRenderSocket', () => ({
  useRenderSocket: (jobId: string | null) => mockUseRenderSocket(jobId),
}))

// ── Mock cancelRender ──────────────────────────────────────────────────────────

const mockCancelRender = vi.fn()

vi.mock('../src/api/render', () => ({
  cancelRender: (jobId: string) => mockCancelRender(jobId),
}))

// ── Mock uiStore ───────────────────────────────────────────────────────────────

const mockAddNotification = vi.fn()

vi.mock('../src/stores/uiStore', () => ({
  useUIStore: (selector: (s: { addNotification: typeof mockAddNotification }) => unknown) =>
    selector({ addNotification: mockAddNotification }),
}))

// ── Mock window.confirm ────────────────────────────────────────────────────────

const originalConfirm = window.confirm

// ── Import after mocks ─────────────────────────────────────────────────────────

import { JobProgressPanel } from '../src/features/progress/JobProgressPanel'
import { ProgressMessageLog } from '../src/features/progress/ProgressMessageLog'

// ── Fixture helpers ────────────────────────────────────────────────────────────

function makeSocketState(overrides = {}) {
  return {
    stage: null,
    jobStatus: null,
    jobMessage: null,
    progress: null,
    isConnected: false,
    isTerminal: false,
    error: null,
    ...overrides,
  }
}

function makeProgress(overrides = {}) {
  return {
    total_parts: 3,
    completed_parts: 1,
    failed_parts: 0,
    pending_parts: 1,
    processing_parts: 1,
    in_progress_count: 1,
    active_parts: [{ part_no: 2, status: 'rendering', progress_percent: 45 }],
    stuck_parts: [],
    current_part: 2,
    current_stage: 'rendering',
    overall_progress_percent: 55,
    parts_percent: 60,
    ...overrides,
  }
}

// ── Setup ──────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  window.confirm = vi.fn().mockReturnValue(true)
  mockCancelRender.mockResolvedValue(undefined)

  // Default: disconnected active socket
  mockUseRenderSocket.mockReturnValue(makeSocketState())
})

// ── Terminal job tests ─────────────────────────────────────────────────────────

describe('JobProgressPanel — terminal job', () => {
  it('calls useRenderSocket with null for terminal jobs', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" initialProgress={100} />)
    expect(mockUseRenderSocket).toHaveBeenCalledWith(null)
  })

  it('does not show Cancel button for completed job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" initialProgress={100} />)
    expect(screen.queryByTestId('cancel-render-btn')).toBeNull()
  })

  it('does not show Cancel button for failed job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="failed" initialProgress={80} />)
    expect(screen.queryByTestId('cancel-render-btn')).toBeNull()
  })

  it('shows status label for terminal job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" initialProgress={100} />)
    expect(screen.getByText('Complete')).toBeTruthy()
  })

  it("shows 'Done' connection badge for terminal job", () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" initialProgress={100} />)
    expect(screen.getByText('Done')).toBeTruthy()
  })
})

// ── Active job tests ───────────────────────────────────────────────────────────

describe('JobProgressPanel — active job', () => {
  it('calls useRenderSocket with jobId for active jobs', () => {
    render(<JobProgressPanel jobId="job-active" initialStatus="running" />)
    expect(mockUseRenderSocket).toHaveBeenCalledWith('job-active')
  })

  it('calls useRenderSocket with jobId for queued jobs', () => {
    render(<JobProgressPanel jobId="job-queued" initialStatus="queued" />)
    expect(mockUseRenderSocket).toHaveBeenCalledWith('job-queued')
  })

  it('renders the progress panel container', () => {
    render(<JobProgressPanel jobId="job-active" initialStatus="running" />)
    expect(screen.getByTestId('job-progress-panel')).toBeTruthy()
  })
})

// ── ConnectionStatusBadge ──────────────────────────────────────────────────────

describe('ConnectionStatusBadge — status display', () => {
  it("shows 'Live' when isConnected is true", () => {
    mockUseRenderSocket.mockReturnValue(makeSocketState({ isConnected: true }))
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByText('Live')).toBeTruthy()
  })

  it("shows 'Disconnected' when error and not connected", () => {
    mockUseRenderSocket.mockReturnValue(
      makeSocketState({ isConnected: false, error: 'max_reconnect_attempts_reached' }),
    )
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByText('Disconnected')).toBeTruthy()
  })

  it("shows 'Connecting' when not connected and no error", () => {
    mockUseRenderSocket.mockReturnValue(makeSocketState({ isConnected: false, error: null }))
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByText('Connecting')).toBeTruthy()
  })
})

// ── Stage label ────────────────────────────────────────────────────────────────

describe('JobProgressPanel — stage label', () => {
  it("renders 'Rendering Parts' label for 'rendering' stage", () => {
    mockUseRenderSocket.mockReturnValue(
      makeSocketState({
        stage: 'rendering',
        isConnected: true,
        progress: makeProgress({ current_stage: 'rendering' }),
      }),
    )
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByText('Rendering Parts')).toBeTruthy()
  })

  it("renders 'Analyzing Scenes' for segment_building stage", () => {
    mockUseRenderSocket.mockReturnValue(
      makeSocketState({
        stage: 'segment_building',
        isConnected: true,
      }),
    )
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByText('Analyzing Scenes')).toBeTruthy()
  })
})

// ── ProgressBar ────────────────────────────────────────────────────────────────

describe('JobProgressPanel — ProgressBar', () => {
  it('renders ProgressBar with correct value from WsProgressSummary', () => {
    mockUseRenderSocket.mockReturnValue(
      makeSocketState({
        isConnected: true,
        progress: makeProgress({ overall_progress_percent: 72 }),
      }),
    )
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    // Use getAllByRole since active_parts also renders a ProgressBar
    const bars = screen.getAllByRole('progressbar')
    // First progressbar is the main one
    expect(bars[0].getAttribute('aria-valuenow')).toBe('72')
  })

  it('renders ProgressBar with initialProgress when no socket progress', () => {
    mockUseRenderSocket.mockReturnValue(makeSocketState({ progress: null }))
    render(<JobProgressPanel jobId="job-1" initialStatus="running" initialProgress={35} />)
    // Only main bar when no active parts
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('35')
  })
})

// ── Cancel button ──────────────────────────────────────────────────────────────

describe('JobProgressPanel — Cancel button', () => {
  it('shows Cancel button for running job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByTestId('cancel-render-btn')).toBeTruthy()
  })

  it('shows Cancel button for queued job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="queued" />)
    expect(screen.getByTestId('cancel-render-btn')).toBeTruthy()
  })

  it('does not show Cancel button for completed job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" />)
    expect(screen.queryByTestId('cancel-render-btn')).toBeNull()
  })

  it('fires window.confirm before calling cancelRender', async () => {
    const user = userEvent.setup()
    render(<JobProgressPanel jobId="job-cancel" initialStatus="running" />)
    await user.click(screen.getByTestId('cancel-render-btn'))
    expect(window.confirm).toHaveBeenCalledWith('Cancel this render job?')
    await waitFor(() => expect(mockCancelRender).toHaveBeenCalledWith('job-cancel'))
  })

  it('does NOT call cancelRender if confirm returns false', async () => {
    ;(window.confirm as ReturnType<typeof vi.fn>).mockReturnValue(false)
    const user = userEvent.setup()
    render(<JobProgressPanel jobId="job-cancel" initialStatus="running" />)
    await user.click(screen.getByTestId('cancel-render-btn'))
    expect(window.confirm).toHaveBeenCalled()
    expect(mockCancelRender).not.toHaveBeenCalled()
  })

  it('does not fire twice on double-click (loading guard)', async () => {
    // Make cancelRender hang so we can test the guard
    let resolveFn!: () => void
    mockCancelRender.mockReturnValue(new Promise<void>((res) => { resolveFn = res }))

    const user = userEvent.setup()
    render(<JobProgressPanel jobId="job-cancel" initialStatus="running" />)

    const btn = screen.getByTestId('cancel-render-btn')
    await user.click(btn)

    // After first click button should be in loading state (disabled)
    await waitFor(() => expect(btn).toBeDisabled())

    // Fire a raw click event (bypasses pointer-events:none check from userEvent)
    // The component guard (isCanceling) should prevent a second call
    fireEvent.click(btn)

    resolveFn()
    expect(mockCancelRender).toHaveBeenCalledTimes(1)
  })

  it('shows error notification when cancelRender throws', async () => {
    mockCancelRender.mockRejectedValue(new Error('Network error'))
    const user = userEvent.setup()
    render(<JobProgressPanel jobId="job-cancel" initialStatus="running" />)
    await user.click(screen.getByTestId('cancel-render-btn'))
    await waitFor(() =>
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error' }),
      ),
    )
  })
})

// ── Message log ────────────────────────────────────────────────────────────────

describe('JobProgressPanel — message log', () => {
  it('shows up to 5 messages without collapsing', () => {
    const msgs = ['msg1', 'msg2', 'msg3', 'msg4', 'msg5']
    render(<ProgressMessageLog messages={msgs} />)
    expect(screen.getByTestId('progress-message-log')).toBeTruthy()
  })

  it('is absent when messages array is empty', () => {
    const { container } = render(<ProgressMessageLog messages={[]} />)
    expect(container.firstChild).toBeNull()
  })
})

// ── JobDetailDrawer integration ────────────────────────────────────────────────

// Mock quality store for drawer tests
const mockFetchJobSummary = vi.fn()
vi.mock('../src/stores/qualityStore', () => ({
  useQualityStore: (selector: (s: unknown) => unknown) =>
    selector({
      summaries: {},
      reports: {},
      loading: {},
      errors: {},
      fetchJobSummary: mockFetchJobSummary,
      refreshJobSummary: vi.fn(),
      fetchPartQuality: vi.fn(),
      refreshPartQuality: vi.fn(),
      clearJob: vi.fn(),
    }),
}))

vi.mock('../src/api/jobs', () => ({
  getJob: vi.fn().mockResolvedValue({
    job_id: 'job-drawer',
    kind: 'render',
    status: 'running',
    stage: 'rendering',
    progress_percent: 55,
    message: 'Processing clip 3',
    payload_json: '{}',
    result_json: '{}',
    created_at: '2026-05-23T00:00:00Z',
    updated_at: '2026-05-23T00:00:00Z',
  }),
}))

describe('JobDetailDrawer integration', () => {
  it('contains a JobProgressPanel in its rendered output', async () => {
    const { JobDetailDrawer } = await import('../src/features/jobs/JobDetailDrawer')
    render(<JobDetailDrawer jobId="job-drawer" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('job-progress-panel')).toBeTruthy())
  })

  it('QualityPanel is still present below progress', async () => {
    const { JobDetailDrawer } = await import('../src/features/jobs/JobDetailDrawer')
    render(<JobDetailDrawer jobId="job-drawer" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('quality-panel')).toBeTruthy())
  })

  it('does not contain "Live progress — available when running" static text', async () => {
    const { JobDetailDrawer } = await import('../src/features/jobs/JobDetailDrawer')
    render(<JobDetailDrawer jobId="job-drawer" onClose={() => {}} />)
    await waitFor(() =>
      expect(screen.queryByText(/Live progress — available when running/i)).toBeNull(),
    )
  })
})

// ── Teardown ───────────────────────────────────────────────────────────────────

afterEach(() => {
  window.confirm = originalConfirm
})
