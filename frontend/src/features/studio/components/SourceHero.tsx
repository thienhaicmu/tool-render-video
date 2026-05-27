import { useState, useRef } from 'react'
import { prepareSource } from '../../../api/render'
import { uploadFile } from '../../../api/upload'
import { useI18n } from '../../../i18n/useI18n'

const ALLOWED_EXTS = new Set(['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'm4v', 'ts', 'wmv'])

interface SourceHeroProps {
  onSessionReady: (
    id: string,
    title: string,
    duration: number,
    sourceMode: 'youtube' | 'local',
    outputDir: string,
  ) => void
}

function IconUpload() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16"/>
      <line x1="12" y1="12" x2="12" y2="21"/>
      <path d="M20.4 17.4A5 5 0 0018 8h-1.3A8 8 0 103 16.3"/>
    </svg>
  )
}

function IconArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12"/>
      <polyline points="12 5 19 12 12 19"/>
    </svg>
  )
}

export function SourceHero({ onSessionReady }: SourceHeroProps) {
  const { t } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleLocal = async (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ALLOWED_EXTS.has(ext)) {
      setError(t('source_error_local'))
      return
    }
    setLoading(true)
    setError(null)
    try {
      const electronPath = (f as any).path as string | undefined
      let videoPath: string
      if (electronPath && electronPath.length > 1) {
        videoPath = electronPath
      } else {
        const uploaded = await uploadFile(f)
        videoPath = uploaded.path
      }
      const res = await prepareSource({ source_mode: 'local', source_video_path: videoPath })
      onSessionReady(res.session_id, res.title, res.duration, 'local', res.export_dir)
    } catch {
      setError(t('source_error_local'))
    } finally {
      setLoading(false)
    }
  }

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    if (f) { setFile(f); setError(null) }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) { setFile(f); setError(null) }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        {/* Brand */}
        <div style={s.brand}>
          <div style={s.brandIcon}>✦</div>
          <span style={s.brandText}>AI Video Studio</span>
        </div>

        <h1 style={s.headline}>{t('source_headline')}</h1>
        <p style={s.sub}>{t('source_sub')}</p>

        {/* Drop zone */}
        <div style={s.inputWrap}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !loading && fileInputRef.current?.click()}
            style={{
              ...s.dropZone,
              borderColor: dragOver
                ? '#a855f7'
                : file
                ? 'rgba(52,200,120,0.5)'
                : error
                ? 'var(--status-error)'
                : 'var(--border-default)',
              backgroundColor: dragOver
                ? 'rgba(168,85,247,0.06)'
                : file
                ? 'rgba(52,200,120,0.04)'
                : 'var(--surface-input)',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              style={{ display: 'none' }}
              onChange={onFileChange}
              disabled={loading}
            />
            {file ? (
              <div style={s.fileInfo}>
                <span style={{ color: 'var(--status-success)', fontSize: '28px', lineHeight: 1 }}>✓</span>
                <span style={s.fileName}>{file.name}</span>
                <span style={s.fileMeta}>{(file.size / 1024 / 1024).toFixed(1)} MB</span>
              </div>
            ) : (
              <div style={s.dropContent}>
                <span style={{ color: 'var(--text-tertiary)' }}><IconUpload /></span>
                <div style={s.dropHintMain}>{t('source_drop_hint')}</div>
                <div style={s.dropHintSub}>{t('source_drop_hint_sub')}</div>
              </div>
            )}
          </div>

          {error && <span style={s.errorText}>{error}</span>}

          <button
            onClick={() => file && handleLocal(file)}
            disabled={loading || !file}
            style={{
              ...s.ctaBtn,
              opacity: loading || !file ? 0.45 : 1,
              cursor: loading || !file ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? (
              <>
                <span style={s.spinner} />
                <span>{t('source_btn_uploading')}</span>
              </>
            ) : (
              <>
                <span>{t('source_btn_generate')}</span>
                <IconArrow />
              </>
            )}
          </button>
        </div>

        {/* Supported formats */}
        <div style={s.platforms}>
          <span style={s.platformsLabel}>Supports</span>
          {['MP4', 'MOV', 'MKV', 'AVI', 'WEBM', 'FLV'].map((p) => (
            <span key={p} style={s.platformChip}>{p}</span>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes sh-spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 'var(--space-6)',
    backgroundColor: 'var(--surface-base)',
    overflowY: 'auto',
    position: 'relative',
  },
  card: {
    position: 'relative',
    width: '100%',
    maxWidth: 'min(480px, 100%)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-5)',
    padding: 'var(--space-8)',
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-default)',
    borderRadius: '20px',
    boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  brandIcon: {
    fontSize: '20px',
    background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    lineHeight: 1,
  },
  brandText: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    color: 'var(--text-tertiary)',
  },
  headline: {
    margin: 0,
    fontSize: 'clamp(22px, 3vw, 28px)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.025em',
    lineHeight: 1.2,
  },
  sub: {
    margin: '-8px 0 0',
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
    lineHeight: 1.6,
  },
  inputWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  ctaBtn: {
    height: '52px',
    border: 'none',
    borderRadius: '12px',
    background: 'linear-gradient(135deg, #a855f7 0%, #4d7cff 100%)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 700,
    letterSpacing: '0.01em',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    transition: 'opacity 0.15s ease, transform 0.1s ease',
    boxShadow: '0 4px 16px rgba(168,85,247,0.35)',
  },
  spinner: {
    display: 'inline-block',
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff',
    borderRadius: '50%',
    animation: 'sh-spin 0.7s linear infinite',
    flexShrink: 0,
  },
  dropZone: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '160px',
    border: '2px dashed',
    borderRadius: '12px',
    transition: 'border-color 0.15s ease, background-color 0.15s ease',
    padding: 'var(--space-5)',
  },
  dropContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '10px',
    textAlign: 'center' as const,
  },
  dropHintMain: {
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-secondary)',
  },
  dropHintSub: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
  },
  fileInfo: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
    textAlign: 'center' as const,
  },
  fileName: {
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    maxWidth: '280px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  fileMeta: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
  errorText: {
    fontSize: 'var(--text-xs)',
    color: 'var(--status-error)',
    paddingLeft: '2px',
  },
  platforms: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    alignItems: 'center',
    gap: '6px',
  },
  platformsLabel: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    marginRight: '2px',
  },
  platformChip: {
    height: '20px',
    padding: '0 8px',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '6px',
    fontSize: '10px',
    fontWeight: 500,
    color: 'var(--text-tertiary)',
    display: 'inline-flex',
    alignItems: 'center',
    letterSpacing: '0.02em',
  },
}
