import { EmptyState } from '../../../components/ui/EmptyState'

export interface PreviewWorkspaceProps {
  hasMedia?: boolean
}

const TRACKS: Array<{ label: string; color: string }> = [
  { label: 'VIDEO',   color: 'var(--accent-subtle)' },
  { label: 'SUBS',    color: 'var(--accent-subtle)' },
  { label: 'AI MKR',  color: 'var(--ai-subtle)' },
]

export function PreviewWorkspace({ hasMedia = false }: PreviewWorkspaceProps) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        minWidth: 0,
      }}
    >
      {/* Video player container */}
      <div
        style={{
          aspectRatio: '16 / 9',
          backgroundColor: 'var(--surface-base)',
          border: '1px solid var(--border-subtle)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          maxHeight: '45%',
        }}
      >
        {!hasMedia && (
          <EmptyState
            variant="no-jobs"
            primary="No media loaded"
            secondary="Select a source to begin"
          />
        )}
      </div>

      {/* Transport controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-2) var(--space-4)',
          flexShrink: 0,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ fontSize: '16px', color: 'var(--text-tertiary)', cursor: 'default' }}>▶</span>
        <span style={{ fontSize: '16px', color: 'var(--text-tertiary)', cursor: 'default' }}>🔊</span>
        <span style={{ fontSize: '16px', color: 'var(--text-tertiary)', cursor: 'default' }}>⟲</span>
        <span style={{ flex: 1 }} />
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          00:00:00
        </span>
      </div>

      {/* 3-track timeline shell */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Track header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            height: '28px',
            borderBottom: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <div style={{ width: 'var(--timeline-label-w)', flexShrink: 0 }} />
          <span
            style={{
              flex: 1,
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              padding: '0 var(--space-2)',
            }}
          >
            Timeline
          </span>
        </div>

        {/* Track rows */}
        {TRACKS.map((track) => (
          <div
            key={track.label}
            style={{
              display: 'flex',
              alignItems: 'center',
              height: 'var(--timeline-track-h)',
              borderBottom: '1px solid var(--border-subtle)',
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: 'var(--timeline-label-w)',
                flexShrink: 0,
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
                padding: '0 var(--space-2)',
                userSelect: 'none',
              }}
            >
              {track.label}
            </div>
            <div
              style={{
                flex: 1,
                height: '100%',
                backgroundColor: track.color,
              }}
            />
          </div>
        ))}
      </div>

      {/* Action row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-6)',
          borderTop: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}
      >
        <button
          disabled
          style={{
            background: 'none',
            border: 'none',
            cursor: 'default',
            color: 'var(--text-tertiary)',
            fontSize: 'var(--text-sm)',
            padding: 'var(--space-2) var(--space-3)',
          }}
        >
          ← Back to Source
        </button>
        <button
          disabled
          style={{
            background: 'var(--accent-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            color: '#FFFFFF',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
            padding: 'var(--space-2) var(--space-4)',
            opacity: 0.4,
            cursor: 'default',
          }}
        >
          Submit Render →
        </button>
      </div>
    </div>
  )
}
