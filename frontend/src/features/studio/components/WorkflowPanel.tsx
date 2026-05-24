/**
 * WorkflowPanel — legacy component, no longer used by StudioScreen.
 * Kept for backward-compat imports. Returns null.
 */
import { type StudioStep } from '../../../stores/uiStore'

export interface WorkflowPanelProps {
  studioStep: StudioStep | null
  sessionId: string | null
  onSessionReady?: (
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

export function WorkflowPanel(_props: WorkflowPanelProps): null {
  return null
}
