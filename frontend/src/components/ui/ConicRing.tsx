/**
 * ConicRing — live progress ring (WP0.3, used by the WP1 clip tiles).
 *
 * Distinct from ScoreRing: this shows in-flight progress (0–100) with the
 * brand accent→pink gradient rather than a traffic-light score. The centre
 * renders `children` (e.g. a step icon) or the percentage by default.
 *
 *   <ConicRing progress={72} size={72} />
 *   <ConicRing progress={72} size={40}><IconFilm size={14} /></ConicRing>
 */
import React from 'react'

export interface ConicRingProps {
  /** 0–100. Clamped. */
  progress: number
  /** Outer diameter in px. Default 72. */
  size?: number
  /** Stroke width in px. Default scales with size. */
  stroke?: number
  /** Centre content. Falls back to the percentage. */
  children?: React.ReactNode
  /** Accessible label. Defaults to "{n}%". */
  label?: string
}

let _gradSeq = 0

export function ConicRing({ progress, size = 72, stroke, children, label }: ConicRingProps) {
  // Unique gradient id per instance so multiple rings don't clash.
  const gidRef = React.useRef<string>('')
  if (!gidRef.current) gidRef.current = `conic-grad-${++_gradSeq}`

  const sw = stroke ?? Math.max(4, Math.round(size * 0.085))
  const r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, progress))
  const fill = (clamped / 100) * circ

  return (
    <div
      style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}
      role="img"
      aria-label={label ?? `${Math.round(clamped)}%`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id={gidRef.current} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--ai-active)" />
            <stop offset="100%" stopColor="var(--accent-primary)" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(var(--text-rgb),.08)" strokeWidth={sw} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${gidRef.current})`} strokeWidth={sw}
          strokeDasharray={`${fill} ${circ}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray .35s ease' }}
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {children ?? (
          <span
            style={{
              fontFamily: 'var(--font-display)', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
              fontSize: Math.round(size * 0.26), color: 'var(--accent-primary)',
            }}
          >
            {Math.round(clamped)}%
          </span>
        )}
      </div>
    </div>
  )
}
