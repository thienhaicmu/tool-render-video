/**
 * QualityErrorState — shown when quality fetch fails with a non-404 error.
 */
import { Button } from '@/components/ui/Button'
import './QualityPanel.css'

export interface QualityErrorStateProps {
  error: string
  onRetry: () => void
}

export function QualityErrorState({ error, onRetry }: QualityErrorStateProps) {
  return (
    <div className="quality-error" data-testid="quality-error">
      <div className="quality-error-message">{error}</div>
      <div>
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </div>
  )
}
