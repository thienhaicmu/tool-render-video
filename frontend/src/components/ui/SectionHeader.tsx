/**
 * SectionHeader — Collapsible section label with chevron and optional badge.
 * Source: docs/design/components.md component #9
 */
export interface SectionHeaderProps {
  title: string
  expanded: boolean
  onToggle: () => void
  badge?: number
}

export function SectionHeader({ title, expanded, onToggle, badge }: SectionHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: '32px',
        padding: '0 var(--space-4)',
        cursor: 'pointer',
        borderTop: '1px solid var(--border-subtle)',
        userSelect: 'none',
      }}
      onClick={onToggle}
      role="button"
      aria-expanded={expanded}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flex: 1, minWidth: 0 }}>
        {/* Chevron */}
        <span
          style={{
            fontSize: '14px',
            color: 'var(--text-secondary)',
            display: 'inline-block',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: `transform var(--duration-fast) var(--ease-in-out)`,
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          ›
        </span>

        {/* Title */}
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-secondary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </span>
      </div>

      {/* Badge */}
      {badge !== undefined && (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: '18px',
            height: '18px',
            padding: '0 4px',
            borderRadius: 'var(--radius-full)',
            backgroundColor: 'var(--accent-subtle)',
            color: 'var(--accent-primary)',
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
            flexShrink: 0,
          }}
        >
          {badge}
        </span>
      )}
    </div>
  )
}
