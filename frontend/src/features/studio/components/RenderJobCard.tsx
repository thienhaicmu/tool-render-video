import { useState } from 'react'
import { StatusPill } from '../../../components/ui/StatusPill'
import { AIChip } from '../../../components/ui/AIChip'
import { RenderProgress } from './RenderProgress'
import { type RenderJobData } from '../types'
import { useI18n } from '../../../i18n/useI18n'
import { relativeTime } from './BottomRenderState'

function stateColor(state: RenderJobData['state']): string {
  if (state === 'completed') return 'var(--status-success)'
  if (state === 'failed') return 'var(--status-error)'
  if (state === 'rendering' || state === 'preparing' || state === 'reviewing') return 'var(--accent-primary)'
  return 'var(--text-tertiary)'
}

export function RenderJobCard({
  title,
  state,
  progress = 0,
  stage = '',
  eta,
  platform,
  createdAt,
  outputDir,
  canOpenFolder,
  completedCount,
  failedCount,
  totalCount,
  kind,
}: RenderJobData) {
  const { t } = useI18n()
  const [isHovered, setIsHovered] = useState(false)

  const openFolder = async () => {
    if (outputDir) await window.electronAPI?.openPath?.(outputDir)
  }

  const timeText = createdAt ? relativeTime(createdAt) : null
  const hasStats = typeof totalCount === 'number' && totalCount > 0
  const kindBadge = kind === 'download' ? '⬇' : '🎬'

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        backgroundColor: isHovered ? 'var(--surface-card-hover)' : 'var(--surface-card)',
        border: `1px solid ${isHovered ? 'var(--border-default)' : 'var(--border-subtle)'}`,
        borderLeft: `3px solid ${stateColor(state)}`,
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-3) var(--space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        transition: 'background-color var(--duration-instant) var(--ease-out)',
      }}
    >
      {/* Top row: kind badge + title + state */}
      <div style={styles.topRow}>
        <span style={styles.kindBadge}>{kindBadge}</span>
        <span style={styles.titleText}>{title}</span>
        {platform && (
          <span style={styles.platformBadge}>{platform}</span>
        )}
        <div style={{ flexShrink: 0, marginLeft: 'auto' }}>
          {state === 'queued' && (
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>In queue</span>
          )}
          {state === 'preparing' && <StatusPill status="running" />}
          {state === 'rendering' && eta && (
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{eta}</span>
          )}
          {state === 'reviewing' && <AIChip variant="applied" label="AI Reviewing…" />}
          {state === 'completed' && <StatusPill status="completed" />}
          {state === 'failed' && <StatusPill status="failed" />}
        </div>
      </div>

      {/* Secondary row: time + stats + open folder */}
      <div style={styles.metaRow}>
        {timeText && <span style={styles.timeText}>{timeText}</span>}
        {hasStats && (
          <span style={styles.statsText}>
            {completedCount}/{totalCount} {t('history_parts_done')}
            {(failedCount ?? 0) > 0 && (
              <span style={{ color: 'var(--status-error)', marginLeft: '4px' }}>
                · {failedCount} {t('history_parts_failed')}
              </span>
            )}
          </span>
        )}
        {canOpenFolder && outputDir && state === 'completed' && (
          <button onClick={openFolder} style={styles.openBtn}>
            📂 {t('history_open')}
          </button>
        )}
      </div>

      {/* Progress (rendering) */}
      {state === 'rendering' && (
        <RenderProgress progress={progress} stage={stage} animated />
      )}
      {state === 'preparing' && (
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Preparing…</span>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  topRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    minWidth: 0,
  },
  kindBadge: {
    fontSize: '12px',
    flexShrink: 0,
  },
  titleText: {
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--weight-medium)' as unknown as number,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    flex: 1,
    minWidth: 0,
  },
  platformBadge: {
    fontSize: '11px',
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-subtle)',
    padding: '1px 6px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap' as const,
  },
  timeText: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
  },
  statsText: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
  openBtn: {
    height: '20px',
    padding: '0 6px',
    border: '1px solid var(--border-subtle)',
    borderRadius: '4px',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    cursor: 'pointer',
    marginLeft: 'auto',
  },
}
