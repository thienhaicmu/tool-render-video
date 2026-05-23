import { useState } from 'react'
import { TimelineClip } from './TimelineClip'

export interface TimelineTrackProps {
  label: string
  color: string
  blocks?: Array<{ start: number; end: number }>
  hasPlayhead?: boolean
  playheadPosition?: number
  onBlockClick?: (blockIndex: number) => void  // B8 ready — kept for compat
  onSeek?: (position: number) => void
  selectedClipId?: string | null
  onClipSelect?: (id: string | null) => void
  zoom?: number
  markerMeta?: Array<{
    label: string
    timecode: string
    confidence: number
  }>
}

export function TimelineTrack({
  label,
  color,
  blocks = [],
  hasPlayhead = false,
  playheadPosition = 0,
  onSeek,
  selectedClipId,
  onClipSelect,
  zoom = 1,
  markerMeta,
}: TimelineTrackProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [ghostPosition, setGhostPosition] = useState<number | null>(null)
  const [hoveredClipIdx, setHoveredClipIdx] = useState<number | null>(null)

  const handleTrackMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setGhostPosition((e.clientX - rect.left) / rect.width)
  }

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek) return
    const rect = e.currentTarget.getBoundingClientRect()
    onSeek((e.clientX - rect.left) / rect.width)
  }

  const scoreColor = (confidence: number) => {
    if (confidence >= 70) return 'var(--score-high)'
    if (confidence >= 40) return 'var(--score-mid)'
    return 'var(--score-low)'
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        height: 'var(--timeline-track-h)',
        borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
      }}
    >
      {/* Label column */}
      <div
        style={{
          width: 'var(--timeline-label-w)',
          flexShrink: 0,
          fontSize: 'var(--text-xs)',
          color: isHovered ? 'var(--text-secondary)' : 'var(--text-tertiary)',
          padding: '0 var(--space-2)',
          userSelect: 'none',
          transition: 'color var(--duration-fast) var(--ease-out)',
        }}
      >
        {label}
      </div>

      {/* Track content area */}
      <div
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => { setIsHovered(false); setGhostPosition(null) }}
        onMouseMove={onSeek ? handleTrackMouseMove : undefined}
        onClick={handleTrackClick}
        style={{
          flex: 1,
          height: '100%',
          position: 'relative',
          backgroundColor: isHovered ? 'var(--surface-card-hover)' : 'transparent',
          transition: 'background-color var(--duration-fast) var(--ease-out)',
          overflow: markerMeta ? 'visible' : 'hidden',
          cursor: onSeek ? 'pointer' : 'default',
        }}
      >
        {/* Clip blocks */}
        {blocks.map((block, i) => {
          const clipId = `${label}-${i}`
          return (
            <TimelineClip
              key={clipId}
              id={clipId}
              start={block.start}
              end={block.end}
              color={color}
              isSelected={selectedClipId === clipId}
              zoom={zoom}
              onClick={() => onClipSelect?.(selectedClipId === clipId ? null : clipId)}
              onHover={markerMeta ? (h) => setHoveredClipIdx(h ? i : null) : undefined}
            />
          )
        })}

        {/* Ghost cursor */}
        {onSeek && (
          <div
            className="timeline-ghost-cursor"
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              width: '1px',
              backgroundColor: 'var(--text-tertiary)',
              opacity: ghostPosition !== null ? 0.5 : 0,
              left: `${(ghostPosition ?? 0) * 100}%`,
              zIndex: 1,
            }}
          />
        )}

        {/* Playhead */}
        {hasPlayhead && (
          <div
            className="playhead-line"
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${playheadPosition * 100}%`,
              width: '1px',
              backgroundColor: 'var(--text-primary)',
              zIndex: 2,
            }}
          />
        )}

        {/* Marker tooltip — only for tracks with markerMeta */}
        {markerMeta && hoveredClipIdx !== null && markerMeta[hoveredClipIdx] && (
          <div
            style={{
              position: 'absolute',
              bottom: '100%',
              left: `${blocks[hoveredClipIdx].start * 100 * zoom}%`,
              backgroundColor: 'var(--surface-overlay)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-1) var(--space-2)',
              zIndex: 10,
              pointerEvents: 'none',
              boxShadow: 'var(--shadow-tooltip)',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-1)',
            }}
          >
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              {markerMeta[hoveredClipIdx].label}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>·</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
              {markerMeta[hoveredClipIdx].timecode}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>·</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: scoreColor(markerMeta[hoveredClipIdx].confidence) }}>
              {markerMeta[hoveredClipIdx].confidence}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
