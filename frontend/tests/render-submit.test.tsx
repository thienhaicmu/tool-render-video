/**
 * render-submit.test.tsx — submit flow tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RenderSetupScreen } from '../src/features/render/RenderSetupScreen'
import { useUIStore } from '../src/stores/uiStore'
import { useRenderStore } from '../src/stores/renderStore'

// Mock the render API so it doesn't actually make HTTP calls
vi.mock('../src/api/render', () => ({
  submitRender: vi.fn(),
}))

import { submitRender as mockSubmitRender } from '../src/api/render'

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'render',
    notifications: [],
  })
  useRenderStore.setState({
    jobs: {},
    activeJobId: null,
  })
})

/** Fill out the form with the minimum valid values via DOM. */
async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  const outputDir = screen.getByTestId('output-dir-input')
  await user.type(outputDir, 'D:\\renders\\test')

  const ytInput = screen.getByTestId('youtube-url-input')
  await user.type(ytInput, 'https://youtube.com/watch?v=abc123')
}

describe('render-submit — success path', () => {
  it('submit with valid form → calls submitRender with correct payload', async () => {
    vi.mocked(mockSubmitRender).mockResolvedValue({ job_id: 'job-123', status: 'queued' })
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      expect(mockSubmitRender).toHaveBeenCalledTimes(1)
    })

    const calledWith = vi.mocked(mockSubmitRender).mock.calls[0][0]
    expect(calledWith.output_dir).toBe('D:\\renders\\test')
    expect(calledWith.youtube_url).toBe('https://youtube.com/watch?v=abc123')
    expect(calledWith.source_mode).toBe('youtube')
  })

  it('submit success → addNotification called with type success', async () => {
    vi.mocked(mockSubmitRender).mockResolvedValue({ job_id: 'job-123', status: 'queued' })
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      expect(notifications.some((n) => n.type === 'success')).toBe(true)
    })
  })

  it('submit success → notification contains job id', async () => {
    vi.mocked(mockSubmitRender).mockResolvedValue({ job_id: 'job-123', status: 'queued' })
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      const successNotif = notifications.find((n) => n.type === 'success')
      expect(successNotif?.title).toContain('job-123')
    })
  })

  it('submit success → setActivePanel called with "history"', async () => {
    vi.mocked(mockSubmitRender).mockResolvedValue({ job_id: 'job-123', status: 'queued' })
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      expect(useUIStore.getState().activePanel).toBe('history')
    })
  })
})

describe('render-submit — error path', () => {
  it('submit with API error → addNotification called with type error', async () => {
    vi.mocked(mockSubmitRender).mockRejectedValue(new Error('Network error'))
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      expect(notifications.some((n) => n.type === 'error')).toBe(true)
    })
  })

  it('submit with API error → error notification has fallback message', async () => {
    vi.mocked(mockSubmitRender).mockRejectedValue(new Error('Something broke'))
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      const errorNotif = notifications.find((n) => n.type === 'error')
      expect(errorNotif).toBeTruthy()
    })
  })
})

describe('render-submit — disabled state', () => {
  it('submit button is disabled when form is invalid (empty output_dir)', () => {
    render(<RenderSetupScreen />)
    const submitBtn = screen.getByTestId('submit-render-button') as HTMLButtonElement
    // output_dir is empty by default → form invalid → button disabled
    expect(submitBtn.disabled).toBe(true)
  })

  it('submit button is enabled when form is valid', async () => {
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)

    const submitBtn = screen.getByTestId('submit-render-button') as HTMLButtonElement
    expect(submitBtn.disabled).toBe(false)
  })

  it('submit button shows submitting state while request is in flight', async () => {
    // Create a promise that we control
    let resolveSubmit!: (v: { job_id: string; status: string }) => void
    const pending = new Promise<{ job_id: string; status: string }>((res) => {
      resolveSubmit = res
    })
    vi.mocked(mockSubmitRender).mockReturnValue(pending)

    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    await fillValidForm(user)
    await user.click(screen.getByTestId('submit-render-button'))

    // Button should be disabled while submitting (loading state)
    const submitBtn = screen.getByTestId('submit-render-button') as HTMLButtonElement
    expect(submitBtn.disabled).toBe(true)

    // Resolve to clean up and avoid act() warning
    await waitFor(async () => {
      resolveSubmit({ job_id: 'job-abc', status: 'queued' })
    })
  })
})
