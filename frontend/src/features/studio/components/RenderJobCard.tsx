import { StatusPill } from '../../../components/ui/StatusPill'
import { AIChip } from '../../../components/ui/AIChip'
import { RenderProgress } from './RenderProgress'
import { type RenderJobData } from '../types'

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span
      style={{
        fontSize: 'var(--text-xs)',
        color: 'var(--accent-primary)',
        backgroundColor: 'var(--accent-subtle)',
        padding: '2px 6px',
        borderRadius: 'var(--radius-sm)',
        flexShrink: 0,
      }}
    >
      {platform}
    </span>
  )
}

export function RenderJobCard({
  title,
  state,
  progress = 0,
  stage = '',
  eta,
  platform,
}: RenderJobData) {
  return (
    <div
      style={{
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-3) var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      {/* Top row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
        {/* Left: title + platform */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
          <span
            style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--weight-medium)' as unknown as number,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {title}
          </span>
          {platform && <PlatformBadge platform={platform} />}
        </div>

        {/* Right: state indicator */}
        {state === 'queued' && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', flexShrink: 0 }}>
            In queue
          </span>
        )}
        {state === 'preparing' && (
          <StatusPill status="running" />
        )}
        {state === 'rendering' && eta && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', flexShrink: 0 }}>
            {eta}
          </span>
        )}
        {state === 'reviewing' && (
          <AIChip variant="applied" label="AI Reviewing…" />
        )}
        {state === 'completed' && (
          <StatusPill status="completed" />
        )}
        {state === 'failed' && (
          <StatusPill status="failed" />
        )}
      </div>

      {/* Secondary text for preparing state */}
      {state === 'preparing' && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          Preparing…
        </span>
      )}

      {/* Progress bar for rendering state */}
      {state === 'rendering' && (
        <RenderProgress progress={progress} stage={stage} animated />
      )}
    </div>
  )
}
