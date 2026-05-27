import type { StatusFilter } from './jobs.types'

export interface JobFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  statusFilter: StatusFilter
  onStatusFilterChange: (value: StatusFilter) => void
}

const STATUS_OPTIONS: { value: StatusFilter; label: string; color?: string }[] = [
  { value: 'all',       label: 'Tất cả' },
  { value: 'running',   label: 'Đang chạy', color: 'var(--accent)' },
  { value: 'completed', label: 'Xong',       color: 'var(--ok)'     },
  { value: 'failed',    label: 'Lỗi',        color: 'var(--fail)'   },
  { value: 'cancelled', label: 'Đã hủy',     color: 'var(--text-3)' },
]

export function JobFilters({ search, onSearchChange, statusFilter, onStatusFilterChange }: JobFiltersProps) {
  return (
    <div style={{
      padding: '10px 14px',
      borderBottom: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', gap: 7, flexShrink: 0,
      background: 'var(--bg-panel)',
    }}>
      {/* Search */}
      <div style={{ position: 'relative' }}>
        <span style={{
          position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)',
          fontSize: 12, color: 'var(--text-3)', pointerEvents: 'none',
        }}>⌕</span>
        <input
          type="text"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
          placeholder="Tìm kiếm theo tên hoặc nguồn..."
          data-testid="history-search-input"
          style={{
            width: '100%', height: 30, paddingLeft: 26, paddingRight: 10,
            background: 'var(--bg-card)', color: 'var(--text-1)',
            border: '1px solid var(--border)', borderRadius: 6, fontSize: 11,
            fontFamily: 'var(--fb)', outline: 'none', boxSizing: 'border-box',
            transition: 'border-color .12s',
          }}
          onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
          onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
        />
      </div>

      {/* Filter pills */}
      <div style={{ display: 'flex', gap: 4 }}>
        {STATUS_OPTIONS.map(opt => {
          const active = statusFilter === opt.value
          return (
            <button
              key={opt.value}
              data-testid={opt.value === 'all' ? 'history-status-filter' : undefined}
              onClick={() => onStatusFilterChange(opt.value)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 9px', borderRadius: 20, fontSize: 10,
                fontWeight: 700, fontFamily: 'var(--fh)', letterSpacing: '.4px',
                cursor: 'pointer', border: 'none', transition: 'all .12s',
                background: active ? (opt.color ? opt.color + '22' : 'var(--accent-dim)') : 'var(--bg-card)',
                color: active ? (opt.color ?? 'var(--accent)') : 'var(--text-3)',
                boxShadow: active
                  ? `0 0 0 1px ${opt.color ?? 'var(--accent)'}55`
                  : '0 0 0 1px var(--border)',
              }}
            >
              {opt.color && (
                <span style={{
                  width: 5, height: 5, borderRadius: '50%',
                  background: opt.color, flexShrink: 0,
                }} />
              )}
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
