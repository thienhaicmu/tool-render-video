/**
 * JobFilters — search input + status filter dropdown.
 */
import type { StatusFilter } from './jobs.types'

export interface JobFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  statusFilter: StatusFilter
  onStatusFilterChange: (value: StatusFilter) => void
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all',       label: 'All'       },
  { value: 'running',   label: 'Rendering' },
  { value: 'completed', label: 'Complete'  },
  { value: 'failed',    label: 'Failed'    },
  { value: 'cancelled', label: 'Canceled'  },
]

export function JobFilters({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
}: JobFiltersProps) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 'var(--space-3)',
        padding: 'var(--space-4)',
        borderBottom: '1px solid var(--color-border)',
        alignItems: 'center',
      }}
    >
      <input
        type="text"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search by title, source, or job ID"
        data-testid="history-search-input"
        style={{
          flex: 1,
          padding: '6px 12px',
          backgroundColor: 'var(--color-bg-elevated)',
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-md)',
          fontSize: 'var(--font-size-sm)',
          fontFamily: 'var(--font-family-base)',
          outline: 'none',
        }}
      />
      <select
        value={statusFilter}
        onChange={(e) => onStatusFilterChange(e.target.value as StatusFilter)}
        data-testid="history-status-filter"
        style={{
          padding: '6px 10px',
          backgroundColor: 'var(--color-bg-elevated)',
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-md)',
          fontSize: 'var(--font-size-sm)',
          fontFamily: 'var(--font-family-base)',
          cursor: 'pointer',
          outline: 'none',
        }}
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}
