import { TransportBar } from './TransportBar'
import { TimelineTrack } from './TimelineTrack'
import { AIChip } from '../../../components/ui/AIChip'
import { type StudioStep } from '../../../stores/uiStore'

export interface PreviewWorkspaceProps {
  hasMedia?: boolean
  studioStep?: StudioStep | null
  mediaUrl?: string      // B8 ready
  duration?: number      // B8 ready
  currentTime?: number   // B8 ready
}

const TIMELINE_BLOCKS = {
  VIDEO:  [{ start: 0.0,  end: 0.85 }],
  SUBS:   [
    { start: 0.05, end: 0.25 },
    { start: 0.35, end: 0.55 },
    { start: 0.65, end: 0.80 },
  ],
  AI_MKR: [
    { start: 0.04, end: 0.06 },
    { start: 0.32, end: 0.34 },
    { start: 0.65, end: 0.67 },
  ],
}

export function PreviewWorkspace({ hasMedia = false, studioStep }: PreviewWorkspaceProps) {
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
      {/* Player container — flex-based, no maxHeight hack */}
      <div
        style={{
          flexBasis: '40%',
          flexShrink: 0,
          flexGrow: 0,
          backgroundColor: 'var(--surface-base)',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* 16:9 letterbox */}
        <div
          style={{
            maxWidth: '100%',
            maxHeight: '100%',
            aspectRatio: '16 / 9',
            margin: 'auto',
            backgroundColor: '#000000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
          }}
        >
          {!hasMedia && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 'var(--space-4)',
              }}
            >
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--surface-card)',
                  border: '1px solid var(--border-default)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '20px',
                  color: 'var(--text-tertiary)',
                }}
              >
                ▶
              </div>
              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-secondary)',
                    fontWeight: 'var(--weight-medium)' as unknown as number,
                  }}
                >
                  Ready to preview
                </div>
                <div
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-tertiary)',
                    marginTop: 'var(--space-1)',
                  }}
                >
                  Add a source file to begin
                </div>
              </div>
            </div>
          )}
        </div>
        {/* AI overlay — visible only when media is loaded */}
        {hasMedia && (
          <div style={{ position: 'absolute', top: 'var(--space-2)', right: 'var(--space-2)' }}>
            <AIChip variant="applied" label="AI Director" />
          </div>
        )}
      </div>

      {/* Transport controls */}
      <TransportBar />

      {/* Timeline */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Ruler */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            height: '20px',
            borderBottom: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <div style={{ width: 'var(--timeline-label-w)', flexShrink: 0 }} />
          <div
            style={{
              flex: 1,
              display: 'flex',
              justifyContent: 'space-between',
              padding: '0 var(--space-2)',
            }}
          >
            {['0:00', '0:30', '1:00', '1:30'].map((t) => (
              <span
                key={t}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-tertiary)',
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>

        {/* Tracks */}
        <TimelineTrack
          label="VIDEO"
          color="var(--accent-subtle)"
          blocks={TIMELINE_BLOCKS.VIDEO}
          hasPlayhead
          playheadPosition={0.15}
        />
        <TimelineTrack
          label="SUBS"
          color="var(--accent-subtle)"
          blocks={TIMELINE_BLOCKS.SUBS}
        />
        <TimelineTrack
          label="AI MKR"
          color="var(--ai-subtle)"
          blocks={TIMELINE_BLOCKS.AI_MKR}
        />
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
            border: '1px solid transparent',
            borderRadius: 'var(--radius-md)',
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
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
            padding: 'var(--space-2) var(--space-4)',
            opacity: 0.4,
            cursor: 'not-allowed',
          }}
        >
          Submit Render →
        </button>
      </div>
      {studioStep === 'plan' && (
        <div
          style={{
            textAlign: 'center',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            padding: 'var(--space-1) var(--space-6) var(--space-2)',
          }}
        >
          3 clips selected by AI Director
        </div>
      )}
    </div>
  )
}
