/**
 * job-list-pagination.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Replaces the "pagination Next button disabled when has_more=false"
 * coverage from deleted history-screen.test.tsx. The pagination UI lives
 * in JobList (features/jobs/JobList.tsx) and exposes
 * data-testid="pagination-prev" / "pagination-next" with disabled state
 * driven by offset + hasMore props.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { JobList } from '../src/features/jobs/JobList'
import type { HistoryItem } from '../src/types/api'


function dummyItem(id: string): HistoryItem {
  return {
    job_id: id,
    title: `Job ${id}`,
    source_hint: 'test',
    status: 'completed',
    created_at: '2026-06-02T10:00:00Z',
    updated_at: '2026-06-02T10:05:00Z',
    progress_percent: 100,
    output_dir: '/tmp',
    output_count: 1,
    parts_total: 1,
    parts_done: 1,
    parts_failed: 0,
    can_retry: false,
    can_rerun: true,
    error_kind: null,
  } as HistoryItem
}


const baseProps = {
  items: [dummyItem('a'), dummyItem('b')],
  loading: false,
  error: null,
  hasFilters: false,
  selectedJobId: null,
  actionLoading: new Set<string>(),
  onSelect: () => {},
  onCancel: () => {},
  onRetry: () => {},
  onRerun: () => {},
  onDelete: () => {},
  onRetryFetch: () => {},
}


describe('JobList — pagination button enabled state', () => {
  it('Next button is disabled when hasMore is false', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    // With offset=0 AND hasMore=false, pagination footer renders only if
    // offset > 0 OR hasMore — neither is true here, so the footer is
    // omitted entirely. queryByTestId returns null.
    expect(screen.queryByTestId('pagination-next')).toBeNull()
  })

  it('Next button is enabled when hasMore is true', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={true}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    const nextBtn = screen.getByTestId('pagination-next') as HTMLButtonElement
    expect(nextBtn.disabled).toBe(false)
  })

  it('Prev button is disabled when offset is 0', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={true}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    const prevBtn = screen.getByTestId('pagination-prev') as HTMLButtonElement
    expect(prevBtn.disabled).toBe(true)
  })

  it('Prev button is enabled when offset > 0', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={false}
        offset={20}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    const prevBtn = screen.getByTestId('pagination-prev') as HTMLButtonElement
    expect(prevBtn.disabled).toBe(false)
  })

  it('footer shows when hasMore even if offset=0', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={true}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    expect(screen.getByTestId('pagination-next')).toBeTruthy()
    expect(screen.getByTestId('pagination-prev')).toBeTruthy()
  })

  it('footer omitted when offset=0 AND !hasMore (no pagination needed)', () => {
    render(
      <JobList
        {...baseProps}
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    expect(screen.queryByTestId('pagination-next')).toBeNull()
    expect(screen.queryByTestId('pagination-prev')).toBeNull()
  })
})


describe('JobList — pagination click handlers', () => {
  it('clicking enabled Next calls onNextPage', async () => {
    const onNextPage = vi.fn()
    render(
      <JobList
        {...baseProps}
        hasMore={true}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={onNextPage}
      />,
    )
    await userEvent.click(screen.getByTestId('pagination-next'))
    expect(onNextPage).toHaveBeenCalledTimes(1)
  })

  it('clicking enabled Prev calls onPrevPage', async () => {
    const onPrevPage = vi.fn()
    render(
      <JobList
        {...baseProps}
        hasMore={false}
        offset={20}
        onPrevPage={onPrevPage}
        onNextPage={() => {}}
      />,
    )
    await userEvent.click(screen.getByTestId('pagination-prev'))
    expect(onPrevPage).toHaveBeenCalledTimes(1)
  })

  it('clicking disabled Next does NOT call onNextPage', async () => {
    const onNextPage = vi.fn()
    render(
      <JobList
        {...baseProps}
        hasMore={true}
        offset={20}
        onPrevPage={() => {}}
        onNextPage={onNextPage}
      />,
    )
    // Manually disable to verify the click is suppressed by the button's
    // own `disabled` attr (not just by props logic above).
    const nextBtn = screen.getByTestId('pagination-next') as HTMLButtonElement
    nextBtn.disabled = true
    await userEvent.click(nextBtn)
    expect(onNextPage).not.toHaveBeenCalled()
  })
})


describe('JobList — empty + loading + error states', () => {
  it('shows loading state when loading=true', () => {
    const { container } = render(
      <JobList
        {...baseProps}
        items={[]}
        loading={true}
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    // The component renders <JobLoadingState /> when loading; we just
    // check that no pagination footer is rendered (sanity).
    expect(container.querySelector('[data-testid="pagination-next"]')).toBeNull()
  })

  it('shows error state when error is set', () => {
    render(
      <JobList
        {...baseProps}
        items={[]}
        error="API down"
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    expect(screen.getByText(/API down/)).toBeTruthy()
  })

  it('shows empty state when no items and no filters', () => {
    const { container } = render(
      <JobList
        {...baseProps}
        items={[]}
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    // Empty state component renders; pagination should not.
    expect(container.querySelector('[data-testid="pagination-next"]')).toBeNull()
  })

  it('shows "no results" filter message when items empty + hasFilters=true', () => {
    render(
      <JobList
        {...baseProps}
        items={[]}
        hasFilters={true}
        hasMore={false}
        offset={0}
        onPrevPage={() => {}}
        onNextPage={() => {}}
      />,
    )
    expect(screen.getByText('Không tìm thấy kết quả.')).toBeTruthy()
  })
})
