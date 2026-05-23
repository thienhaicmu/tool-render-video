import { useState, type CSSProperties } from 'react'

export interface TransportBarProps {
  currentTime?: string
  totalDuration?: string
  onPlay?: () => void    // B8 ready
  onPause?: () => void   // B8 ready
  onSeek?: (delta: number) => void  // B8 ready
  onMute?: () => void    // B8 ready
}

type BtnId = 'prev' | 'play' | 'next' | 'mute'

export function TransportBar({
  currentTime = '00:00:00',
  totalDuration = '--:--:--',
}: TransportBarProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [hoveredBtn, setHoveredBtn] = useState<BtnId | null>(null)

  const btnStyle = (id: BtnId): CSSProperties => ({
    width: '28px',
    height: '28px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    backgroundColor: hoveredBtn === id ? 'var(--surface-card)' : 'transparent',
    color: hoveredBtn === id ? 'var(--text-primary)' : 'var(--text-secondary)',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '14px',
    transition: 'background-color var(--duration-instant) var(--ease-out), color var(--duration-instant) var(--ease-out)',
    flexShrink: 0,
  })

  return (
    <div
      style={{
        height: '36px',
        display: 'flex',
        alignItems: 'center',
        padding: '0 var(--space-4)',
        gap: 'var(--space-2)',
        backgroundColor: 'var(--surface-panel)',
        borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
      }}
    >
      {/* Seek backward */}
      <button
        className="btn-motion"
        style={btnStyle('prev')}
        onMouseEnter={() => setHoveredBtn('prev')}
        onMouseLeave={() => setHoveredBtn(null)}
        aria-label="Seek backward"
      >
        ⏮
      </button>

      {/* Play / Pause */}
      <button
        className="btn-motion"
        style={btnStyle('play')}
        onMouseEnter={() => setHoveredBtn('play')}
        onMouseLeave={() => setHoveredBtn(null)}
        onClick={() => setIsPlaying((p) => !p)}
        aria-label={isPlaying ? 'Pause' : 'Play'}
      >
        {isPlaying ? '⏸' : '▶'}
      </button>

      {/* Seek forward */}
      <button
        className="btn-motion"
        style={btnStyle('next')}
        onMouseEnter={() => setHoveredBtn('next')}
        onMouseLeave={() => setHoveredBtn(null)}
        aria-label="Seek forward"
      >
        ⏭
      </button>

      {/* Divider */}
      <div style={{ width: '1px', height: '16px', backgroundColor: 'var(--border-subtle)', margin: '0 var(--space-1)' }} />

      {/* Mute */}
      <button
        className="btn-motion"
        style={btnStyle('mute')}
        onMouseEnter={() => setHoveredBtn('mute')}
        onMouseLeave={() => setHoveredBtn(null)}
        onClick={() => setIsMuted((m) => !m)}
        aria-label={isMuted ? 'Unmute' : 'Mute'}
      >
        {isMuted ? '🔇' : '🔊'}
      </button>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Timecode */}
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
        }}
      >
        {currentTime}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-disabled)' }}>
        /
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
        {totalDuration}
      </span>
    </div>
  )
}
