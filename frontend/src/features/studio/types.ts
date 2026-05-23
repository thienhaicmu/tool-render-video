export type RenderJobState =
  | 'queued'
  | 'preparing'
  | 'rendering'
  | 'reviewing'
  | 'completed'
  | 'failed'

export interface RenderJobData {
  jobId: string
  title: string
  state: RenderJobState
  progress?: number
  stage?: string
  eta?: string
  platform?: string
}
