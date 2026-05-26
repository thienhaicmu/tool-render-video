import { useState } from 'react'
import type { Lang } from '../ClipStudio'

const QUALITY_OPTIONS = ['Best Available', '1080p', '720p', '480p']
const FORMAT_OPTIONS  = ['mp4', 'webm', 'mkv']

interface DownloadItem {
  id: string
  url: string
  status: 'queued' | 'downloading' | 'done' | 'failed'
  progress: number
  title: string
}

export function DownloadTab({ lang: _lang }: { lang: Lang }) {
  const [url, setUrl]         = useState('')
  const [quality, setQuality] = useState(QUALITY_OPTIONS[0])
  const [format, setFormat]   = useState(FORMAT_OPTIONS[0])
  const [items, setItems]     = useState<DownloadItem[]>([])

  function addDownload() {
    const v = url.trim()
    if (!v) return
    setItems((prev) => [
      ...prev,
      {
        id:       crypto.randomUUID(),
        url:      v,
        status:   'queued',
        progress: 0,
        title:    v.length > 50 ? v.slice(0, 50) + '…' : v,
      },
    ])
    setUrl('')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--cs-bg-base)' }}>
      {/* URL input area */}
      <div style={{
        padding: '20px',
        borderBottom: '1px solid var(--cs-border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            style={{
              flex: 1,
              background: 'var(--cs-bg-card)',
              border: '1px solid var(--cs-border)',
              borderRadius: '8px',
              padding: '10px 14px',
              fontSize: '13px',
              color: 'var(--cs-text-1)',
              outline: 'none',
              fontFamily: 'var(--cs-font-body)',
            }}
            placeholder="https://youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addDownload()}
          />
          <button
            onClick={addDownload}
            style={{
              padding: '0 20px',
              background: 'var(--cs-accent-dim)',
              border: '1px solid var(--cs-accent)',
              borderRadius: '8px',
              fontFamily: 'var(--cs-font-head)',
              fontSize: '12px',
              fontWeight: 700,
              letterSpacing: '1px',
              textTransform: 'uppercase',
              color: 'var(--cs-accent)',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            ADD
          </button>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: 'var(--cs-text-3)', flexShrink: 0 }}>Quality</span>
          <select
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
            style={{
              background: 'var(--cs-bg-card)',
              border: '1px solid var(--cs-border)',
              borderRadius: '6px',
              padding: '5px 8px',
              fontSize: '11px',
              color: 'var(--cs-text-1)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            {QUALITY_OPTIONS.map((q) => <option key={q}>{q}</option>)}
          </select>

          <span style={{ fontSize: '11px', color: 'var(--cs-text-3)', flexShrink: 0 }}>Format</span>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            style={{
              background: 'var(--cs-bg-card)',
              border: '1px solid var(--cs-border)',
              borderRadius: '6px',
              padding: '5px 8px',
              fontSize: '11px',
              color: 'var(--cs-text-1)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            {FORMAT_OPTIONS.map((f) => <option key={f}>{f}</option>)}
          </select>
        </div>
      </div>

      {/* Queue */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
        {items.length === 0 ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            gap: '12px',
            color: 'var(--cs-text-3)',
            fontSize: '13px',
          }}>
            <span style={{ fontSize: '36px', opacity: 0.3 }}>⬇</span>
            Add URLs above to start downloading
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '10px 14px',
                  background: 'var(--cs-bg-card)',
                  border: '1px solid var(--cs-border)',
                  borderRadius: '8px',
                }}
              >
                <span style={{ fontSize: '16px' }}>▶</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '12px', color: 'var(--cs-text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title}
                  </div>
                  <div style={{
                    marginTop: '4px',
                    height: '3px',
                    background: 'var(--cs-border-hi)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                  }}>
                    <div style={{ width: `${item.progress}%`, height: '100%', background: 'var(--cs-grad)' }} />
                  </div>
                </div>
                <span style={{
                  fontSize: '10px',
                  fontFamily: 'var(--cs-font-head)',
                  fontWeight: 700,
                  letterSpacing: '0.5px',
                  textTransform: 'uppercase',
                  color: item.status === 'done' ? 'var(--cs-ok)' : item.status === 'failed' ? 'var(--cs-fail)' : 'var(--cs-text-3)',
                  flexShrink: 0,
                }}>
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
