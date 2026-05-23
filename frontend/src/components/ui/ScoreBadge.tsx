/**
 * ScoreBadge — Numeric score display with semantic color and optional count-up animation.
 * Source: docs/design/components.md component #4
 */
import { useEffect, useRef } from 'react'
import { animateScore } from '../../lib/animateScore'

export type ScoreBadgeSize = 'xl' | 'lg' | 'md' | 'sm'

export interface ScoreBadgeProps {
  value: number
  size?: ScoreBadgeSize
  animate?: boolean
}

function getScoreColor(value: number): string {
  if (value >= 70) return 'var(--score-high)'
  if (value >= 40) return 'var(--score-mid)'
  return 'var(--score-low)'
}

const SIZE_FONT: Record<ScoreBadgeSize, string> = {
  xl: 'var(--text-score-xl)',
  lg: 'var(--text-2xl)',
  md: 'var(--text-xl)',
  sm: 'var(--text-base)',
}

export function ScoreBadge({ value, size = 'md', animate = false }: ScoreBadgeProps) {
  const spanRef = useRef<HTMLSpanElement>(null)
  const color = getScoreColor(value)
  const fontSize = SIZE_FONT[size]

  useEffect(() => {
    if (animate && spanRef.current) {
      animateScore(spanRef.current, value)
    } else if (spanRef.current) {
      spanRef.current.textContent = String(Math.round(value))
    }
  }, [value, animate])

  return (
    <span
      ref={spanRef}
      className={size === 'xl' ? 'score-value--xl' : undefined}
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-ui)',
        fontSize,
        fontWeight: 'var(--weight-semibold)' as unknown as number,
        color,
        backgroundColor: 'var(--score-track-bg)',
        borderRadius: 'var(--radius-md)',
        padding: size === 'xl' ? 'var(--space-3) var(--space-4)' : '0 var(--space-2)',
        lineHeight: 'var(--leading-tight)',
      }}
    >
      {animate ? '0' : Math.round(value)}
    </span>
  )
}
