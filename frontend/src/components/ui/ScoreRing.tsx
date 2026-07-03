/**
 * ScoreRing — canonical 0–100 score ring (WP0.3).
 *
 * Extracted from the two ad-hoc SVG rings in StepResults (ScoreRingSm /
 * ScoreRingLg). One primitive, size-driven; tone auto-derives from the
 * shared scoring thresholds unless overridden.
 *
 *   <ScoreRing value={87} size={68} />
 */
import { scoreColor } from '@/features/clip-studio/render/scoring'

export interface ScoreRingProps {
  /** 0–100. Clamped. */
  value: number
  /** Outer diameter in px. Default 34. */
  size?: number
  /** Stroke width in px. Default scales with size. */
  stroke?: number
  /** Override arc colour. Defaults to scoreColor(value). */
  tone?: string
  /** Show the numeric value in the centre. Default true. */
  showValue?: boolean
}

export function ScoreRing({ value, size = 34, stroke, tone, showValue = true }: ScoreRingProps) {
  const sw = stroke ?? Math.max(3, Math.round(size * 0.1))
  const r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, value))
  const fill = (clamped / 100) * circ
  const col = tone ?? scoreColor(clamped)

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(var(--text-rgb),.1)" strokeWidth={sw} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={sw}
          strokeDasharray={`${fill} ${circ}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray .4s ease' }}
        />
      </svg>
      {showValue && (
        <span
          style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-display)', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
            fontSize: Math.round(size * 0.32), color: col,
          }}
        >
          {Math.round(clamped)}
        </span>
      )}
    </div>
  )
}
