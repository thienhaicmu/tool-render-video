/**
 * job-list-pagination.test.tsx — updated for the cumulative "Load more" UI.
 *
 * JobList's prev/next pager was replaced (B6) by a single cumulative
 * data-testid="load-more" button shown when hasMore is true. This file covers
 * that + the empty/loading/error states.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { JobList } from '../src/features/jobs/JobList'
import type { HistoryItem } from '../src/types/api'

function dummyItem(id: string): HistoryItem {
  return {
    job_id: id, title: `Job ${id}`, source_hint: 'test',
    status: 'completed', created_at: '2026-06-02T10:00:00Z', updated_at: '2026-06-02T10:05:00Z',
    progress_percent: 100, output_dir: '/tmp', output_count: 1,
    parts_total: 1, parts_done: 1, parts_failed: 0,
    can_retry: false, can_rerun: true, error_kind: null,
  } as HistoryItem
}

const baseProps = {
  items: [dummyItem('a'), dummyItem('b')],
  loading: false,
  error: null as string | null,
  hasFilters: false,
  selectedJobId: null,
  actionLoading: new Set<string>(),
  hasMore: false,
  onSelect: () => {},
  onCancel: () => {},
  onRetry: () => {},
  onRerun: () => {},
  onDelete: () => {},
  onRetryFetch: () => {},
  onLoadMore: () => {},
}

describe('JobList — Load more button', () => {
  it('shows the load-more button when hasMore is true', () => {
    render(<JobList {...baseProps} hasMore />)
    expect(screen.getByTestId('load-more')).toBeTruthy()
  })

  it('hides the load-more button when hasMore is false', () => {
    render(<JobList {...baseProps} hasMore={false} />)
    expect(screen.queryByTestId('load-more')).toBeNull()
  })

  it('clicking load-more calls onLoadMore', async () => {
    const onLoadMore = vi.fn()
    render(<JobList {...baseProps} hasMore onLoadMore={onLoadMore} />)
    await userEvent.click(screen.getByTestId('load-more'))
    expect(onLoadMore).toHaveBeenCalledTimes(1)
  })
})

describe('JobList — empty + loading + error states', () => {
  it('shows loading state when loading=true (no load-more)', () => {
    const { container } = render(<JobList {...baseProps} items={[]} loading hasMore />)
    expect(container.querySelector('[data-testid="load-more"]')).toBeNull()
  })

  it('shows error state when error is set', () => {
    render(<JobList {...baseProps} items={[]} error="API down" />)
    expect(screen.getByText(/API down/)).toBeTruthy()
  })

  it('shows empty state when no items and no filters (no load-more)', () => {
    const { container } = render(<JobList {...baseProps} items={[]} />)
    expect(container.querySelector('[data-testid="load-more"]')).toBeNull()
  })

  it('shows the "no results" message when items empty + hasFilters=true', () => {
    render(<JobList {...baseProps} items={[]} hasFilters />)
    expect(screen.getByText('No results found.')).toBeTruthy()
  })
})
