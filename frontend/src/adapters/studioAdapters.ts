import type { TranscriptSegment } from '../api/render'
import type { JobPart } from '../types/api'
import type { ReviewCardData } from '../features/studio/types'

export interface AIPlanCardData {
  title: string
  confidence: number
  reasoning: string
  impact: string
  tags: string[]
  startSec: number
  endSec: number
}

export function formatTimecode(sec: number): string {
  const s = Math.floor(sec)
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Group transcript segments into ~60-second clip windows.
 * Each window becomes one plan card — the user can approve it to add it
 * to clip_lock in the render request.
 */
export function mapSegmentsToPlan(segments: TranscriptSegment[]): AIPlanCardData[] {
  if (segments.length === 0) return []

  const TARGET_WINDOW_SEC = 60
  const MAX_CARDS = 8

  const cards: AIPlanCardData[] = []
  let windowStartIdx = 0

  while (windowStartIdx < segments.length && cards.length < MAX_CARDS) {
    const windowStart = segments[windowStartIdx].start
    let windowEndIdx = windowStartIdx

    // Grow window until it hits ~60s or end of segments
    while (
      windowEndIdx < segments.length - 1 &&
      segments[windowEndIdx].end - windowStart < TARGET_WINDOW_SEC
    ) {
      windowEndIdx++
    }

    const windowEnd = segments[windowEndIdx].end
    const windowSec = windowEnd - windowStart
    const windowText = segments
      .slice(windowStartIdx, windowEndIdx + 1)
      .map((s) => s.text)
      .join(' ')
      .trim()

    // Simple heuristic confidence: earlier segments score higher (hook bias),
    // with a mild bonus for denser text (more words per second)
    const wordCount = windowText.split(/\s+/).length
    const density = windowSec > 0 ? wordCount / windowSec : 0
    const positionPenalty = (cards.length / MAX_CARDS) * 20
    const densityBonus = Math.min(density * 3, 10)
    const confidence = Math.round(
      Math.max(45, Math.min(94, 82 - positionPenalty + densityBonus)),
    )

    cards.push({
      title: windowText.slice(0, 55) || `Clip at ${formatTimecode(windowStart)}`,
      confidence,
      reasoning: windowText.slice(0, 140) || 'Segment of transcript.',
      impact: `${formatTimecode(windowStart)} → ${formatTimecode(windowEnd)} · ~${Math.round(windowSec)}s`,
      tags: [
        formatTimecode(windowStart),
        `${Math.round(windowSec)}s`,
      ],
      startSec: windowStart,
      endSec: windowEnd,
    })

    windowStartIdx = windowEndIdx + 1
  }

  return cards
}

export function mapPartsToReviewCards(parts: JobPart[]): ReviewCardData[] {
  const done = parts.filter((p) => p.status === 'done')
  return done.map((p) => {
    const filename = p.output_file
      ? p.output_file.split(/[/\\]/).pop() ?? `clip_${p.part_no}.mp4`
      : `clip_${p.part_no}.mp4`

    return {
      id: String(p.part_no),
      title: `Clip ${p.part_no}`,
      confidence: 0, // real score fetched on demand via quality endpoint — 0 means "not scored yet"
      reasoning: filename,
      impact: p.output_file ? `✓ ${filename}` : 'Rendered output',
      previewTag: `Part ${p.part_no}`,
      clipLabel: `Clip ${p.part_no} of ${done.length}`,
    }
  })
}
