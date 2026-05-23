import { useEffect, useState } from 'react'
import { type StudioStep, useUIStore } from '../../../stores/uiStore'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ReviewWorkspace } from './ReviewWorkspace'
import { AnalyzeStep } from './AnalyzeStep'
import { EditStep } from './EditStep'
import { PlanStep } from './PlanStep'
import { RenderStep } from './RenderStep'
import { prepareSource, getPreviewTranscript } from '../../../api/render'
import { uploadFile } from '../../../api/upload'
import { mapSegmentsToPlan } from '../../../adapters/studioAdapters'
import type { AIPlanCardData } from '../../../adapters/studioAdapters'

export interface WorkflowPanelProps {
  studioStep: StudioStep | null
  sessionId: string | null
  onSessionReady: (
    id: string,
    title: string,
    duration: number,
    sourceMode: 'youtube' | 'local',
    outputDir: string,
  ) => void
  sessionTitle?: string
  sessionDuration?: number
  sessionSourceMode?: 'youtube' | 'local'
  sessionOutputDir?: string
}

const STEP_TITLES: Record<StudioStep, string> = {
  source:  'Source Setup',
  analyze: 'AI Analysis',
  plan:    'Plan',
  edit:    'Edit Settings',
  render:  'Render Options',
  review:  'Review',
}


const ALLOWED_VIDEO_EXTENSIONS = new Set([
  'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'm4v', 'ts', 'wmv',
])
const MAX_VIDEO_BYTES = 200 * 1024 * 1024

function validateVideoFile(file: File): string | null {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_VIDEO_EXTENSIONS.has(ext)) {
    return `Unsupported file type ".${ext}". Use MP4, MOV, MKV, AVI, or WebM.`
  }
  if (file.size > MAX_VIDEO_BYTES) {
    return `File too large (${Math.round(file.size / (1024 * 1024))} MB). Maximum is 200 MB.`
  }
  return null
}

export function WorkflowPanel({ studioStep, sessionId, onSessionReady, sessionTitle = '', sessionDuration = 0, sessionSourceMode = 'youtube', sessionOutputDir = '' }: WorkflowPanelProps) {
  const setStudioStep = useUIStore((s) => s.setStudioStep)
  const [urlValue, setUrlValue] = useState('')
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [planCards, setPlanCards] = useState<AIPlanCardData[] | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [sourceMode, setSourceMode] = useState<'youtube' | 'local'>('youtube')
  const [localFile, setLocalFile] = useState<File | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)

  useEffect(() => {
    if (studioStep !== 'plan' || !sessionId) {
      setPlanCards(null)
      setPlanError(null)
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
        setPlanError('Transcript unavailable — showing AI recommendations instead.')
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
      onSessionReady(res.session_id, res.title, res.duration, 'youtube', res.export_dir)
    } catch {
      setSourceError('Unable to prepare source — check the URL and try again.')
    } finally {
      setSourceLoading(false)
    }
  }

  const handleLocalFileSubmit = async () => {
    if (!localFile) return
    const validationError = validateVideoFile(localFile)
    if (validationError) {
      setSourceError(validationError)
      return
    }
    setUploadLoading(true)
    setSourceError(null)
    try {
      const uploaded = await uploadFile(localFile)
      const res = await prepareSource({ source_mode: 'local', source_video_path: uploaded.path })
      onSessionReady(res.session_id, res.title, res.duration, 'local', res.export_dir)
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
        <PlanStep planCards={planCards} planLoading={planLoading} planError={planError} />
      ) : studioStep === 'analyze' ? (
        <AnalyzeStep sessionId={sessionId} sessionTitle={sessionTitle} sessionDuration={sessionDuration} />
      ) : studioStep === 'edit' ? (
        <EditStep />
      ) : studioStep === 'render' ? (
        <RenderStep
          sessionId={sessionId}
          sessionDuration={sessionDuration}
          sessionSourceMode={sessionSourceMode}
          sessionOutputDir={sessionOutputDir}
          onRenderComplete={() => setStudioStep('review')}
        />
      ) : studioStep === 'review' ? (
        <ReviewWorkspace />
      ) : null}
    </div>
  )
}
