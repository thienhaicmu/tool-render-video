/**
 * ProgressClipsGrid — compact visual grid of all clips during render.
 * Replaces ProgressPartList for the new layout.
 */
import type { JobPart } from '@/types/api'
import type { JobPartStageEnum, RenderStage } from '@/types/enums'

// Statuses that mark a clip as actively processing. Mixes per-part stages
// (rendering/cutting/transcribing) with the legacy 'downloading' job stage;
// `satisfies` validates every member against the C1 contract unions.
const ACTIVE_CLIP_STATUSES = [
  'rendering',
  'cutting',
  'transcribing',
  'downloading',
] as const satisfies readonly (RenderStage | JobPartStageEnum)[]

export interface ProgressClipsGridProps {
  liveParts: JobPart[]
  activeParts: Array<{ part_no: number; status: string; progress_percent: number }>
  completedParts: number
  failedParts: number
  totalParts: number
}

interface ClipState {
  part_no: number
  status: string
  progress_percent: number
  hook_score: number
  viral_score: number
  hasScore: boolean
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--color-success)'
  if (score >= 60) return '#F59E0B'
  return 'var(--color-text-secondary)'
}

function borderColor(status: string, hasScore: boolean, avgScore: number): string {
  if (status === 'done') {
    if (hasScore && avgScore >= 80) return 'var(--color-success)'
    return 'var(--color-success)'
  }
  const activeStatuses = new Set<string>(ACTIVE_CLIP_STATUSES)
  if (activeStatuses.has(status)) return 'var(--color-accent)'
  return 'var(--color-border)'
}

export function ProgressClipsGrid({
  liveParts,
  activeParts,
  completedParts,
  failedParts,
  totalParts,
}: ProgressClipsGridProps) {
  // No data at all
  if (liveParts.length === 0 && totalParts === 0) {
    return (
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          opacity: 0.7,
        }}
      >
        Clips will appear once rendering starts.
      </div>
    )
  }

  // Build unified clip map: liveParts (have scores) take precedence
  const clipMap = new Map<number, ClipState>()

  // Seed from liveParts first (most complete data)
  for (const lp of liveParts) {
    const hasScore = lp.hook_score > 0 || lp.viral_score > 0
    clipMap.set(lp.part_no, {
      part_no: lp.part_no,
      status: lp.status,
      progress_percent: lp.progress_percent,
      hook_score: lp.hook_score,
      viral_score: lp.viral_score,
      hasScore,
    })
  }

  // Fill from activeParts if not already present
  for (const ap of activeParts) {
    if (!clipMap.has(ap.part_no)) {
      clipMap.set(ap.part_no, {
        part_no: ap.part_no,
        status: ap.status,
        progress_percent: ap.progress_percent,
        hook_score: 0,
        viral_score: 0,
        hasScore: false,
      })
    }
  }

  // Fill waiting slots up to totalParts
  for (let i = 1; i <= totalParts; i++) {
    if (!clipMap.has(i)) {
      clipMap.set(i, {
        part_no: i,
        status: 'waiting',
        progress_percent: 0,
        hook_score: 0,
        viral_score: 0,
        hasScore: false,
      })
    }
  }

  const clips = Array.from(clipMap.values()).sort((a, b) => a.part_no - b.part_no)

  const activeStatuses = new Set<string>(ACTIVE_CLIP_STATUSES)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
        }}
      >
        <span style={{ fontWeight: 'var(--font-weight-medium)' as unknown as number }}>Clips</span>
        <span>
          {completedParts}/{totalParts} done
          {failedParts > 0 && (
            <span style={{ color: 'var(--color-error)', marginLeft: 'var(--space-2)' }}>
              {failedParts} failed
            </span>
          )}
        </span>
      </div>

      {/* Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(52px, 1fr))',
          gap: 'var(--space-1)',
        }}
      >
        {clips.map((clip) => {
          const isDone = clip.status === 'done'
          const isFailed = clip.status === 'failed' || clip.status === 'cancelled'
          const isActive = activeStatuses.has(clip.status)
          const isWaiting = !isDone && !isFailed && !isActive
          const avgScore = clip.hasScore
            ? Math.round((clip.hook_score + clip.viral_score) / 2)
            : 0
          const border = borderColor(clip.status, clip.hasScore, avgScore)

          return (
            <div
              key={clip.part_no}
              style={{
                width: '100%',
                minWidth: 0,
                height: 70,
                border: `1px solid ${border}`,
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 2,
                padding: '4px 2px',
                opacity: isWaiting ? 0.5 : 1,
                backgroundColor: 'var(--color-bg-elevated)',
                boxSizing: 'border-box',
              }}
            >
              {/* Clip number */}
              <span
                style={{
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--color-text-secondary)',
                  lineHeight: 1,
                }}
              >
                #{clip.part_no}
              </span>

              {/* Status display */}
              {isDone && clip.hasScore && (
                <span
                  style={{
                    fontSize: 'var(--font-size-sm)',
                    fontWeight: 'var(--font-weight-semibold)' as unknown as number,
                    color: scoreColor(avgScore),
                    lineHeight: 1,
                  }}
                >
                  {avgScore}
                </span>
              )}

              {isDone && !clip.hasScore && (
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-success)', lineHeight: 1 }}>
                  ✓
                </span>
              )}

              {isFailed && (
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-error)', lineHeight: 1 }}>
                  ✕
                </span>
              )}

              {isActive && (
                <>
                  <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-accent)', lineHeight: 1 }}>
                    ◐
                  </span>
                  {/* Mini progress bar */}
                  <div
                    style={{
                      width: '80%',
                      height: 3,
                      backgroundColor: 'var(--color-border)',
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${clip.progress_percent}%`,
                        height: '100%',
                        backgroundColor: 'var(--color-accent)',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                  <span style={{ fontSize: '9px', color: 'var(--color-text-secondary)', lineHeight: 1 }}>
                    {clip.progress_percent}%
                  </span>
                </>
              )}

              {isWaiting && (
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-border)', lineHeight: 1 }}>
                  ○
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
