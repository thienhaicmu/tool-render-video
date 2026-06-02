/**
 * QualityBadge — colored score badge using thresholds from §8.3.
 * >=85 Good (success), 70-84 Needs Review (warning), 50-69 Warning (error), <50 Poor (neutral)
 */
import React from 'react'
import { Badge } from '../ui/Badge'
import { getQualityLabel, getQualityVariant } from '@/lib/constants'

export interface QualityBadgeProps {
  score: number
  showScore?: boolean
  size?: 'sm' | 'md'
  style?: React.CSSProperties
}

export function QualityBadge({ score, showScore = true, size = 'md', style }: QualityBadgeProps) {
  const label = getQualityLabel(score)
  const variant = getQualityVariant(score)

  return (
    <Badge variant={variant} size={size} style={style}>
      {showScore ? `${Math.round(score)} — ${label}` : label}
    </Badge>
  )
}
