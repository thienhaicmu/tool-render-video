/**
 * job-detail-drawer.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Replaces the deleted job-detail-open-editor.test.tsx which asserted the
 * "Open in Editor" English label. The current button uses Vietnamese
 * label "✏ Chỉnh sửa" and is conditionally rendered when canEditor:
 *   canEditor = ['completed', 'partial', 'completed_with_errors'].includes(job.status)
 *
 * The button onClick calls openEditor(jobId, 1) then setActivePanel('editor').
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock api/jobs and api/render to avoid real backend calls
const getJobMock = vi.fn()
const getJobPartsMock = vi.fn()
const retryRenderMock = vi.fn()
const resumeRenderMock = vi.fn()
const deleteJobMock = vi.fn()

vi.mock('../src/api/jobs', () => ({
  getJob: (...args: unknown[]) => getJobMock(...args),
  getJobParts: (...args: unknown[]) => getJobPartsMock(...args),
  deleteJob: (...args: unknown[]) => deleteJobMock(...args),
}))

vi.mock('../src/api/render', () => ({
  retryRender: (...args: unknown[]) => retryRenderMock(...args),
  resumeRender: (...args: unknown[]) => resumeRenderMock(...args),
}))

import { JobDetailDrawer } from '../src/features/jobs/JobDetailDrawer'
import { useEditorStore } from '../src/stores/editorStore'
import { useUIStore } from '../src/stores/uiStore'


function jobFixture(overrides: Partial<{
  job_id: string
  status: string
  stage: string
  progress_percent: number
  message: string
  payload_json: string
  result_json: string
  created_at: string
  updated_at: string
}> = {}) {
  return {
    job_id: 'job-test-1',
    status: 'completed',
    stage: 'done',
    progress_percent: 100,
    message: '',
    payload_json: '{}',
    result_json: '{}',
    created_at: '2026-06-02T10:00:00Z',
    updated_at: '2026-06-02T10:05:00Z',
    ...overrides,
  }
}


beforeEach(() => {
  vi.clearAllMocks()
  getJobPartsMock.mockResolvedValue([])
  useEditorStore.setState({ jobId: null })
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'home',
    notifications: [],
  })
})


describe('JobDetailDrawer — Edit button visibility per job status', () => {
  it.each(['completed', 'partial', 'completed_with_errors'])(
    'shows "Chỉnh sửa" Edit button for terminal-success status: %s',
    async (status) => {
      getJobMock.mockResolvedValue(jobFixture({ status }))
      render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
      await waitFor(() => {
        expect(screen.getByText(/Chỉnh sửa/)).toBeTruthy()
      })
    },
  )

  it.each(['failed', 'running', 'queued', 'cancelled', 'interrupted'])(
    'hides Edit button for non-success status: %s',
    async (status) => {
      getJobMock.mockResolvedValue(jobFixture({ status }))
      render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
      // Wait for loading to clear (status badge appears)
      await waitFor(() => {
        // Loading screen has spinner; once the badge renders, fetch is done.
        // Use a non-throwing query for the Edit button.
        expect(screen.queryByText(/Chỉnh sửa/)).toBeNull()
      })
    },
  )
})


describe('JobDetailDrawer — Edit button click navigates to editor', () => {
  it('clicking "Chỉnh sửa" calls openEditor(jobId, 1)', async () => {
    getJobMock.mockResolvedValue(jobFixture({ status: 'completed' }))
    const openEditorSpy = vi.fn()
    useEditorStore.setState({ openEditor: openEditorSpy })

    render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
    const btn = await screen.findByText(/Chỉnh sửa/)
    await userEvent.click(btn)

    expect(openEditorSpy).toHaveBeenCalledTimes(1)
    expect(openEditorSpy).toHaveBeenCalledWith('job-test-1', 1)
  })

  it('clicking "Chỉnh sửa" sets activePanel to "editor"', async () => {
    getJobMock.mockResolvedValue(jobFixture({ status: 'partial' }))
    useEditorStore.setState({ openEditor: vi.fn() })

    render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
    const btn = await screen.findByText(/Chỉnh sửa/)
    await userEvent.click(btn)

    expect(useUIStore.getState().activePanel).toBe('editor')
  })

  it('does not invoke any backend mutation on Edit click', async () => {
    getJobMock.mockResolvedValue(jobFixture({ status: 'completed' }))
    useEditorStore.setState({ openEditor: vi.fn() })

    render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
    const btn = await screen.findByText(/Chỉnh sửa/)
    await userEvent.click(btn)

    expect(retryRenderMock).not.toHaveBeenCalled()
    expect(resumeRenderMock).not.toHaveBeenCalled()
    expect(deleteJobMock).not.toHaveBeenCalled()
  })
})


describe('JobDetailDrawer — fetch contract', () => {
  it('calls getJob(jobId) on mount', async () => {
    getJobMock.mockResolvedValue(jobFixture({ status: 'completed' }))
    render(<JobDetailDrawer jobId="job-test-fetch" onClose={() => {}} />)
    await waitFor(() => {
      expect(getJobMock).toHaveBeenCalledWith('job-test-fetch')
    })
  })

  it('renders the status badge label after fetch resolves', async () => {
    getJobMock.mockResolvedValue(jobFixture({ status: 'completed' }))
    render(<JobDetailDrawer jobId="job-test-1" onClose={() => {}} />)
    await waitFor(() => {
      // STATUS_CFG.completed.label === 'Xong'
      expect(screen.getByText('Xong')).toBeTruthy()
    })
  })
})
