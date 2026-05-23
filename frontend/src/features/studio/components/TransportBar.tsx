import { useState, type CSSProperties } from 'react'

export interface TransportBarProps {
  currentTime?: string
  totalDuration?: string
  isPlaying?: boolean       // controlled — add this
  onPlayPause?: () => void  // controlled — add this
  onPlay?: () => void       // B8 ready — keep
  onPause?: () => void      // B8 ready — keep
  onSeek?: (delta: number) => void  // B8 ready — keep
  onMute?: () => void    // B8 ready — keep
  isMuted?: boolean          // NEW — lifted mute state
  onMuteToggle?: () => void  // NEW — lifted mute toggle
}

type BtnId = 'prev' | 'play' | 'next' | 'mute'

export function TransportBar({
  currentTime = '00:00:00',
  totalDuration = '--:--:--',
  isPlaying: isPlayingProp,
  onPlayPause,
  isMuted: isMutedProp,
  onMuteToggle,
  onSeek,
}: TransportBarProps) {
  const [localIsPlaying, setLocalIsPlaying] = useState(false)
  const playing = isPlayingProp !== undefined ? isPlayingProp : localIsPlaying
  const [isMuted, setIsMuted] = useState(false)
  const muted = isMutedProp !== undefined ? isMutedProp : isMuted
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
        onClick={() => onSeek?.(-10)}
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
        onClick={() => {
          if (onPlayPause) {
            onPlayPause()
          } else {
            setLocalIsPlaying((p) => !p)
          }
        }}
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {playing ? '⏸' : '▶'}
      </button>

      {/* Seek forward */}
      <button
        className="btn-motion"
        style={btnStyle('next')}
        onMouseEnter={() => setHoveredBtn('next')}
        onMouseLeave={() => setHoveredBtn(null)}
        onClick={() => onSeek?.(10)}
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
        onClick={() => {
          if (onMuteToggle) {
            onMuteToggle()
          } else {
            setIsMuted((m) => !m)
          }
        }}
        aria-label={muted ? 'Unmute' : 'Mute'}
      >
        {muted ? '🔇' : '🔊'}
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
