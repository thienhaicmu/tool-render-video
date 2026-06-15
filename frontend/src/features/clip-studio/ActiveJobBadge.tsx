/**
 * ActiveJobBadge — cs-shell topbar indicator for running render jobs.
 *
 * Added 2026-06-15 to close Bug #2 (no active-job awareness anywhere in the
 * cs-shell): when the user navigates away from the Rendering screen, there
 * was no visual cue that a render was still in progress. Now a pulsing
 * pill with the running count + the primary job's progress percent appears
 * between the nav and the topbar-right cluster. Clicking the pill switches
 * the active tab to Render — RenderWorkflow's own auto-reattach hook then
 * lands the user on the monitor view.
 */
import { useEffect, useRef, useState } from 'react'
import { getJobHistory } from '@/api/jobs'
import type { HistoryItem } from '@/types/api'

const POLL_MS = 4000

interface ActiveJobBadgeProps {
  onClick: () => void
}

export function ActiveJobBadge({ onClick }: ActiveJobBadgeProps) {
  const [primary, setPrimary] = useState<HistoryItem | null>(null)
  const [count, setCount] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const res = await getJobHistory(10, 0)
        if (cancelled) return
        const active = res.items.filter(
          (j) => j.status === 'running' || j.status === 'queued',
        )
        setCount(active.length)
        setPrimary(active[0] ?? null)
      } catch {
        // backend unreachable — keep last known
      }
    }
    tick()
    pollRef.current = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  if (count === 0 || !primary) return null

  const pct = Math.max(0, Math.min(100, primary.progress_percent || 0))
  const label = primary.status === 'queued'
    ? 'Queued'
    : count > 1
      ? `${count} rendering`
      : `Rendering · ${pct}%`

  return (
    <button
      type="button"
      onClick={onClick}
      title={primary.title || primary.source_hint || 'Active render job'}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        height: 28,
        padding: '0 14px 0 12px',
        background:
          'linear-gradient(135deg, rgba(139,92,246,.14), rgba(236,72,153,.12))',
        border: '1px solid color-mix(in srgb, var(--accent-primary) 30%, transparent)',
        borderRadius: 999,
        color: 'var(--text-primary)',
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: '-0.005em',
        cursor: 'pointer',
        overflow: 'hidden',
        transition: 'all 0.15s ease',
      }}
    >
      {/* Background progress fill — subtle gradient that follows the % */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          width: `${pct}%`,
          background:
            'linear-gradient(135deg, rgba(139,92,246,.20), rgba(236,72,153,.18))',
          transition: 'width 0.6s ease',
          pointerEvents: 'none',
        }}
      />
      <span style={{ position: 'relative', display: 'inline-flex', width: 8, height: 8 }}>
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            background: 'var(--accent-primary)',
            borderRadius: '50%',
            animation: 'aj-pulse 1.4s ease-in-out infinite',
          }}
        />
        <span
          style={{
            position: 'relative',
            width: 8,
            height: 8,
            background: 'var(--accent-primary)',
            borderRadius: '50%',
          }}
        />
      </span>
      <span style={{ position: 'relative' }}>{label}</span>
      <style>{`
        @keyframes aj-pulse {
          0%, 100% { transform: scale(1); opacity: 0.5; }
          50%      { transform: scale(2.2); opacity: 0; }
        }
      `}</style>
    </button>
  )
}
