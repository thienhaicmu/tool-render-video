/**
 * QualityLoadingState — compact skeleton placeholder for quality panel.
 */
import './QualityPanel.css'

export function QualityLoadingState() {
  return (
    <div className="quality-loading" data-testid="quality-loading">
      <div className="quality-loading-row" style={{ width: '60%' }} />
      <div className="quality-loading-row" style={{ width: '100%' }} />
      <div className="quality-loading-row" style={{ width: '80%' }} />
    </div>
  )
}
