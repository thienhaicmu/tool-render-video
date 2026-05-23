import { useState, useEffect, useRef } from 'react'
import { TransportBar } from './TransportBar'
import { TimelineTrack } from './TimelineTrack'
import { TimelineZoomControl } from './TimelineZoomControl'
import { AIChip } from '../../../components/ui/AIChip'
import { type StudioStep } from '../../../stores/uiStore'

export interface PreviewWorkspaceProps {
  hasMedia?: boolean
  studioStep?: StudioStep | null
  mediaUrl?: string
  duration?: number      // B8 ready
  currentTime?: number   // B8 ready
}

const TIMELINE_BLOCKS = {
  VIDEO:  [{ start: 0.0,  end: 0.85 }],
  SUBS:   [
    { start: 0.05, end: 0.25 },
    { start: 0.35, end: 0.55 },
    { start: 0.65, end: 0.80 },
  ],
  AI_MKR: [
    { start: 0.04, end: 0.06 },
    { start: 0.32, end: 0.34 },
    { start: 0.65, end: 0.67 },
  ],
}

const MARKER_META = [
  { label: 'Hook detected', timecode: '0:04', confidence: 87 },
  { label: 'Energy peak',   timecode: '0:38', confidence: 74 },
  { label: 'CTA moment',    timecode: '1:18', confidence: 61 },
]

const TOTAL_DURATION_SECS = 120

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || isNaN(seconds) || seconds < 0) return '--:--'
  const s = Math.floor(seconds)
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function PreviewWorkspace({ hasMedia = false, studioStep, mediaUrl }: PreviewWorkspaceProps) {
  // B11 illusion state (used when no mediaUrl)
  const [playheadPosition, setPlayheadPosition] = useState(0.15)
  const [isPlaying, setIsPlaying] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(1)
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null)
  const intervalRef = useRef<number | null>(null)

  // B12 real video state
  const videoRef = useRef<HTMLVideoElement>(null)
  const [videoCurrentTime, setVideoCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [isMuted, setIsMuted] = useState(false)

  // B11 interval illusion — only runs when no real media
  useEffect(() => {
    if (!mediaUrl && isPlaying) {
      intervalRef.current = window.setInterval(() => {
        setPlayheadPosition((prev) => {
          const next = prev + (0.1 / TOTAL_DURATION_SECS)
          if (next >= 1) {
            setIsPlaying(false)
            return 0
          }
          return next
        })
      }, 100)
    } else {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [isPlaying, mediaUrl])

  // Reset video state when mediaUrl changes (including removal)
  useEffect(() => {
    setVideoCurrentTime(0)
    setIsPlaying(false)
    setVideoDuration(0)
    setIsLoading(mediaUrl ? true : false)
  }, [mediaUrl])

  // Sync muted state to video element (React muted prop doesn't update reliably after mount)
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted
    }
  }, [isMuted])

  // Video event handlers
  const handleVideoTimeUpdate = () => {
    if (videoRef.current) {
      setVideoCurrentTime(videoRef.current.currentTime)
    }
  }

  const handleVideoLoadedMetadata = () => {
    if (videoRef.current) {
      setVideoDuration(videoRef.current.duration)
      setIsLoading(false)
    }
  }

  const handleVideoEnded = () => {
    setIsPlaying(false)
  }

  const handleVideoPlay = () => {
    setIsPlaying(true)
  }

  const handleVideoPause = () => {
    setIsPlaying(false)
  }

  const handleVideoLoadStart = () => {
    setIsLoading(true)
  }

  const handleVideoCanPlay = () => {
    setIsLoading(false)
  }

  // Play/pause — direct DOM call avoids circular state updates
  const handlePlayPause = () => {
    if (mediaUrl && videoRef.current) {
      if (videoRef.current.paused) {
        videoRef.current.play().catch(() => {})
      } else {
        videoRef.current.pause()
      }
      // isPlaying is set by onPlay/onPause events, NOT here
    } else {
      setIsPlaying((p) => !p)
    }
  }

  // Timeline seek — real seek when media present, illusion seek otherwise
  const handleTimelineSeek = (position: number) => {
    if (mediaUrl && videoRef.current && videoDuration > 0) {
      videoRef.current.currentTime = position * videoDuration
    } else {
      setPlayheadPosition(position)
    }
  }

  // Transport ±10s seek
  const handleSeek = (delta: number) => {
    if (mediaUrl && videoRef.current && videoDuration > 0) {
      const clamped = Math.max(0, Math.min(videoDuration, videoRef.current.currentTime + delta))
      videoRef.current.currentTime = clamped
    }
    // No-op in illusion mode
  }

  // Derived display values
  const resolvedPlayheadPosition = mediaUrl && videoDuration > 0
    ? videoCurrentTime / videoDuration
    : playheadPosition

  const timecodeDisplay = mediaUrl
    ? formatTime(videoCurrentTime)
    : (() => {
        const s = Math.floor(playheadPosition * TOTAL_DURATION_SECS)
        return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
      })()

  const totalDurationDisplay = mediaUrl
    ? (videoDuration > 0 ? formatTime(videoDuration) : '--:--')
    : '02:00'

  const showAIChip = mediaUrl || hasMedia

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        minWidth: 0,
      }}
    >
      {/* Player container */}
      <div
        style={{
          flexBasis: '40%',
          flexShrink: 0,
          flexGrow: 0,
          backgroundColor: 'var(--surface-base)',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* 16:9 letterbox */}
        <div
          style={{
            maxWidth: '100%',
            maxHeight: '100%',
            aspectRatio: '16 / 9',
            margin: 'auto',
            backgroundColor: '#000000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
            position: 'relative',
          }}
        >
          {/* Real video element */}
          {mediaUrl && (
            <video
              ref={videoRef}
              src={mediaUrl}
              muted={isMuted}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                display: 'block',
              }}
              onTimeUpdate={handleVideoTimeUpdate}
              onLoadedMetadata={handleVideoLoadedMetadata}
              onEnded={handleVideoEnded}
              onPlay={handleVideoPlay}
              onPause={handleVideoPause}
              onLoadStart={handleVideoLoadStart}
              onCanPlay={handleVideoCanPlay}
            />
          )}

          {/* Empty state — no media loaded */}
          {!mediaUrl && !hasMedia && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 'var(--space-4)',
              }}
            >
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--surface-card)',
                  border: '1px solid var(--border-default)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '20px',
                  color: 'var(--text-tertiary)',
                }}
              >
                ▶
              </div>
              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-secondary)',
                    fontWeight: 'var(--weight-medium)' as unknown as number,
                  }}
                >
                  Ready to preview
                </div>
                <div
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-tertiary)',
                    marginTop: 'var(--space-1)',
                  }}
                >
                  Add a source file to begin
                </div>
              </div>
            </div>
          )}

          {/* Loading overlay */}
          {isLoading && mediaUrl && (
            <div
              style={{
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                left: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'rgba(0,0,0,0.4)',
                pointerEvents: 'none',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                }}
              >
                Loading…
              </span>
            </div>
          )}
        </div>

        {/* AI Director chip overlay */}
        {showAIChip && (
          <div style={{ position: 'absolute', top: 'var(--space-2)', right: 'var(--space-2)' }}>
            <AIChip variant="applied" label="AI Director" />
          </div>
        )}
      </div>

      {/* Transport controls */}
      <TransportBar
        isPlaying={isPlaying}
        onPlayPause={handlePlayPause}
        currentTime={timecodeDisplay}
        totalDuration={totalDurationDisplay}
        isMuted={isMuted}
        onMuteToggle={() => setIsMuted((m) => !m)}
        onSeek={handleSeek}
      />

      {/* Timeline */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Ruler */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            height: '20px',
            borderBottom: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <div style={{ width: 'var(--timeline-label-w)', flexShrink: 0 }} />
          <div
            style={{
              flex: 1,
              display: 'flex',
              justifyContent: 'space-between',
              padding: '0 var(--space-2)',
              alignItems: 'center',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', flex: 1 }}>
              {['0:00', '0:30', '1:00', '1:30'].map((t) => (
                <span
                  key={t}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
            <TimelineZoomControl zoom={zoomLevel} onZoomChange={setZoomLevel} />
          </div>
        </div>

        {/* Tracks */}
        <TimelineTrack
          label="VIDEO"
          color="var(--accent-subtle)"
          blocks={TIMELINE_BLOCKS.VIDEO}
          hasPlayhead
          playheadPosition={resolvedPlayheadPosition}
          onSeek={handleTimelineSeek}
          selectedClipId={selectedClipId}
          onClipSelect={setSelectedClipId}
          zoom={zoomLevel}
        />
        <TimelineTrack
          label="SUBS"
          color="var(--accent-subtle)"
          blocks={TIMELINE_BLOCKS.SUBS}
          hasPlayhead
          playheadPosition={resolvedPlayheadPosition}
          onSeek={handleTimelineSeek}
          selectedClipId={selectedClipId}
          onClipSelect={setSelectedClipId}
          zoom={zoomLevel}
        />
        <TimelineTrack
          label="AI MKR"
          color="var(--ai-subtle)"
          blocks={TIMELINE_BLOCKS.AI_MKR}
          hasPlayhead
          playheadPosition={resolvedPlayheadPosition}
          onSeek={handleTimelineSeek}
          selectedClipId={selectedClipId}
          onClipSelect={setSelectedClipId}
          zoom={zoomLevel}
          markerMeta={MARKER_META}
        />
      </div>

      {/* Action row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-6)',
          borderTop: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}
      >
        <button
          disabled
          style={{
            background: 'none',
            border: '1px solid transparent',
            borderRadius: 'var(--radius-md)',
            cursor: 'default',
            color: 'var(--text-tertiary)',
            fontSize: 'var(--text-sm)',
            padding: 'var(--space-2) var(--space-3)',
          }}
        >
          ← Back to Source
        </button>
        <button
          disabled
          style={{
            background: 'var(--accent-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--weight-medium)' as unknown as number,
            padding: 'var(--space-2) var(--space-4)',
            opacity: 0.4,
            cursor: 'not-allowed',
          }}
        >
          Submit Render →
        </button>
      </div>
      {studioStep === 'plan' && (
        <div
          style={{
            textAlign: 'center',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            padding: 'var(--space-1) var(--space-6) var(--space-2)',
          }}
        >
          3 clips selected by AI Director
        </div>
      )}
    </div>
  )
}
