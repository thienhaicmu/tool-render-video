import { useState } from 'react'

export interface TimelineTrackProps {
  label: string
  color: string
  blocks?: Array<{ start: number; end: number }>
  hasPlayhead?: boolean
  playheadPosition?: number
  onBlockClick?: (blockIndex: number) => void  // B8 ready — unused in B7
}

export function TimelineTrack({
  label,
  color,
  blocks = [],
  hasPlayhead = false,
  playheadPosition = 0,
}: TimelineTrackProps) {
  const [isHovered, setIsHovered] = useState(false)

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
        onMouseLeave={() => setIsHovered(false)}
        style={{
          flex: 1,
          height: '100%',
          position: 'relative',
          backgroundColor: isHovered ? 'var(--surface-card-hover)' : 'transparent',
          transition: 'background-color var(--duration-fast) var(--ease-out)',
          overflow: 'hidden',
        }}
      >
        {/* Clip blocks */}
        {blocks.map((block, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              top: '3px',
              bottom: '3px',
              left: `${block.start * 100}%`,
              width: `${(block.end - block.start) * 100}%`,
              backgroundColor: color,
              borderRadius: 'var(--radius-sm)',
            }}
          />
        ))}

        {/* Playhead */}
        {hasPlayhead && (
          <div
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
      </div>
    </div>
  )
}
