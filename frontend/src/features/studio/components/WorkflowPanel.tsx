import { useEffect, useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'
import { EmptyState } from '../../../components/ui/EmptyState'
import { AIPlanCard } from './AIPlanCard'
import { ReviewWorkspace } from './ReviewWorkspace'
import { prepareSource, getPreviewTranscript, type TranscriptSegment } from '../../../api/render'
import { uploadFile } from '../../../api/upload'

export interface WorkflowPanelProps {
  studioStep: StudioStep | null
  sessionId: string | null
  onSessionReady: (id: string, title: string, duration: number) => void
  sessionTitle?: string
  sessionDuration?: number
}

const STEP_TITLES: Record<StudioStep, string> = {
  source:  'Source Setup',
  analyze: 'AI Analysis',
  plan:    'Plan',
  edit:    'Edit Settings',
  render:  'Render Options',
  review:  'Review',
}

const SAMPLE_AI_PLAN = [
  {
    title: 'Hook Opening',
    confidence: 87,
    reasoning: 'Hook identified at 0:04. Strong visual cut predicted to retain audience.',
    impact: '+12% watch duration',
    tags: ['hook', '0:04', 'high retention'],
  },
  {
    title: 'Climax Moment',
    confidence: 74,
    reasoning: 'Peak energy moment at 1:32. AI markers indicate high engagement.',
    impact: '+8% completion rate',
    tags: ['climax', '1:32', 'energy peak'],
  },
  {
    title: 'Call-to-Action Close',
    confidence: 61,
    reasoning: 'Strong verbal CTA detected at 3:48. Subtitle density peaks here.',
    impact: '+5% conversion signal',
    tags: ['cta', '3:48', 'verbal'],
  },
]

function formatTimecode(sec: number): string {
  const s = Math.floor(sec)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function mapSegmentsToPlan(segments: TranscriptSegment[]) {
  const limited = segments.slice(0, 5)
  const total = limited.length
  return limited.map((seg, i) => ({
    title: seg.text.trim().slice(0, 40) || `Segment at ${formatTimecode(seg.start)}`,
    confidence: Math.round(85 - (i / Math.max(total - 1, 1)) * 22),
    reasoning: seg.text,
    impact: `Segment ${i + 1} of ${total}`,
    tags: [`${formatTimecode(seg.start)}–${formatTimecode(seg.end)}`],
  }))
}

export function WorkflowPanel({ studioStep, sessionId, onSessionReady, sessionTitle = '', sessionDuration = 0 }: WorkflowPanelProps) {
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const [urlValue, setUrlValue] = useState('')
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [planCards, setPlanCards] = useState<ReturnType<typeof mapSegmentsToPlan> | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [sourceMode, setSourceMode] = useState<'youtube' | 'local'>('youtube')
  const [localFile, setLocalFile] = useState<File | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)

  useEffect(() => {
    if (studioStep !== 'plan' || !sessionId) {
      setPlanCards(null)
      return
    }
    setPlanLoading(true)
    getPreviewTranscript(sessionId)
      .then((res) => {
        const mapped = mapSegmentsToPlan(res.segments)
        setPlanCards(mapped.length > 0 ? mapped : null)
      })
      .catch(() => {
        setPlanCards(null)
      })
      .finally(() => {
        setPlanLoading(false)
      })
  }, [studioStep, sessionId])

  const handleSourceSubmit = async () => {
    if (!urlValue.trim()) return
    setSourceLoading(true)
    setSourceError(null)
    try {
      const res = await prepareSource({ source_mode: 'youtube', youtube_url: urlValue.trim() })
      onSessionReady(res.session_id, res.title, res.duration)
    } catch {
      setSourceError('Unable to prepare source — check the URL and try again.')
    } finally {
      setSourceLoading(false)
    }
  }

  const handleLocalFileSubmit = async () => {
    if (!localFile) return
    setUploadLoading(true)
    setSourceError(null)
    try {
      const uploaded = await uploadFile(localFile)
      const res = await prepareSource({ source_mode: 'local', source_video_path: uploaded.path })
      onSessionReady(res.session_id, res.title, res.duration)
    } catch {
      setSourceError('Unable to prepare source — try again.')
    } finally {
      setUploadLoading(false)
    }
  }

  return (
    <div
      style={{
        width: 'var(--inspector-width)',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--surface-panel)',
        borderLeft: '1px solid var(--border-subtle)',
        overflowY: 'auto',
      }}
    >
      {/* Panel header */}
      <div
        style={{
          height: '40px',
          display: 'flex',
          alignItems: 'center',
          padding: '0 var(--space-4)',
          flexShrink: 0,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-base)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-primary)',
          }}
        >
          {studioStep !== null ? STEP_TITLES[studioStep] : 'Workflow'}
        </span>
      </div>

      {/* Panel body */}
      {studioStep === null ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState
            primary="Select a step to begin"
            secondary="Use the strip above to navigate"
          />
        </div>
      ) : studioStep === 'source' ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {/* Mode tabs */}
            <div style={{ display: 'flex', gap: 'var(--space-4)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 'var(--space-2)' }}>
              {(['youtube', 'local'] as const).map((mode) => (
                <span
                  key={mode}
                  onClick={() => { setSourceMode(mode); setSourceError(null) }}
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: sourceMode === mode ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    fontWeight: sourceMode === mode ? ('var(--weight-medium)' as unknown as number) : ('var(--weight-regular)' as unknown as number),
                    cursor: 'pointer',
                    paddingBottom: 'var(--space-2)',
                    borderBottom: sourceMode === mode ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  }}
                >
                  {mode === 'youtube' ? 'YouTube URL' : 'Local File'}
                </span>
              ))}
            </div>

            {sourceMode === 'youtube' ? (
              <>
                <input
                  type="url"
                  placeholder="Paste YouTube URL…"
                  value={urlValue}
                  disabled={sourceLoading}
                  onChange={(e) => { setUrlValue(e.target.value); setSourceError(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSourceSubmit() }}
                  style={{
                    width: '100%',
                    height: '34px',
                    padding: '0 var(--space-3)',
                    backgroundColor: 'var(--surface-input)',
                    border: `1px solid ${sourceError ? 'var(--status-error)' : 'var(--border-default)'}`,
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--text-sm)',
                    outline: 'none',
                    boxSizing: 'border-box' as const,
                  }}
                />
                {sourceError && (
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--status-error)' }}>
                    {sourceError}
                  </span>
                )}
                <button
                  onClick={handleSourceSubmit}
                  disabled={sourceLoading || !urlValue.trim()}
                  style={{
                    height: '34px',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: sourceLoading || !urlValue.trim() ? 'var(--surface-card)' : 'var(--accent-primary)',
                    color: sourceLoading || !urlValue.trim() ? 'var(--text-tertiary)' : 'var(--text-primary)',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--weight-medium)' as unknown as number,
                    cursor: sourceLoading || !urlValue.trim() ? 'not-allowed' : 'pointer',
                    transition: 'background-color var(--duration-instant) var(--ease-out)',
                  }}
                >
                  {sourceLoading ? 'Preparing…' : 'Prepare Source'}
                </button>
              </>
            ) : (
              <>
                <input
                  type="file"
                  accept="video/*"
                  onChange={(e) => { setLocalFile(e.target.files?.[0] ?? null); setSourceError(null) }}
                  style={{
                    width: '100%',
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'var(--surface-input)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-2) var(--space-3)',
                    boxSizing: 'border-box' as const,
                  }}
                />
                {localFile && (
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                    {localFile.name}
                  </span>
                )}
                {sourceError && (
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--status-error)' }}>
                    {sourceError}
                  </span>
                )}
                <button
                  onClick={handleLocalFileSubmit}
                  disabled={uploadLoading || !localFile}
                  style={{
                    height: '34px',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: uploadLoading || !localFile ? 'var(--surface-card)' : 'var(--accent-primary)',
                    color: uploadLoading || !localFile ? 'var(--text-tertiary)' : 'var(--text-primary)',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--weight-medium)' as unknown as number,
                    cursor: uploadLoading || !localFile ? 'not-allowed' : 'pointer',
                    transition: 'background-color var(--duration-instant) var(--ease-out)',
                  }}
                >
                  {uploadLoading ? 'Uploading…' : 'Prepare Source'}
                </button>
              </>
            )}
          </div>
        </div>
      ) : studioStep === 'plan' ? (
        /* PLAN STEP */
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-3) var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-1)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            AI Recommendations
          </div>
          {planLoading ? (
            /* Skeleton loading */
            [0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  height: '96px',
                  backgroundColor: 'var(--surface-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-lg)',
                  opacity: 0.6,
                }}
              />
            ))
          ) : (planCards ?? SAMPLE_AI_PLAN).map((card, i) => (
            <AIPlanCard
              key={card.title}
              {...card}
              selected={selectedCards.includes(i)}
              onApprove={() =>
                setSelectedCards((prev) =>
                  prev.includes(i) ? prev.filter((j) => j !== i) : [...prev, i]
                )
              }
              onIgnore={() => setSelectedCards((prev) => prev.filter((j) => j !== i))}
            />
          ))}
        </div>
      ) : studioStep === 'analyze' ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
          {sessionId === null ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <EmptyState primary="Source not prepared" secondary="Go back to Source step" />
            </div>
          ) : (
            <div style={{
              backgroundColor: 'var(--surface-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-3)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span style={{ color: 'var(--status-success)', fontSize: 'var(--text-sm)' }}>✓</span>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>
                  {sessionTitle || 'Source prepared'}
                </span>
              </div>
              {sessionDuration > 0 && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                  Duration: {Math.floor(sessionDuration / 60)}m {Math.floor(sessionDuration % 60)}s
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span style={{ color: 'var(--ai-active)', fontSize: 'var(--text-sm)' }}>·</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>Transcript building</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span style={{ color: 'var(--ai-active)', fontSize: 'var(--text-sm)' }}>·</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>AI moments detection</span>
              </div>
            </div>
          )}
        </div>
      ) : studioStep === 'edit' ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
          <div style={{
            backgroundColor: 'var(--surface-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)',
          }}>
            {([
              { label: 'AI clip selection', value: '3 clips selected' },
              { label: 'Subtitles', value: 'Enabled · Pro Karaoke style' },
              { label: 'Format', value: '9:16 Vertical · 60fps' },
              { label: 'Platform', value: 'TikTok optimized' },
            ] as const).map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{label}</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>{value}</span>
              </div>
            ))}
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', paddingTop: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)' }}>
              Adjust settings in Edit options below
            </div>
          </div>
        </div>
      ) : studioStep === 'render' ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
          <div style={{
            backgroundColor: 'var(--surface-card)',
            border: '1px solid var(--status-success-bg)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)',
          }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)' as unknown as number, color: 'var(--status-success)' }}>
              Ready to Render
            </div>
            {([
              { label: 'Platform', value: 'TikTok Vertical' },
              { label: 'Clips', value: '3 clips selected' },
            ] as const).map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{label}</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 'var(--weight-medium)' as unknown as number }}>{value}</span>
              </div>
            ))}
            {sessionDuration > 0 && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                Est. output: ~{Math.max(15, Math.floor(sessionDuration * 0.12))}s total
              </div>
            )}
            <div style={{
              marginTop: 'var(--space-2)',
              height: '34px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--surface-panel)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-tertiary)',
            }}>
              Submit Render →
            </div>
          </div>
        </div>
      ) : studioStep === 'review' ? (
        <ReviewWorkspace />
      ) : null}
    </div>
  )
}
