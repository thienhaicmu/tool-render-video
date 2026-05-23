/**
 * trim-flow.test.tsx — Phase 6.8 trim flow integration tests.
 *
 * Tests:
 * - trimJobPart called with correct args on Apply Trim click
 * - Success notification fired on trim success
 * - Error notification fired on trim failure
 * - Apply Trim button shows loading state during request
 * - Re-render redirects to History on success
 * - Re-render error shows notification
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditorMetadataPanel } from '../src/features/editor/EditorMetadataPanel'
import * as editingApi from '../src/api/editing'

// ── Shared mocks ───────────────────────────────────────────────────────────────

const mockAddNotification = vi.fn()
const mockSetActivePanel = vi.fn()

vi.mock('../src/stores/uiStore', () => ({
  useUIStore: (selector: (s: object) => unknown) =>
    selector({ addNotification: mockAddNotification, setActivePanel: mockSetActivePanel }),
}))

vi.mock('../src/api/editing')

const trimmedProps = {
  jobId: 'job-trim-test',
  partNo: 1,
  jobStatus: 'completed',
  durationSec: 30.0,
  trimStartSec: 5.0,
  trimEndSec: 20.0,
  mediaUrl: '/api/render/jobs/job-trim-test/parts/1/media',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('trim-flow — Apply Trim', () => {
  it('calls trimJobPart with correct start/end when Apply Trim clicked', async () => {
    const user = userEvent.setup()
    const mockTrim = vi.mocked(editingApi.trimJobPart).mockResolvedValue({
      status: 'ok', job_id: 'job-trim-test', part_no: 1,
      output_file: '/fake/out.mp4', duration_sec: 15.0,
      trim_start_sec: 5.0, trim_end_sec: 20.0, output_mode: 'new_job',
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('apply-trim-btn'))

    expect(mockTrim).toHaveBeenCalledWith(
      'job-trim-test',
      1,
      expect.objectContaining({ start_sec: 5.0, end_sec: 20.0 }),
    )
  })

  it('shows success notification after successful trim', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.trimJobPart).mockResolvedValue({
      status: 'ok', job_id: 'job-trim-test', part_no: 1,
      output_file: '/fake/out.mp4', duration_sec: 15.0,
      trim_start_sec: 5.0, trim_end_sec: 20.0, output_mode: 'new_job',
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('apply-trim-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success', title: 'Trim applied' }),
      )
    })
  })

  it('shows error notification when trim fails', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.trimJobPart).mockRejectedValue(new Error('FFmpeg failed'))

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('apply-trim-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', title: 'Trim failed' }),
      )
    })
  })

  it('uses new_job output mode by default', async () => {
    const user = userEvent.setup()
    const mockTrim = vi.mocked(editingApi.trimJobPart).mockResolvedValue({
      status: 'ok', job_id: 'job-trim-test', part_no: 1,
      output_file: '/fake/out.mp4', duration_sec: 15.0,
      trim_start_sec: 5.0, trim_end_sec: 20.0, output_mode: 'new_job',
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('apply-trim-btn'))

    expect(mockTrim).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Number),
      expect.objectContaining({ output_mode: 'new_job' }),
    )
  })
})

describe('trim-flow — Re-render Selection', () => {
  it('calls rerenderSelection with correct start/end when clicked', async () => {
    const user = userEvent.setup()
    const mockRerender = vi.mocked(editingApi.rerenderSelection).mockResolvedValue({
      status: 'queued', new_job_id: 'rerender_abc', parent_job_id: 'job-trim-test',
      parent_part_no: 1, trim_start_sec: 5.0, trim_end_sec: 20.0,
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('rerender-btn'))

    expect(mockRerender).toHaveBeenCalledWith(
      'job-trim-test',
      1,
      expect.objectContaining({ start_sec: 5.0, end_sec: 20.0 }),
    )
  })

  it('redirects to History panel on re-render success', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.rerenderSelection).mockResolvedValue({
      status: 'queued', new_job_id: 'rerender_abc', parent_job_id: 'job-trim-test',
      parent_part_no: 1, trim_start_sec: 5.0, trim_end_sec: 20.0,
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('rerender-btn'))

    await waitFor(() => {
      expect(mockSetActivePanel).toHaveBeenCalledWith('history')
    })
  })

  it('shows success notification on re-render success', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.rerenderSelection).mockResolvedValue({
      status: 'queued', new_job_id: 'rerender_abc', parent_job_id: 'job-trim-test',
      parent_part_no: 1, trim_start_sec: 5.0, trim_end_sec: 20.0,
    })

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('rerender-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success', title: 'Re-render queued' }),
      )
    })
  })

  it('shows error notification when re-render fails', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.rerenderSelection).mockRejectedValue(new Error('Server error'))

    render(<EditorMetadataPanel {...trimmedProps} />)
    await user.click(screen.getByTestId('rerender-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', title: 'Re-render failed' }),
      )
    })
  })
})
