/**
 * OutputClipGallery — grid of rendered clips with scores after job completion.
 */
import type { JobPart } from '../../types/api'

export interface OutputClipGalleryProps {
  parts: JobPart[]
  bestPartNo?: number
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--color-success)'
  if (score >= 60) return '#F59E0B'
  return 'var(--color-text-secondary)'
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div
      style={{
        flex: 1,
        height: 3,
        backgroundColor: 'var(--color-border)',
        borderRadius: 2,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: `${Math.min(100, Math.max(0, value))}%`,
          height: '100%',
          backgroundColor: color,
        }}
      />
    </div>
  )
}

export function OutputClipGallery({ parts, bestPartNo }: OutputClipGalleryProps) {
  if (parts.length === 0) {
    return (
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          opacity: 0.7,
        }}
      >
        No output clips available.
      </div>
    )
  }

  // Sort: done parts by hook_score desc, then failed parts
  const sorted = [...parts].sort((a, b) => {
    const aDone = a.status === 'done'
    const bDone = b.status === 'done'
    if (aDone && !bDone) return -1
    if (!aDone && bDone) return 1
    if (aDone && bDone) return b.hook_score - a.hook_score
    return a.part_no - b.part_no
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <span
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          fontWeight: 'var(--font-weight-medium)' as unknown as number,
        }}
      >
        Output Clips
      </span>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 'var(--space-2)',
        }}
      >
        {sorted.map((part) => {
          const isDone = part.status === 'done'
          const isFailed = part.status === 'failed' || part.status === 'cancelled'
          const isBest = part.part_no === bestPartNo || part.hook_score >= 80
          const hasScore = isDone && (part.hook_score > 0 || part.viral_score > 0)
          const borderCol = isBest && isDone
            ? 'var(--color-success)'
            : isFailed
              ? 'var(--color-error)'
              : 'var(--color-border)'

          return (
            <div
              key={part.part_no}
              style={{
                backgroundColor: 'var(--color-bg-elevated)',
                border: `1px solid ${borderCol}`,
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-3)',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              {/* Header */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 'var(--space-1)',
                }}
              >
                <span
                  style={{
                    fontSize: 'var(--font-size-xs)',
                    fontWeight: 'var(--font-weight-semibold)' as unknown as number,
                    color: 'var(--color-text-primary)',
                  }}
                >
                  {isBest && isDone ? `⭐ Clip #${part.part_no}` : `Clip #${part.part_no}`}
                </span>
                <span
                  style={{
                    fontSize: '10px',
                    backgroundColor: isDone
                      ? 'rgba(34,197,94,0.15)'
                      : isFailed
                        ? 'rgba(239,68,68,0.15)'
                        : 'var(--color-accent-muted)',
                    color: isDone
                      ? 'var(--color-success)'
                      : isFailed
                        ? 'var(--color-error)'
                        : 'var(--color-accent)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '1px 5px',
                    textTransform: 'capitalize' as const,
                  }}
                >
                  {part.status}
                </span>
              </div>

              {/* Scores row */}
              {hasScore && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {/* Hook */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
                    <span style={{ fontSize: '9px', color: 'var(--color-text-secondary)', width: 32, flexShrink: 0 }}>
                      Hook
                    </span>
                    <ScoreBar value={part.hook_score} color={scoreColor(part.hook_score)} />
                    <span style={{ fontSize: '9px', color: scoreColor(part.hook_score), width: 20, textAlign: 'right', flexShrink: 0 }}>
                      {part.hook_score}
                    </span>
                  </div>
                  {/* Viral */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
                    <span style={{ fontSize: '9px', color: 'var(--color-text-secondary)', width: 32, flexShrink: 0 }}>
                      Viral
                    </span>
                    <ScoreBar value={part.viral_score} color={scoreColor(part.viral_score)} />
                    <span style={{ fontSize: '9px', color: scoreColor(part.viral_score), width: 20, textAlign: 'right', flexShrink: 0 }}>
                      {part.viral_score}
                    </span>
                  </div>
                  {/* Motion */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
                    <span style={{ fontSize: '9px', color: 'var(--color-text-secondary)', width: 32, flexShrink: 0 }}>
                      Motion
                    </span>
                    <ScoreBar value={part.motion_score} color={scoreColor(part.motion_score)} />
                    <span style={{ fontSize: '9px', color: scoreColor(part.motion_score), width: 20, textAlign: 'right', flexShrink: 0 }}>
                      {part.motion_score}
                    </span>
                  </div>
                </div>
              )}

              {/* Duration */}
              {isDone && part.duration > 0 && (
                <div
                  style={{
                    fontSize: 'var(--font-size-xs)',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  {part.duration.toFixed(1)}s
                </div>
              )}

              {/* Actions */}
              {isDone && part.output_file && (
                <button
                  onClick={() => { navigator.clipboard.writeText(part.output_file).catch(() => {}) }}
                  title={part.output_file}
                  style={{
                    background: 'none',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--color-text-secondary)',
                    fontSize: 'var(--font-size-xs)',
                    cursor: 'pointer',
                    padding: '3px 8px',
                    textAlign: 'center',
                    fontFamily: 'var(--font-family-base)',
                  }}
                >
                  Copy Path
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
