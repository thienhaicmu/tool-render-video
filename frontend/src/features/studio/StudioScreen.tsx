import { useEffect, useRef, useState } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { StepNav } from './components/StepNav'
import { SourceHero } from './components/SourceHero'
import { AnalyzeStep } from './components/AnalyzeStep'
import { PlanStep } from './components/PlanStep'
import { EditStep } from './components/EditStep'
import { ReviewStep } from './components/ReviewStep'
import { RenderStep } from './components/RenderStep'
import { MonitorStep } from './components/MonitorStep'
import { ResultsStep } from './components/ResultsStep'
import { PreviewWorkspace } from './components/PreviewWorkspace'
import { getPreviewVideoUrl } from '../../api/render'
import type { AIPlanCardData } from '../../adapters/studioAdapters'

// ── EditSidePanel (inline) ────────────────────────────────────────────────────

interface EditSidePanelProps {
  onBack: () => void
  onContinue: () => void
}

function EditSidePanel({ onBack, onContinue }: EditSidePanelProps) {
  return (
    <div style={ep.panel}>
      {/* Header */}
      <div style={ep.header}>
        <button onClick={onBack} style={ep.backBtn}>← Plan</button>
        <span style={ep.title}>Edit Settings</span>
        <button onClick={onContinue} style={ep.continueBtn}>Continue →</button>
      </div>

      {/* Body: existing EditStep */}
      <div style={ep.body}>
        <EditStep />
      </div>
    </div>
  )
}

const ep: Record<string, React.CSSProperties> = {
  panel: {
    width: 'min(320px, 36vw)',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-panel)',
    borderLeft: '1px solid var(--border-subtle)',
    overflow: 'hidden',
  },
  header: {
    height: '48px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-3)',
    borderBottom: '1px solid var(--border-subtle)',
    gap: 'var(--space-2)',
    flexShrink: 0,
  },
  title: {
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    flex: 1,
    textAlign: 'center' as const,
  },
  backBtn: {
    height: '28px',
    padding: '0 var(--space-2)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-xs)',
    cursor: 'pointer',
    flexShrink: 0,
  },
  continueBtn: {
    height: '28px',
    padding: '0 var(--space-3)',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    background: 'linear-gradient(135deg, #7B61FF 0%, #4D7CFF 100%)',
    color: '#fff',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0,
  },
  body: {
    flex: 1,
    overflow: 'hidden',
    minHeight: 0,
  },
}

// ── StudioHeader ──────────────────────────────────────────────────────────────

interface StudioHeaderProps {
  sessionTitle: string
  onBack: () => void
}

function StudioHeader({ sessionTitle, onBack }: StudioHeaderProps) {
  return (
    <header style={{
      height: '48px',
      flexShrink: 0,
      backgroundColor: 'var(--surface-panel)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 20px',
      gap: '14px',
      boxShadow: '0 1px 0 rgba(255,255,255,0.03)',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', flexShrink: 0 }}>
        <span style={{ fontSize: '15px', background: 'linear-gradient(135deg, #7B61FF, #4D7CFF)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', lineHeight: 1 }}>✦</span>
        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>AI Video Studio</span>
      </div>

      <div style={{ width: '1px', height: '18px', backgroundColor: 'var(--border-subtle)', flexShrink: 0 }} />

      {/* Project breadcrumb */}
      {sessionTitle ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase' as const, letterSpacing: '0.07em', flexShrink: 0 }}>Project</span>
          <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', flexShrink: 0 }}>/</span>
          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{sessionTitle}</span>
        </div>
      ) : (
        <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', flex: 1 }}>New Project</span>
      )}

      {/* Exit */}
      <button
        onClick={onBack}
        style={{
          height: '28px',
          padding: '0 12px',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          backgroundColor: 'transparent',
          color: 'var(--text-tertiary)',
          fontSize: '11px',
          fontWeight: 500,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
          flexShrink: 0,
          transition: 'border-color 0.12s ease, color 0.12s ease',
        }}
      >
        ← Exit
      </button>
    </header>
  )
}

// ── StudioScreen ──────────────────────────────────────────────────────────────

export function StudioScreen() {
  const studioStep = useUIStore((s) => s.studioStep)
  const setStudioStep = useUIStore((s) => s.setStudioStep)
  const hasInitialized = useRef(false)

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState('')
  const [sessionDuration, setSessionDuration] = useState(0)
  const [sessionSourceMode, setSessionSourceMode] = useState<'youtube' | 'local'>('youtube')
  const [sessionOutputDir, setSessionOutputDir] = useState('')
  const [planCards, setPlanCards] = useState<AIPlanCardData[] | null>(null)
  const [renderedJobId, setRenderedJobId] = useState<string | null>(null)

  const mediaUrl = sessionId ? getPreviewVideoUrl(sessionId) : undefined

  const handleSessionReady = (
    id: string,
    title: string,
    duration: number,
    sourceMode: 'youtube' | 'local',
    outputDir: string,
  ) => {
    setSessionId(id)
    setSessionTitle(title)
    setSessionDuration(duration)
    setSessionSourceMode(sourceMode)
    setSessionOutputDir(outputDir)
    setStudioStep('analyze')
  }

  useEffect(() => {
    if (!hasInitialized.current && studioStep === null) {
      hasInitialized.current = true
      setStudioStep('source')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const renderStepContent = () => {
    if (studioStep === null || studioStep === 'source') {
      return <SourceHero onSessionReady={handleSessionReady} />
    }

    if (studioStep === 'analyze') {
      return (
        <AnalyzeStep
          sessionId={sessionId}
          sessionTitle={sessionTitle}
          sessionDuration={sessionDuration}
          onContinue={() => setStudioStep('plan')}
        />
      )
    }

    if (studioStep === 'plan') {
      return (
        <PlanStep
          sessionId={sessionId}
          onCardsLoaded={setPlanCards}
          onContinue={() => setStudioStep('edit')}
        />
      )
    }

    if (studioStep === 'edit') {
      return (
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
          <PreviewWorkspace studioStep="edit" mediaUrl={mediaUrl} />
          <EditSidePanel
            onBack={() => setStudioStep('plan')}
            onContinue={() => setStudioStep('review')}
          />
        </div>
      )
    }

    if (studioStep === 'review') {
      return (
        <ReviewStep
          planCards={planCards}
          onContinue={() => setStudioStep('render')}
        />
      )
    }

    if (studioStep === 'render') {
      return (
        <RenderStep
          sessionId={sessionId}
          sessionDuration={sessionDuration}
          sessionSourceMode={sessionSourceMode}
          sessionOutputDir={sessionOutputDir}
          onRenderStarted={(jobId) => {
            setRenderedJobId(jobId)
            setStudioStep('monitor')
          }}
        />
      )
    }

    if (studioStep === 'monitor') {
      return (
        <MonitorStep
          jobId={renderedJobId}
          onComplete={() => setStudioStep('results')}
        />
      )
    }

    if (studioStep === 'results') {
      return (
        <ResultsStep
          jobId={renderedJobId}
          sessionOutputDir={sessionOutputDir}
          onNewProject={() => {
            setSessionId(null)
            setStudioStep('source')
          }}
        />
      )
    }

    return null
  }

  const setActivePanel = useUIStore((s) => s.setActivePanel)

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        backgroundColor: 'var(--surface-base)',
      }}
    >
      <StudioHeader
        sessionTitle={sessionTitle}
        onBack={() => setActivePanel('home')}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <StepNav currentStep={studioStep} onStepClick={setStudioStep} />
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {renderStepContent()}
        </div>
      </div>
    </div>
  )
}
