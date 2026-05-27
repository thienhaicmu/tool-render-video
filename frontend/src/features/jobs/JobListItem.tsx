import { JobActionsMenu } from './JobActionsMenu'
import { formatRelativeTime, isActiveStatus } from './jobs.utils'
import type { HistoryItem } from '../../types/api'

const STATUS_CFG: Record<string, { color: string; bg: string; label: string }> = {
  completed:            { color: 'var(--ok)',   bg: 'rgba(0,200,150,.12)',  label: 'Xong'       },
  partial:              { color: 'var(--warn)',  bg: 'rgba(240,160,32,.12)', label: 'Một phần'   },
  completed_with_errors:{ color: 'var(--warn)',  bg: 'rgba(240,160,32,.12)', label: 'Một phần'   },
  running:              { color: 'var(--accent)',bg: 'var(--accent-dim)',    label: 'Đang render' },
  queued:               { color: 'var(--text-3)',bg: 'rgba(74,82,112,.12)', label: 'Xếp hàng'   },
  failed:               { color: 'var(--fail)',  bg: 'rgba(232,64,122,.12)', label: 'Lỗi'        },
  interrupted:          { color: 'var(--warn)',  bg: 'rgba(240,160,32,.12)', label: 'Gián đoạn'  },
  cancelled:            { color: 'var(--text-3)',bg: 'rgba(74,82,112,.10)', label: 'Đã hủy'     },
  canceled:             { color: 'var(--text-3)',bg: 'rgba(74,82,112,.10)', label: 'Đã hủy'     },
  cancelling:           { color: 'var(--warn)',  bg: 'rgba(240,160,32,.12)', label: 'Đang hủy'   },
}
const FALLBACK = { color: 'var(--text-3)', bg: 'rgba(74,82,112,.10)', label: '—' }

const KIND_ICON: Record<string, string> = { render: '▶', download: '↓' }

export interface JobListItemProps {
  item: HistoryItem
  isSelected: boolean
  actionLoading: Set<string>
  onSelect: (jobId: string) => void
  onCancel: (jobId: string) => void
  onRetry: (jobId: string) => void
  onRerun: (jobId: string) => void
  onDelete: (jobId: string) => void
}

export function JobListItem({
  item, isSelected, actionLoading,
  onSelect, onCancel, onRetry, onRerun, onDelete,
}: JobListItemProps) {
  const isActive    = isActiveStatus(item.status)
  const st          = STATUS_CFG[item.status] ?? FALLBACK
  const progressPct = item.total_count > 0
    ? Math.round((item.completed_count / item.total_count) * 100)
    : 0

  return (
    <div
      data-testid={`job-list-item-${item.job_id}`}
      onClick={() => onSelect(item.job_id)}
      style={{
        background: isSelected ? 'var(--bg-hover)' : 'var(--bg-card)',
        border: `1px solid ${isSelected ? 'var(--border-hi)' : 'var(--border)'}`,
        borderRadius: 8,
        cursor: 'pointer',
        transition: 'all .12s',
        overflow: 'hidden',
      }}
    >
      {/* Status accent bar top */}
      <div style={{ height: 2, background: `linear-gradient(90deg, ${st.color}, transparent)` }} />

      <div style={{ padding: '10px 12px' }}>
        {/* Row 1: kind icon + title + status badge + time */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
          <span style={{
            width: 22, height: 22, borderRadius: 5, flexShrink: 0,
            background: 'var(--bg-hover)', border: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, color: 'var(--text-2)',
          }}>
            {KIND_ICON[item.kind] ?? '▶'}
          </span>

          <span style={{
            flex: 1, fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            lineHeight: 1.4,
          }}>
            {item.title || item.job_id}
          </span>

          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 20, flexShrink: 0,
            background: st.bg, color: st.color,
            display: 'inline-flex', alignItems: 'center', gap: 3, fontFamily: 'var(--fh)',
            letterSpacing: '.4px',
          }}>
            {isActive && (
              <span style={{
                width: 5, height: 5, borderRadius: '50%', background: st.color,
                animation: 'job-pulse 1.4s ease-in-out infinite',
              }} />
            )}
            {st.label}
          </span>
        </div>

        {/* Row 2: source hint */}
        {item.source_hint && (
          <div style={{
            fontSize: 10, color: 'var(--text-3)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            marginBottom: 6, paddingLeft: 30, fontFamily: 'var(--fb)',
          }}>
            {item.source_hint}
          </div>
        )}

        {/* Progress bar for active */}
        {isActive && (
          <div style={{ marginBottom: 6, paddingLeft: 30 }}>
            <div style={{ height: 3, borderRadius: 99, background: 'var(--bg-hover)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 99, width: `${progressPct}%`,
                background: `linear-gradient(90deg, ${st.color}, ${st.color}88)`,
                transition: 'width .4s ease',
                boxShadow: `0 0 6px ${st.color}55`,
              }} />
            </div>
          </div>
        )}

        {/* Row 3: meta chips */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, paddingLeft: 30, flexWrap: 'wrap' }}>
          {item.total_count > 0 && (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              background: 'var(--bg-hover)', color: 'var(--text-2)',
              border: '1px solid var(--border)',
            }}>
              {isActive ? `${item.completed_count}/${item.total_count}` : `${item.completed_count}`} clip
            </span>
          )}
          {item.failed_count > 0 && (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              background: 'rgba(232,64,122,.1)', color: 'var(--fail)',
              border: '1px solid rgba(232,64,122,.2)',
            }}>
              {item.failed_count} lỗi
            </span>
          )}
          {item.summary_text && (
            <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{item.summary_text}</span>
          )}
          <span style={{ fontSize: 9, color: 'var(--text-3)', marginLeft: 'auto' }}>
            {formatRelativeTime(item.created_at)}
          </span>
        </div>

        {/* Row 4: actions */}
        <div style={{ marginTop: 8, paddingLeft: 30 }} onClick={e => e.stopPropagation()}>
          <JobActionsMenu
            item={item}
            actionLoading={actionLoading}
            onCancel={onCancel}
            onRetry={onRetry}
            onRerun={onRerun}
            onDelete={onDelete}
            onDetails={onSelect}
          />
        </div>
      </div>
    </div>
  )
}
