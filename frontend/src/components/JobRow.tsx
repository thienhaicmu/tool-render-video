/**
 * JobRow — shared job row chrome (WP2).
 *
 * One consistent row used by the Queue screen (and, progressively, the dock /
 * library / downloads). Renders the kind badge, title (optionally an "open"
 * button), a subtitle, a progress bar, and an `actions` slot so each surface
 * supplies its own controls without forking the row's look.
 */
import React from 'react'

export interface JobRowProps {
  kind: 'render' | 'download'
  title: string
  subtitle?: string
  /** 'warn' tints the subtitle (e.g. a paused job). */
  subtitleTone?: 'default' | 'warn'
  progressPct?: number
  /** When set, the title becomes a button that opens the job. */
  onOpen?: () => void
  openTitle?: string
  /** Right-aligned control cluster. */
  actions?: React.ReactNode
}

export function JobRow({
  kind, title, subtitle, subtitleTone = 'default', progressPct, onOpen, openTitle, actions,
}: JobRowProps) {
  const pct = progressPct == null ? null : Math.max(0, Math.min(100, progressPct))
  const kindLabel = kind === 'render' ? 'RENDER' : 'DOWNLOAD'
  const kindBg = kind === 'render' ? 'var(--accent-subtle)' : 'rgba(34,197,94,.12)'
  const kindFg = kind === 'render' ? 'var(--accent-primary)' : 'rgb(34,197,94)'

  return (
    <div style={styles.row}>
      <div style={styles.top}>
        <span style={{ ...styles.kindBadge, background: kindBg, color: kindFg }}>{kindLabel}</span>
        {onOpen ? (
          <button style={{ ...styles.title, ...styles.titleBtn }} title={openTitle} onClick={onOpen}>
            {title}
          </button>
        ) : (
          <span style={styles.title}>{title}</span>
        )}
        {subtitle != null && (
          <span style={{ ...styles.sub, ...(subtitleTone === 'warn' ? { color: 'var(--status-warning)', fontWeight: 700 } : null) }}>
            {subtitle}
          </span>
        )}
      </div>

      {pct != null && (
        <div style={styles.progressWrap}>
          <span style={{ ...styles.progressBar, width: `${pct}%` }} />
        </div>
      )}

      {actions && <div style={styles.actions}>{actions}</div>}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  row: {
    border: '1px solid var(--border-subtle)', borderRadius: 10, padding: '9px 11px',
    background: 'var(--surface-card)', display: 'flex', flexDirection: 'column', gap: 7,
  },
  top: { display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 },
  kindBadge: {
    fontSize: 9, fontWeight: 700, letterSpacing: '.06em', padding: '2px 6px',
    borderRadius: 4, whiteSpace: 'nowrap', flexShrink: 0,
  },
  title: {
    fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  titleBtn: {
    border: 'none', background: 'transparent', textAlign: 'left', cursor: 'pointer', padding: 0, minWidth: 0,
  },
  sub: {
    fontSize: 10, color: 'var(--text-tertiary)', fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap', flexShrink: 0,
  },
  progressWrap: { position: 'relative', height: 4, background: 'var(--border-subtle)', borderRadius: 2, overflow: 'hidden' },
  progressBar: { position: 'absolute', inset: 0, background: 'var(--accent-primary)', transition: 'width 0.3s ease' },
  actions: { display: 'flex', alignItems: 'center', gap: 4 },
}
