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
  // Extended from HistoryItem for richer log display
  createdAt?: string
  outputDir?: string | null
  canOpenFolder?: boolean
  completedCount?: number
  failedCount?: number
  totalCount?: number
  summaryText?: string
  kind?: 'render' | 'download'
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
