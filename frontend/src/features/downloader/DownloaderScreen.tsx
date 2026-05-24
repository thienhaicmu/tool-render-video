import { useState, useEffect, useRef } from 'react'
import { createDownloadBatch, retryDownloadItems } from '../../api/download'
import { getJobParts } from '../../api/jobs'
import { useI18n } from '../../i18n/useI18n'
import type { JobPart } from '../../types/api'

type PartStatus = JobPart['status'] | 'done' | 'failed' | 'downloading' | 'waiting' | 'unsupported'

interface TrackItem {
  part_no: number
  url: string
  status: PartStatus
  progress: number
  output_file: string
  message: string
}

const POLL_INTERVAL_MS = 1800
const TERMINAL_PART_STATUSES = new Set(['done', 'failed', 'unsupported'])

function isJobTerminal(parts: TrackItem[]): boolean {
  return parts.length > 0 && parts.every((p) => TERMINAL_PART_STATUSES.has(p.status as string))
}

function statusColor(status: PartStatus): string {
  if (status === 'done') return 'var(--status-success)'
  if (status === 'failed' || status === 'unsupported') return 'var(--status-error)'
  if (status === 'downloading') return 'var(--accent-primary)'
  return 'var(--text-tertiary)'
}

export function DownloaderScreen() {
  const { t } = useI18n()
  const [urlInput, setUrlInput] = useState('')
  const [outputDir, setOutputDir] = useState('downloads')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [tracks, setTracks] = useState<TrackItem[]>([])
  const [done, setDone] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return
    setDone(false)
    const poll = async () => {
      try {
        const parts = await getJobParts(jobId)
        const mapped: TrackItem[] = parts.map((p) => ({
          part_no: p.part_no,
          url: p.output_file || '',
          status: p.status as PartStatus,
          progress: p.progress_percent,
          output_file: p.output_file || '',
          message: (p as any).message || '',
        }))
        setTracks(mapped)
        if (isJobTerminal(mapped)) {
          setDone(true)
          if (pollRef.current) clearInterval(pollRef.current)
        }
      } catch { /* silent — keep polling */ }
    }
    poll()
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [jobId])

  const parseUrls = (raw: string): string[] =>
    raw.split(/[\n,]+/).map((u) => u.trim()).filter(Boolean)

  const pickOutputDir = async () => {
    const api = (window as any).electronAPI
    if (!api?.pickOutputDir) return
    const picked: string | null = await api.pickOutputDir()
    if (picked) setOutputDir(picked)
  }

  const openFolder = async () => {
    const api = (window as any).electronAPI
    if (!api?.openPath || !outputDir.trim()) return
    await api.openPath(outputDir.trim())
  }

  const handleSubmit = async () => {
    const urls = parseUrls(urlInput)
    if (urls.length === 0) { setSubmitError(t('dl_error_no_urls')); return }
    if (!outputDir.trim()) { setSubmitError(t('dl_error_no_folder')); return }
    setSubmitting(true)
    setSubmitError(null)
    setJobId(null)
    setTracks([])
    setDone(false)
    try {
      const res = await createDownloadBatch(urls, outputDir.trim())
      setTracks(res.items.map((item) => ({
        part_no: item.part_no,
        url: item.url,
        status: 'waiting' as PartStatus,
        progress: 0,
        output_file: '',
        message: 'Queued',
      })))
      setJobId(res.job_id)
    } catch (err: any) {
      setSubmitError(err?.detail || err?.message || 'Download failed — check the URLs and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRetryFailed = async () => {
    if (!jobId) return
    const failedNos = tracks.filter((t) => t.status === 'failed').map((t) => t.part_no)
    if (failedNos.length === 0) return
    try {
      await retryDownloadItems(jobId, failedNos)
      setDone(false)
      setTracks((prev) => prev.map((tr) => failedNos.includes(tr.part_no)
        ? { ...tr, status: 'waiting', progress: 0, message: 'Retrying' }
        : tr,
      ))
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const parts = await getJobParts(jobId)
          const mapped: TrackItem[] = parts.map((p) => ({
            part_no: p.part_no,
            url: p.output_file || '',
            status: p.status as PartStatus,
            progress: p.progress_percent,
            output_file: p.output_file || '',
            message: (p as any).message || '',
          }))
          setTracks(mapped)
          if (isJobTerminal(mapped)) {
            setDone(true)
            if (pollRef.current) clearInterval(pollRef.current)
          }
        } catch { /* silent */ }
      }, POLL_INTERVAL_MS)
    } catch (err: any) {
      setSubmitError(err?.detail || 'Retry failed.')
    }
  }

  function statusLabel(status: PartStatus): string {
    if (status === 'done') return t('dl_status_saved')
    if (status === 'failed') return t('dl_status_failed')
    if (status === 'unsupported') return t('dl_status_unsupported')
    if (status === 'downloading') return t('dl_status_downloading')
    if (status === 'waiting') return t('dl_status_waiting')
    return status
  }

  const failedCount = tracks.filter((tr) => tr.status === 'failed').length
  const doneCount = tracks.filter((tr) => tr.status === 'done').length
  const totalCount = tracks.length

  return (
    <div style={styles.page}>
      <div style={styles.inner}>
        {/* Header */}
        <div style={styles.header}>
          <h1 style={styles.title}>{t('dl_title')}</h1>
          <p style={styles.subtitle}>{t('dl_subtitle')}</p>
        </div>

        {/* Input card */}
        <div style={styles.card}>
          <label style={styles.label}>{t('dl_label_urls')}</label>
          <textarea
            placeholder={'https://www.youtube.com/watch?v=...\nhttps://www.tiktok.com/...'}
            value={urlInput}
            onChange={(e) => { setUrlInput(e.target.value); setSubmitError(null) }}
            disabled={submitting}
            rows={4}
            style={{
              ...styles.textarea,
              borderColor: submitError ? 'var(--status-error)' : 'var(--border-default)',
            }}
          />
          <span style={styles.hintText}>{t('dl_url_hint')}</span>

          <label style={{ ...styles.label, marginTop: 'var(--space-3)' }}>{t('dl_label_save')}</label>
          <div style={styles.folderRow}>
            <input
              type="text"
              value={outputDir}
              onChange={(e) => { setOutputDir(e.target.value); setSubmitError(null) }}
              placeholder={t('dl_folder_placeholder')}
              disabled={submitting}
              style={styles.folderInput}
            />
            <button onClick={pickOutputDir} disabled={submitting} style={styles.browseBtn} title="Browse folder">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
              <span style={{ fontSize: '11px' }}>{t('dl_btn_browse')}</span>
            </button>
          </div>
          <span style={styles.hintText}>{t('dl_folder_hint')}</span>

          {submitError && <div style={styles.errorBox}>{submitError}</div>}

          <button
            onClick={handleSubmit}
            disabled={submitting || !urlInput.trim()}
            style={{
              ...styles.submitBtn,
              opacity: submitting || !urlInput.trim() ? 0.5 : 1,
              cursor: submitting || !urlInput.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? t('dl_btn_starting') : `⬇ ${t('dl_btn_start')}`}
          </button>
        </div>

        {/* Progress */}
        {tracks.length > 0 && (
          <div style={styles.card}>
            <div style={styles.progressHeader}>
              <span style={styles.progressTitle}>
                {done
                  ? `${t('dl_progress_done')} — ${doneCount}/${totalCount}`
                  : `${t('dl_progress_downloading')} — ${doneCount}/${totalCount}`}
              </span>
              <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                {done && failedCount > 0 && (
                  <button onClick={handleRetryFailed} style={styles.retryBtn}>
                    ↺ {t('dl_retry')} {failedCount}
                  </button>
                )}
                {done && doneCount > 0 && (
                  <button onClick={openFolder} style={styles.openBtn}>
                    📂 {t('dl_btn_open')}
                  </button>
                )}
              </div>
            </div>

            <div style={styles.trackList}>
              {tracks.map((track, i) => {
                const rawUrl = parseUrls(urlInput)[i] ?? track.url
                const displayUrl = rawUrl.length > 60 ? rawUrl.slice(0, 57) + '…' : rawUrl
                const color = statusColor(track.status)
                const pct = track.status === 'done' ? 100 : track.progress

                return (
                  <div key={track.part_no} style={styles.trackRow}>
                    <div style={styles.trackTop}>
                      <span style={styles.trackUrl}>{displayUrl}</span>
                      <span style={{ ...styles.trackStatus, color }}>
                        {statusLabel(track.status)}
                      </span>
                    </div>
                    {track.message && track.status !== 'done' && (
                      <span style={styles.trackMsg}>{track.message}</span>
                    )}
                    <div style={styles.progressTrack}>
                      <div style={{ ...styles.progressFill, width: `${pct}%`, backgroundColor: color, transition: 'width 0.4s ease-out' }} />
                    </div>
                    <div style={styles.trackBottom}>
                      <span style={styles.trackPct}>{pct}%</span>
                      {track.status === 'done' && track.output_file && (
                        <span style={styles.savedPath}>
                          ✓ {track.output_file.split(/[/\\]/).slice(-2).join('/')}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {done && (
          <button
            onClick={() => { setUrlInput(''); setTracks([]); setJobId(null); setDone(false); setSubmitError(null) }}
            style={styles.newDownloadBtn}
          >
            {t('dl_btn_new')}
          </button>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    overflowY: 'auto',
    backgroundColor: 'var(--surface-base)',
    padding: 'var(--space-8) var(--space-6)',
  },
  inner: {
    maxWidth: '640px',
    margin: '0 auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
  },
  header: { display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' },
  title: {
    margin: 0,
    fontSize: 'var(--text-2xl)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    color: 'var(--text-primary)',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    margin: 0,
    fontSize: 'var(--text-base)',
    color: 'var(--text-secondary)',
  },
  card: {
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-default)',
    borderRadius: '12px',
    padding: 'var(--space-5)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  label: {
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--weight-medium)' as unknown as number,
    color: 'var(--text-secondary)',
  },
  textarea: {
    width: '100%',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: '8px',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-sm)',
    fontFamily: 'var(--font-mono)',
    padding: 'var(--space-3)',
    resize: 'vertical' as const,
    outline: 'none',
    boxSizing: 'border-box' as const,
    lineHeight: 1.6,
  },
  folderRow: {
    display: 'flex',
    gap: 'var(--space-2)',
    alignItems: 'stretch',
  },
  folderInput: {
    flex: 1,
    height: '38px',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: '8px',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-sm)',
    fontFamily: 'var(--font-mono)',
    padding: '0 var(--space-3)',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  browseBtn: {
    height: '38px',
    padding: '0 var(--space-3)',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: '8px',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    transition: 'background-color 0.15s ease',
    whiteSpace: 'nowrap' as const,
  },
  hintText: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
  },
  errorBox: {
    padding: 'var(--space-2) var(--space-3)',
    borderRadius: '6px',
    backgroundColor: 'var(--status-error-bg)',
    color: 'var(--status-error)',
    fontSize: 'var(--text-sm)',
    border: '1px solid rgba(224, 82, 82, 0.3)',
  },
  submitBtn: {
    marginTop: 'var(--space-2)',
    height: '44px',
    border: 'none',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-base)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    cursor: 'pointer',
    transition: 'opacity 0.15s ease',
    letterSpacing: '0.01em',
  },
  progressHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 'var(--space-1)',
    flexWrap: 'wrap' as const,
    gap: 'var(--space-2)',
  },
  progressTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    color: 'var(--text-primary)',
  },
  retryBtn: {
    height: '28px',
    padding: '0 var(--space-3)',
    border: '1px solid var(--status-error)',
    borderRadius: '6px',
    backgroundColor: 'var(--status-error-bg)',
    color: 'var(--status-error)',
    fontSize: 'var(--text-xs)',
    fontWeight: 'var(--weight-medium)' as unknown as number,
    cursor: 'pointer',
  },
  openBtn: {
    height: '28px',
    padding: '0 var(--space-3)',
    border: '1px solid var(--border-default)',
    borderRadius: '6px',
    backgroundColor: 'var(--surface-panel)',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-xs)',
    fontWeight: 'var(--weight-medium)' as unknown as number,
    cursor: 'pointer',
  },
  trackList: { display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' },
  trackRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: 'var(--space-3)',
    backgroundColor: 'var(--surface-panel)',
    borderRadius: '8px',
    border: '1px solid var(--border-subtle)',
  },
  trackTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-2)' },
  trackUrl: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    flex: 1,
  },
  trackStatus: { fontSize: 'var(--text-xs)', fontWeight: 'var(--weight-medium)' as unknown as number, flexShrink: 0 },
  trackMsg: { fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' },
  progressTrack: { width: '100%', height: '4px', backgroundColor: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden', marginTop: '2px' },
  progressFill: { height: '100%', borderRadius: '2px' },
  trackBottom: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  trackPct: { fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' },
  savedPath: { fontSize: 'var(--text-xs)', color: 'var(--status-success)', fontFamily: 'var(--font-mono)', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  newDownloadBtn: {
    alignSelf: 'center',
    height: '36px',
    padding: '0 var(--space-5)',
    border: '1px solid var(--border-default)',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-sm)',
    cursor: 'pointer',
  },
}
