import { useEffect, useRef, useState } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { StepStrip } from './components/StepStrip'
import { WorkflowPanel } from './components/WorkflowPanel'
import { PreviewWorkspace } from './components/PreviewWorkspace'
import { BottomRenderState } from './components/BottomRenderState'
import { getPreviewVideoUrl } from '../../api/render'

export function StudioScreen() {
  const studioStep    = useUIStore((s) => s.studioStep)
  const setStudioStep = useUIStore((s) => s.setStudioStep)
  const hasInitialized = useRef(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState<string>('')
  const [sessionDuration, setSessionDuration] = useState<number>(0)
  const [sessionSourceMode, setSessionSourceMode] = useState<'youtube' | 'local'>('youtube')
  const [sessionOutputDir, setSessionOutputDir] = useState<string>('')
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

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - var(--topbar-height))',
        overflow: 'hidden',
      }}
    >
      {/* Step strip */}
      <StepStrip
        currentStep={studioStep}
        onStepClick={setStudioStep}
      />

      {/* Middle body: PreviewWorkspace (left, flex) + WorkflowPanel (right, fixed) */}
      <div
        style={{
          display: 'flex',
          flex: 1,
          overflow: 'hidden',
          minHeight: 0,
        }}
      >
        <PreviewWorkspace studioStep={studioStep} mediaUrl={mediaUrl} />
        <WorkflowPanel
          studioStep={studioStep}
          sessionId={sessionId}
          onSessionReady={handleSessionReady}
          sessionTitle={sessionTitle}
          sessionDuration={sessionDuration}
          sessionSourceMode={sessionSourceMode}
          sessionOutputDir={sessionOutputDir}
        />
      </div>

      {/* Bottom render state */}
      <BottomRenderState />
    </div>
  )
}
