import { JobActionsMenu } from './JobActionsMenu'
import { formatRelativeTime, isActiveStatus } from './jobs.utils'
import type { HistoryItem } from '@/types/api'

const STATUS_CFG: Record<string, { color: string; label: string }> = {
  completed:             { color: 'var(--ok)',     label: 'Xong'       },
  partial:               { color: 'var(--warn)',   label: 'Một phần'   },
  completed_with_errors: { color: 'var(--warn)',   label: 'Một phần'   },
  running:               { color: 'var(--accent)', label: 'Đang render' },
  queued:                { color: 'var(--text-3)', label: 'Xếp hàng'   },
  failed:                { color: 'var(--fail)',   label: 'Lỗi'        },
  interrupted:           { color: 'var(--warn)',   label: 'Gián đoạn'  },
  cancelled:             { color: 'var(--text-3)', label: 'Đã hủy'     },
  canceled:              { color: 'var(--text-3)', label: 'Đã hủy'     },
  cancelling:            { color: 'var(--warn)',   label: 'Đang hủy'   },
}
const FALLBACK = { color: 'var(--text-3)', label: '—' }

export interface JobListItemProps {
  item: HistoryItem
  isSelected: boolean
  actionLoading: Set<string>
  onSelect: (jobId: string) => void
  onCancel: (jobId: string) => void
  onRetry: (jobId: string) => void
  onRerun: (jobId: string) => void
  onDelete: (jobId: string) => void
  onDuplicate?: (jobId: string) => void
  /** S3.3 — batch mode: when isBatchSelected !== undefined, the row
   *  renders a checkbox and clicks toggle batch selection instead of
   *  opening the detail drawer. Pass undefined to disable batch UI. */
  isBatchSelected?: boolean
  onToggleBatch?: (jobId: string, withShift: boolean) => void
}

export function JobListItem({
  item, isSelected, actionLoading,
  onSelect, onCancel, onRetry, onRerun, onDelete, onDuplicate,
  isBatchSelected, onToggleBatch,
}: JobListItemProps) {
  const inBatchMode = isBatchSelected !== undefined
  const isActive = isActiveStatus(item.status)
  const st = STATUS_CFG[item.status] ?? FALLBACK
  const progressPct = item.total_count > 0
    ? Math.round((item.completed_count / item.total_count) * 100)
    : 0

  return (
    <div
      data-testid={`job-list-item-${item.job_id}`}
      onClick={(e) => {
        if (inBatchMode && onToggleBatch) {
          onToggleBatch(item.job_id, e.shiftKey)
          return
        }
        onSelect(item.job_id)
      }}
      style={{
        display: 'flex', cursor: 'pointer', transition: 'background .1s',
        background: isBatchSelected
          ? 'var(--accent-dim, rgba(123,97,255,.12))'
          : isSelected ? 'var(--bg-hover)' : 'transparent',
        borderBottom: '1px solid var(--border)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Left accent bar */}
      <div style={{
        width: 3, flexShrink: 0,
        background: st.color,
        opacity: isSelected || isBatchSelected ? 1 : 0.45,
        transition: 'opacity .12s',
      }} />

      {/* S3.3 batch checkbox — only when batch mode is wired */}
      {inBatchMode && (
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 28, flexShrink: 0,
            borderRight: '1px solid var(--border)',
          }}
          onClick={(e) => {
            e.stopPropagation()
            if (onToggleBatch) onToggleBatch(item.job_id, e.shiftKey)
          }}
        >
          <input
            type="checkbox"
            checked={!!isBatchSelected}
            readOnly
            style={{ cursor: 'pointer' }}
            data-testid={`batch-cb-${item.job_id}`}
          />
        </div>
      )}

      <div style={{ flex: 1, minWidth: 0, padding: '9px 10px' }}>
        {/* Row 1: title + time */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 3 }}>
          {isActive && (
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginTop: 4,
              background: st.color, boxShadow: `0 0 5px ${st.color}`,
              animation: 'job-pulse 1.4s ease-in-out infinite',
            }} />
          )}
          <span style={{
            flex: 1, fontSize: 11, fontWeight: 600, color: 'var(--text-1)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            lineHeight: 1.35,
          }}>
            {item.title || item.job_id.slice(0, 12)}
          </span>
          <span style={{ fontSize: 9, color: 'var(--text-3)', flexShrink: 0, marginTop: 1 }}>
            {formatRelativeTime(item.created_at)}
          </span>
        </div>

        {/* Row 2: status + clips + failed */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: isActive ? 5 : 0 }}>
          <span style={{
            fontSize: 8, fontWeight: 700, color: st.color,
            fontFamily: 'var(--fh)', letterSpacing: '.04em',
          }}>
            {st.label}
          </span>
          {item.total_count > 0 && (
            <span style={{
              fontSize: 8, padding: '1px 5px', borderRadius: 4,
              background: 'var(--bg-card)', color: 'var(--text-2)',
              border: '1px solid var(--border)', fontWeight: 600,
            }}>
              {isActive ? `${item.completed_count}/${item.total_count}` : `${item.completed_count}`} clip
            </span>
          )}
          {item.failed_count > 0 && (
            <span style={{
              fontSize: 8, padding: '1px 5px', borderRadius: 4,
              background: 'rgba(232,64,122,.1)', color: 'var(--fail)',
              border: '1px solid rgba(232,64,122,.2)', fontWeight: 600,
            }}>
              {item.failed_count} lỗi
            </span>
          )}
        </div>

        {/* Progress bar (active only) */}
        {isActive && (
          <div style={{ height: 2, borderRadius: 99, background: 'var(--bg-card)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 99,
              width: `${progressPct}%`,
              background: `linear-gradient(90deg, ${st.color}, ${st.color}88)`,
              transition: 'width .4s ease',
              boxShadow: `0 0 4px ${st.color}66`,
            }} />
          </div>
        )}

        {/* Actions (selected only) */}
        {isSelected && (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 5 }} onClick={e => e.stopPropagation()}>
            <JobActionsMenu
              item={item}
              actionLoading={actionLoading}
              onCancel={onCancel}
              onRetry={onRetry}
              onRerun={onRerun}
              onDelete={onDelete}
              onDuplicate={onDuplicate}
              onDetails={onSelect}
            />
            {item.can_open_folder && item.output_dir && (
              <button
                onClick={() => window.electronAPI?.openPath?.(item.output_dir!)}
                style={{
                  fontSize: 10, padding: '2px 7px', borderRadius: 5,
                  border: '1px solid var(--border)', background: 'var(--bg-hover)',
                  color: 'var(--text-3)', cursor: 'pointer',
                }}
              >📂</button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
