/**
 * Local types for the jobs/history feature module.
 */

export type StatusFilter = 'all' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface JobActionState {
  loading: boolean
  error: string | null
}
