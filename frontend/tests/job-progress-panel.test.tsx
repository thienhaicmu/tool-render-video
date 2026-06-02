/**
 * job-progress-panel.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Replaces the deleted job-progress-panel.test.tsx coverage. The current
 * JobProgressPanel routes to one of two inner components based on
 * isTerminalStatus(initialStatus):
 *   - terminal:  TerminalProgressPanel (no WS) — shows status label + bar
 *   - active:    ActiveProgressPanel via useRenderSocket(jobId)
 *
 * Both render `data-testid="job-progress-panel"` so a smoke check
 * confirms the right branch was taken without coupling to internal markup.
 * Cancel button: data-testid="cancel-render-btn", shown only for active.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// useRenderSocket must be mocked — real implementation tries to open a
// WebSocket which jsdom doesn't support.
const useRenderSocketMock = vi.fn()

vi.mock('../src/hooks/useRenderSocket', () => ({
  useRenderSocket: (jobId: string | null) => useRenderSocketMock(jobId),
}))

const cancelRenderMock = vi.fn()
vi.mock('../src/api/render', () => ({
  cancelRender: (...args: unknown[]) => cancelRenderMock(...args),
}))

import { JobProgressPanel } from '../src/features/progress/JobProgressPanel'
import { useUIStore } from '../src/stores/uiStore'


function emptySocketState() {
  return {
    stage: null,
    jobStatus: null,
    jobMessage: null,
    progress: null,
    liveParts: [],
    isConnected: false,
    isReconnecting: false,
    isTerminal: false,
    error: null,
  }
}


beforeEach(() => {
  vi.clearAllMocks()
  useRenderSocketMock.mockReturnValue(emptySocketState())
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'home',
    notifications: [],
  })
})


describe('JobProgressPanel — active-job branch (calls useRenderSocket)', () => {
  it('calls useRenderSocket with jobId for running jobs', () => {
    render(<JobProgressPanel jobId="job-running-1" initialStatus="running" />)
    expect(useRenderSocketMock).toHaveBeenCalledWith('job-running-1')
  })

  it('calls useRenderSocket with jobId for queued jobs', () => {
    render(<JobProgressPanel jobId="job-queued-1" initialStatus="queued" />)
    expect(useRenderSocketMock).toHaveBeenCalledWith('job-queued-1')
  })

  it('renders the job-progress-panel container for active jobs', () => {
    render(<JobProgressPanel jobId="job-running-1" initialStatus="running" />)
    expect(screen.getByTestId('job-progress-panel')).toBeTruthy()
  })
})


describe('JobProgressPanel — terminal-job branch (no WS connection)', () => {
  it.each(['completed', 'failed', 'cancelled', 'interrupted'])(
    'calls useRenderSocket with null for terminal status: %s',
    (status) => {
      render(<JobProgressPanel jobId="job-1" initialStatus={status} />)
      expect(useRenderSocketMock).toHaveBeenCalledWith(null)
    },
  )

  it('still renders the panel container in terminal mode', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" />)
    expect(screen.getByTestId('job-progress-panel')).toBeTruthy()
  })

  it('does not render the Cancel button in terminal mode', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" />)
    expect(screen.queryByTestId('cancel-render-btn')).toBeNull()
  })
})


describe('JobProgressPanel — Cancel button', () => {
  it('shows Cancel button for running job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    expect(screen.getByTestId('cancel-render-btn')).toBeTruthy()
  })

  it('shows Cancel button for queued job', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="queued" />)
    expect(screen.getByTestId('cancel-render-btn')).toBeTruthy()
  })

  it('clicking Cancel fires window.confirm before cancelRender', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    cancelRenderMock.mockResolvedValue(undefined)

    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    await userEvent.click(screen.getByTestId('cancel-render-btn'))

    expect(confirmSpy).toHaveBeenCalled()
    expect(cancelRenderMock).toHaveBeenCalledWith('job-1')
    confirmSpy.mockRestore()
  })

  it('does NOT call cancelRender if confirm returns false', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    await userEvent.click(screen.getByTestId('cancel-render-btn'))

    expect(cancelRenderMock).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('adds an error notification when cancelRender throws', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    cancelRenderMock.mockRejectedValue(new Error('backend down'))

    render(<JobProgressPanel jobId="job-1" initialStatus="running" />)
    await userEvent.click(screen.getByTestId('cancel-render-btn'))

    // The handler awaits cancelRender and adds a notification on failure
    await new Promise((r) => setTimeout(r, 10))
    const notifs = useUIStore.getState().notifications
    expect(notifs.length).toBeGreaterThanOrEqual(1)
    expect(notifs[notifs.length - 1].type).toBe('error')
    expect(notifs[notifs.length - 1].title).toBe('Cancel failed')
    confirmSpy.mockRestore()
  })
})


describe('JobProgressPanel — progress display', () => {
  it('renders the initialProgress percentage when terminal and progress > 0', () => {
    render(<JobProgressPanel jobId="job-1" initialStatus="completed" initialProgress={87} />)
    expect(screen.getByText('87%')).toBeTruthy()
  })

  it('uses progress from socket when active', () => {
    useRenderSocketMock.mockReturnValue({
      ...emptySocketState(),
      progress: { overall_progress_percent: 42, current_stage: 'rendering' },
    })
    render(<JobProgressPanel jobId="job-1" initialStatus="running" initialProgress={0} />)
    expect(screen.getByText('42%')).toBeTruthy()
  })
})
