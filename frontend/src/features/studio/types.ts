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

export type ReviewCardStatus = 'pending' | 'approved' | 'rejected'

export interface ReviewCardData {
  id: string
  title: string
  confidence: number
  reasoning: string
  impact: string
  previewTag: string
  clipLabel: string
  status?: ReviewCardStatus
}
