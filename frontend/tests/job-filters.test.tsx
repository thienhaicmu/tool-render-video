/**
 * job-filters.test.tsx — Sprint 8 frontend test rewrite.
 *
 * Replaces "status filter dropdown" coverage from deleted
 * history-screen.test.tsx. The old test expected a <select> dropdown
 * (`getByRole('combobox')`) but the current implementation uses pill
 * buttons. Tests verify the current pill-button shape.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { JobFilters } from '../src/features/jobs/JobFilters'


describe('JobFilters — search input', () => {
  it('renders the search input with its data-testid', () => {
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={() => {}}
      />,
    )
    expect(screen.getByTestId('history-search-input')).toBeTruthy()
  })

  it('shows the current search value in the input', () => {
    render(
      <JobFilters
        search="my query"
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={() => {}}
      />,
    )
    const input = screen.getByTestId('history-search-input') as HTMLInputElement
    expect(input.value).toBe('my query')
  })

  it('calls onSearchChange with the typed value', async () => {
    const onSearchChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={onSearchChange}
        statusFilter="all"
        onStatusFilterChange={() => {}}
      />,
    )
    const input = screen.getByTestId('history-search-input')
    await userEvent.type(input, 'a')
    expect(onSearchChange).toHaveBeenCalledWith('a')
  })
})


describe('JobFilters — status pill buttons', () => {
  it('renders all 5 status pills (Tất cả/Chạy/Xong/Lỗi/Đã hủy)', () => {
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={() => {}}
      />,
    )
    expect(screen.getByText('Tất cả')).toBeTruthy()
    expect(screen.getByText('Chạy')).toBeTruthy()
    expect(screen.getByText('Xong')).toBeTruthy()
    expect(screen.getByText('Lỗi')).toBeTruthy()
    expect(screen.getByText('Đã hủy')).toBeTruthy()
  })

  it('clicking "Chạy" pill calls onStatusFilterChange("running")', async () => {
    const onStatusFilterChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={onStatusFilterChange}
      />,
    )
    await userEvent.click(screen.getByText('Chạy'))
    expect(onStatusFilterChange).toHaveBeenCalledWith('running')
  })

  it('clicking "Xong" pill calls onStatusFilterChange("completed")', async () => {
    const onStatusFilterChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={onStatusFilterChange}
      />,
    )
    await userEvent.click(screen.getByText('Xong'))
    expect(onStatusFilterChange).toHaveBeenCalledWith('completed')
  })

  it('clicking "Lỗi" pill calls onStatusFilterChange("failed")', async () => {
    const onStatusFilterChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={onStatusFilterChange}
      />,
    )
    await userEvent.click(screen.getByText('Lỗi'))
    expect(onStatusFilterChange).toHaveBeenCalledWith('failed')
  })

  it('clicking "Đã hủy" pill calls onStatusFilterChange("cancelled")', async () => {
    const onStatusFilterChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="all"
        onStatusFilterChange={onStatusFilterChange}
      />,
    )
    await userEvent.click(screen.getByText('Đã hủy'))
    expect(onStatusFilterChange).toHaveBeenCalledWith('cancelled')
  })

  it('clicking "Tất cả" pill calls onStatusFilterChange("all")', async () => {
    const onStatusFilterChange = vi.fn()
    render(
      <JobFilters
        search=""
        onSearchChange={() => {}}
        statusFilter="running"
        onStatusFilterChange={onStatusFilterChange}
      />,
    )
    await userEvent.click(screen.getByText('Tất cả'))
    expect(onStatusFilterChange).toHaveBeenCalledWith('all')
  })
})
