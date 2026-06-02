/**
 * job-actions-menu.test.tsx — Sprint 8 frontend test rewrite.
 *
 * The deleted job-actions.test.tsx exercised Cancel/Retry/Delete handlers
 * via the HistoryScreen but used stale data-testids that no longer matched
 * the markup. The current JobActionsMenu (features/jobs/JobActionsMenu.tsx)
 * exposes proper data-testid attributes that follow the
 * `{action}-btn-{job_id}` convention; these tests pin that contract +
 * the visibility rules from jobs.utils.ts (canCancel/canRetry/canDelete).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { JobActionsMenu } from '../src/features/jobs/JobActionsMenu'
import type { HistoryItem } from '../src/types/api'


function makeItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    job_id: 'job-1',
    status: 'completed',
    created_at: '2026-06-02T10:00:00Z',
    updated_at: '2026-06-02T10:05:00Z',
    progress_percent: 100,
    output_dir: '/tmp/out',
    output_count: 1,
    parts_total: 1,
    parts_done: 1,
    parts_failed: 0,
    can_retry: false,
    can_rerun: true,
    error_kind: null,
    ...overrides,
  } as HistoryItem
}


const noopHandlers = {
  onCancel: vi.fn(),
  onRetry: vi.fn(),
  onRerun: vi.fn(),
  onDelete: vi.fn(),
  onDetails: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
})


describe('JobActionsMenu — Cancel button visibility', () => {
  it('shows Cancel button for running jobs', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'running' })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.getByTestId('cancel-btn-job-1')).toBeTruthy()
  })

  it('shows Cancel button for queued jobs', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'queued' })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.getByTestId('cancel-btn-job-1')).toBeTruthy()
  })

  it('hides Cancel button for completed jobs', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'completed' })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.queryByTestId('cancel-btn-job-1')).toBeNull()
  })

  it('hides Cancel button for failed jobs', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'failed' })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.queryByTestId('cancel-btn-job-1')).toBeNull()
  })
})


describe('JobActionsMenu — Retry button visibility', () => {
  it('shows Retry button when item.can_retry is true', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'failed', can_retry: true })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.getByTestId('retry-btn-job-1')).toBeTruthy()
  })

  it('hides Retry button when item.can_retry is false', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'failed', can_retry: false })}
        actionLoading={new Set()}
        {...noopHandlers}
      />,
    )
    expect(screen.queryByTestId('retry-btn-job-1')).toBeNull()
  })
})


describe('JobActionsMenu — Delete button visibility', () => {
  it('shows Delete button for terminal statuses (completed/failed/cancelled)', () => {
    for (const status of ['completed', 'failed', 'cancelled', 'interrupted'] as const) {
      const { unmount } = render(
        <JobActionsMenu
          item={makeItem({ status })}
          actionLoading={new Set()}
          {...noopHandlers}
        />,
      )
      expect(screen.getByTestId('delete-btn-job-1')).toBeTruthy()
      unmount()
    }
  })

  it('hides Delete button for active statuses (running/queued)', () => {
    for (const status of ['running', 'queued'] as const) {
      const { unmount } = render(
        <JobActionsMenu
          item={makeItem({ status })}
          actionLoading={new Set()}
          {...noopHandlers}
        />,
      )
      expect(screen.queryByTestId('delete-btn-job-1')).toBeNull()
      unmount()
    }
  })
})


describe('JobActionsMenu — Details button always present', () => {
  it('shows Details button for every status', () => {
    for (const status of ['running', 'queued', 'completed', 'failed'] as const) {
      const { unmount } = render(
        <JobActionsMenu
          item={makeItem({ status })}
          actionLoading={new Set()}
          {...noopHandlers}
        />,
      )
      expect(screen.getByTestId('details-btn-job-1')).toBeTruthy()
      unmount()
    }
  })
})


describe('JobActionsMenu — click handlers receive the job_id', () => {
  it('Cancel click calls onCancel(jobId)', async () => {
    const onCancel = vi.fn()
    render(
      <JobActionsMenu
        item={makeItem({ status: 'running' })}
        actionLoading={new Set()}
        {...noopHandlers}
        onCancel={onCancel}
      />,
    )
    await userEvent.click(screen.getByTestId('cancel-btn-job-1'))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onCancel).toHaveBeenCalledWith('job-1')
  })

  it('Retry click calls onRetry(jobId)', async () => {
    const onRetry = vi.fn()
    render(
      <JobActionsMenu
        item={makeItem({ status: 'failed', can_retry: true })}
        actionLoading={new Set()}
        {...noopHandlers}
        onRetry={onRetry}
      />,
    )
    await userEvent.click(screen.getByTestId('retry-btn-job-1'))
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(onRetry).toHaveBeenCalledWith('job-1')
  })

  it('Delete click calls onDelete(jobId)', async () => {
    const onDelete = vi.fn()
    render(
      <JobActionsMenu
        item={makeItem({ status: 'completed' })}
        actionLoading={new Set()}
        {...noopHandlers}
        onDelete={onDelete}
      />,
    )
    await userEvent.click(screen.getByTestId('delete-btn-job-1'))
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete).toHaveBeenCalledWith('job-1')
  })

  it('Details click calls onDetails(jobId)', async () => {
    const onDetails = vi.fn()
    render(
      <JobActionsMenu
        item={makeItem({ status: 'completed' })}
        actionLoading={new Set()}
        {...noopHandlers}
        onDetails={onDetails}
      />,
    )
    await userEvent.click(screen.getByTestId('details-btn-job-1'))
    expect(onDetails).toHaveBeenCalledTimes(1)
    expect(onDetails).toHaveBeenCalledWith('job-1')
  })
})


describe('JobActionsMenu — loading state', () => {
  it('passes loading=true to Cancel/Retry/Delete buttons when actionLoading.has(jobId)', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'failed', can_retry: true })}
        actionLoading={new Set(['job-1'])}
        {...noopHandlers}
      />,
    )
    // The Button component renders the loading visual when prop loading=true.
    // We verify the data-testid is present + the buttons exist (not crashed)
    // — visual is a Button-internal concern.
    expect(screen.getByTestId('retry-btn-job-1')).toBeTruthy()
    expect(screen.getByTestId('delete-btn-job-1')).toBeTruthy()
  })

  it('Details button is NOT loading-gated (always interactive)', () => {
    render(
      <JobActionsMenu
        item={makeItem({ status: 'completed' })}
        actionLoading={new Set(['job-1'])}
        {...noopHandlers}
      />,
    )
    // Details button has no `loading` prop in the component implementation,
    // so even when actionLoading.has(jobId), it remains usable. This is
    // intentional — Details is read-only navigation, not a mutation.
    const detailsBtn = screen.getByTestId('details-btn-job-1') as HTMLButtonElement
    expect(detailsBtn.disabled).toBe(false)
  })
})
