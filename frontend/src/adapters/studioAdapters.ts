import type { TranscriptSegment } from '../api/render'
import type { JobPart } from '../types/api'
import type { ReviewCardData } from '../features/studio/types'

export interface AIPlanCardData {
  title: string
  confidence: number
  reasoning: string
  impact: string
  tags: string[]
}

export function formatTimecode(sec: number): string {
  const s = Math.floor(sec)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function mapSegmentsToPlan(segments: TranscriptSegment[]): AIPlanCardData[] {
  const limited = segments.slice(0, 5)
  const total = limited.length
  return limited.map((seg, i) => ({
    title: seg.text.trim().slice(0, 40) || `Segment at ${formatTimecode(seg.start)}`,
    confidence: Math.round(85 - (i / Math.max(total - 1, 1)) * 22),
    reasoning: seg.text,
    impact: `Segment ${i + 1} of ${total}`,
    tags: [`${formatTimecode(seg.start)}–${formatTimecode(seg.end)}`],
  }))
}

export function mapPartsToReviewCards(parts: JobPart[]): ReviewCardData[] {
  const done = parts.filter((p) => p.status === 'done')
  return done.map((p) => ({
    id: String(p.part_no),
    title: `Clip ${p.part_no}`,
    confidence: 72,
    reasoning: 'Successfully rendered clip',
    impact: '↑ Rendered output',
    previewTag: `Part ${p.part_no}`,
    clipLabel: `Clip ${p.part_no} of ${done.length}`,
  }))
}
