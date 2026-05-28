import type { StatusFilter } from './jobs.types'

export interface JobFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  statusFilter: StatusFilter
  onStatusFilterChange: (value: StatusFilter) => void
}

const STATUS_OPTIONS: { value: StatusFilter; label: string; color?: string }[] = [
  { value: 'all',       label: 'Tất cả'   },
  { value: 'running',   label: 'Chạy',    color: 'var(--accent)' },
  { value: 'completed', label: 'Xong',    color: 'var(--ok)'     },
  { value: 'failed',    label: 'Lỗi',     color: 'var(--fail)'   },
  { value: 'cancelled', label: 'Đã hủy',  color: 'var(--text-3)' },
]

export function JobFilters({ search, onSearchChange, statusFilter, onStatusFilterChange }: JobFiltersProps) {
  return (
    <div style={{
      padding: '7px 10px', borderBottom: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0,
      background: 'var(--bg-panel)',
    }}>
      {/* Search */}
      <div style={{ position: 'relative' }}>
        <span style={{
          position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)',
          fontSize: 11, color: 'var(--text-3)', pointerEvents: 'none', lineHeight: 1,
        }}>⌕</span>
        <input
          type="text"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
          placeholder="Tìm kiếm…"
          data-testid="history-search-input"
          style={{
            width: '100%', height: 28, paddingLeft: 24, paddingRight: 8,
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
      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        {STATUS_OPTIONS.map(opt => {
          const active = statusFilter === opt.value
          return (
            <button
              key={opt.value}
              data-testid={opt.value === 'all' ? 'history-status-filter' : undefined}
              onClick={() => onStatusFilterChange(opt.value)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 20, fontSize: 9,
                fontWeight: 700, fontFamily: 'var(--fh)', letterSpacing: '.4px',
                cursor: 'pointer', border: 'none', transition: 'all .12s',
                background: active ? (opt.color ? opt.color + '20' : 'var(--accent-dim)') : 'transparent',
                color: active ? (opt.color ?? 'var(--accent)') : 'var(--text-3)',
                boxShadow: active
                  ? `0 0 0 1px ${opt.color ?? 'var(--accent)'}44`
                  : '0 0 0 1px var(--border)',
              }}
            >
              {opt.color && active && (
                <span style={{ width: 4, height: 4, borderRadius: '50%', background: opt.color, flexShrink: 0 }} />
              )}
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
