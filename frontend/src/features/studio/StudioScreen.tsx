import { useEffect, useRef, useState } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { StepNav } from './components/StepNav'
import { SourceHero } from './components/SourceHero'
import { ConfigureStep } from './components/ConfigureStep'
import { AnalyzeStep } from './components/AnalyzeStep'
import { PlanStep } from './components/PlanStep'
import { MonitorStep } from './components/MonitorStep'
import { ResultsStep } from './components/ResultsStep'

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
        <span style={{ fontSize: '15px', background: 'linear-gradient(135deg, #a855f7, #4d7cff)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', lineHeight: 1 }}>✦</span>
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
          height: '34px',
          padding: '0 14px',
          border: '1px solid var(--border-default)',
          borderRadius: '8px',
          backgroundColor: 'transparent',
          color: 'var(--text-secondary)',
          fontSize: '12px',
          fontWeight: 700,
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
  const setActivePanel = useUIStore((s) => s.setActivePanel)
  const hasInitialized = useRef(false)

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState('')
  const [sessionDuration, setSessionDuration] = useState(0)
  const [sessionSourceMode, setSessionSourceMode] = useState<'youtube' | 'local'>('youtube')
  const [sessionOutputDir, setSessionOutputDir] = useState('')
  const [renderedJobId, setRenderedJobId] = useState<string | null>(null)

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
    setStudioStep('configure')
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

    if (studioStep === 'configure') {
      return (
        <ConfigureStep
          defaultOutputDir={sessionOutputDir}
          onContinue={(outputDir) => {
            setSessionOutputDir(outputDir)
            setStudioStep('analyze')
          }}
        />
      )
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
          sessionSourceMode={sessionSourceMode}
          sessionOutputDir={sessionOutputDir}
          onRenderStarted={(jobId: string) => {
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
