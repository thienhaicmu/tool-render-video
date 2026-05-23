import { useEffect, useState } from 'react'
import { type StudioStep } from '../../../stores/uiStore'
import { EmptyState } from '../../../components/ui/EmptyState'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { AIPlanCard } from './AIPlanCard'
import { ReviewWorkspace } from './ReviewWorkspace'
import { prepareSource, getPreviewTranscript, type TranscriptSegment } from '../../../api/render'

export interface WorkflowPanelProps {
  studioStep: StudioStep | null
  sessionId: string | null
  onSessionReady: (id: string) => void
}

const STEP_TITLES: Record<StudioStep, string> = {
  source:  'Source Setup',
  analyze: 'AI Analysis',
  plan:    'Plan',
  edit:    'Edit Settings',
  render:  'Render Options',
  review:  'Review',
}

const STEP_SECTIONS: Record<StudioStep, string[]> = {
  source:  ['Source Settings'],
  analyze: ['Analysis Config'],
  plan:    ['Plan Settings', 'Clip Selection'],
  edit:    ['Clip Settings', 'Subtitle', 'Voice', 'AI Assistance', 'Platform'],
  render:  ['Render Options'],
  review:  ['Review Summary'],
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
    confidence: i < total * 0.1 ? 85 : i > total * 0.9 ? 65 : 72,
    reasoning: seg.text,
    impact: `Segment ${i + 1} of ${total}`,
    tags: [`${formatTimecode(seg.start)}–${formatTimecode(seg.end)}`],
  }))
}

export function WorkflowPanel({ studioStep, sessionId, onSessionReady }: WorkflowPanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const [urlValue, setUrlValue] = useState('')
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [planCards, setPlanCards] = useState<ReturnType<typeof mapSegmentsToPlan> | null>(null)
  const [planLoading, setPlanLoading] = useState(false)

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

  const toggleSection = (title: string) => {
    setExpanded((prev) => ({ ...prev, [title]: !prev[title] }))
  }

  const isSectionExpanded = (title: string, index: number) =>
    expanded[title] !== undefined ? expanded[title] : index === 0

  const handleSourceSubmit = async () => {
    if (!urlValue.trim()) return
    setSourceLoading(true)
    setSourceError(null)
    try {
      const res = await prepareSource({ source_mode: 'youtube', youtube_url: urlValue.trim() })
      onSessionReady(res.session_id)
    } catch {
      setSourceError('Unable to prepare source — check the URL and try again.')
    } finally {
      setSourceLoading(false)
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
        /* SOURCE FORM */
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              YouTube Source
            </div>
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
      ) : studioStep === 'review' ? (
        <ReviewWorkspace />
      ) : (
        /* GENERIC SECTIONS for analyze, edit, render */
        <div style={{ flex: 1 }}>
          {STEP_SECTIONS[studioStep].map((section, i) => (
            <div key={section}>
              <SectionHeader
                title={section}
                expanded={isSectionExpanded(section, i)}
                onToggle={() => toggleSection(section)}
              />
              {isSectionExpanded(section, i) && (
                <div
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  Settings for this step are not yet available.
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
