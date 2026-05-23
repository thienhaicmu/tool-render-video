/**
 * VideoPreview — native HTML5 video player with event callbacks.
 * Shows an error overlay on load failure. Does not crash on error.
 */
import { useRef, useState } from 'react'

export interface VideoPreviewProps {
  src: string
  poster?: string
  onDuration?: (duration: number) => void
  onTimeUpdate?: (time: number) => void
  onError?: (error: string) => void
}

export function VideoPreview({
  src,
  poster,
  onDuration,
  onTimeUpdate,
  onError,
}: VideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  function handleLoadedMetadata() {
    const video = videoRef.current
    if (!video) return
    setLoadError(null)
    onDuration?.(video.duration)
  }

  function handleTimeUpdate() {
    const video = videoRef.current
    if (!video) return
    onTimeUpdate?.(video.currentTime)
  }

  function handleError() {
    const msg = 'Failed to load video'
    setLoadError(msg)
    onError?.(msg)
  }

  return (
    <div
      className="editor-video-frame"
      style={{ position: 'relative', background: '#000' }}
      data-testid="video-preview"
    >
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        controls
        style={{ width: '100%', display: 'block' }}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onError={handleError}
        data-testid="video-element"
      />
      {loadError && (
        <div
          data-testid="video-error-overlay"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0,0,0,0.7)',
            color: 'var(--color-error)',
            fontSize: 'var(--font-size-sm)',
          }}
        >
          {loadError}
        </div>
      )}
    </div>
  )
}
