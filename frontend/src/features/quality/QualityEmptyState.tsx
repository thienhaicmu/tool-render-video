/**
 * QualityEmptyState — shown when no quality report is available (404 or no data).
 */
import './QualityPanel.css'

export function QualityEmptyState() {
  return (
    <div className="quality-empty" data-testid="quality-empty">
      <div>Quality report not available for this job.</div>
      <div style={{ opacity: 0.7 }}>Reports are generated after render completes.</div>
    </div>
  )
}
