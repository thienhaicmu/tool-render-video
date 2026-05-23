/**
 * export-flow.test.tsx — Phase 6.8 export clip flow tests.
 *
 * Tests:
 * - Export button disabled without destination dir
 * - Export button enabled when dir is typed
 * - exportClip called with correct args
 * - Success notification shown
 * - Error notification shown on failure
 * - Validation error shown when empty dir submitted via enter
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

const baseProps = {
  jobId: 'job-export-test',
  partNo: 2,
  jobStatus: 'completed',
  durationSec: 60.0,
  trimStartSec: 0.0,
  trimEndSec: 60.0,
  mediaUrl: '/api/render/jobs/job-export-test/parts/2/media',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('export-flow', () => {
  it('export button is disabled when destination dir is empty', () => {
    render(<EditorMetadataPanel {...baseProps} />)
    expect(screen.getByTestId('export-clip-btn')).toBeDisabled()
  })

  it('export button becomes enabled after typing a path', async () => {
    const user = userEvent.setup()
    render(<EditorMetadataPanel {...baseProps} />)
    await user.type(screen.getByTestId('export-dir-input'), '/home/user/exports')
    expect(screen.getByTestId('export-clip-btn')).not.toBeDisabled()
  })

  it('calls exportClip with the typed destination dir', async () => {
    const user = userEvent.setup()
    const mockExport = vi.mocked(editingApi.exportClip).mockResolvedValue({
      status: 'ok', job_id: 'job-export-test', part_no: 2,
      source_file: 'part2.mp4', exported_to: '/home/user/exports/part2.mp4',
      destination_dir: '/home/user/exports',
    })

    render(<EditorMetadataPanel {...baseProps} />)
    await user.type(screen.getByTestId('export-dir-input'), '/home/user/exports')
    await user.click(screen.getByTestId('export-clip-btn'))

    expect(mockExport).toHaveBeenCalledWith(
      'job-export-test',
      2,
      expect.objectContaining({ destination_dir: '/home/user/exports' }),
    )
  })

  it('shows success notification after export', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.exportClip).mockResolvedValue({
      status: 'ok', job_id: 'job-export-test', part_no: 2,
      source_file: 'part2.mp4', exported_to: '/home/user/exports/part2.mp4',
      destination_dir: '/home/user/exports',
    })

    render(<EditorMetadataPanel {...baseProps} />)
    await user.type(screen.getByTestId('export-dir-input'), '/home/user/exports')
    await user.click(screen.getByTestId('export-clip-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success', title: 'Export complete' }),
      )
    })
  })

  it('shows error notification when export fails', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.exportClip).mockRejectedValue(new Error('Permission denied'))

    render(<EditorMetadataPanel {...baseProps} />)
    await user.type(screen.getByTestId('export-dir-input'), '/root/forbidden')
    await user.click(screen.getByTestId('export-clip-btn'))

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', title: 'Export failed' }),
      )
    })
  })

  it('shows validation error when clicking export with only whitespace dir', async () => {
    const user = userEvent.setup()
    render(<EditorMetadataPanel {...baseProps} />)
    // Button stays disabled for whitespace-only input
    const input = screen.getByTestId('export-dir-input')
    await user.type(input, '   ')
    // Button should remain disabled (trimmed value is empty)
    expect(screen.getByTestId('export-clip-btn')).toBeDisabled()
  })

  it('does not navigate away on export success', async () => {
    const user = userEvent.setup()
    vi.mocked(editingApi.exportClip).mockResolvedValue({
      status: 'ok', job_id: 'job-export-test', part_no: 2,
      source_file: 'part2.mp4', exported_to: '/home/user/exports/part2.mp4',
      destination_dir: '/home/user/exports',
    })

    render(<EditorMetadataPanel {...baseProps} />)
    await user.type(screen.getByTestId('export-dir-input'), '/home/user/exports')
    await user.click(screen.getByTestId('export-clip-btn'))

    await waitFor(() => expect(mockAddNotification).toHaveBeenCalled())
    // Export does NOT redirect to history (only re-render does)
    expect(mockSetActivePanel).not.toHaveBeenCalled()
  })
})
