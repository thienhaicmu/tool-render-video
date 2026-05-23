/**
 * SummaryCard — sticky right-column card showing a summary of current form state.
 */
import React from 'react'
import { Button } from '../../../components/ui/Button'
import type { RenderFormState } from '../RenderForm.types'

interface SummaryCardProps {
  state: RenderFormState
  isValid: boolean
  isSubmitting: boolean
  onSubmit: () => void
}

export function SummaryCard({ state, isValid, isSubmitting, onSubmit }: SummaryCardProps) {
  return (
    <div style={cardStyle}>
      <h3 style={headingStyle}>Render Summary</h3>

      <dl style={dlStyle}>
        <SummaryRow label="Source" value={state.source_mode === 'youtube' ? 'YouTube' : 'Local File'} />
        <SummaryRow label="Platform" value={state.target_platform} />
        <SummaryRow label="Aspect" value={state.aspect_ratio} />
        <SummaryRow label="Duration" value={`${state.min_part_sec}s – ${state.max_part_sec}s`} />
        <SummaryRow label="Parts" value={String(state.max_export_parts)} />
        <SummaryRow label="Subtitles" value={state.add_subtitle ? 'On' : 'Off'} />
        <SummaryRow label="AI Director" value={state.ai_director_enabled ? 'On' : 'Off'} />
        <SummaryRow label="Effect" value={state.effect_preset} />
        <SummaryRow label="Profile" value={state.render_profile} />
      </dl>

      {!isValid && (
        <p style={validationHintStyle}>
          Fix errors above before submitting
        </p>
      )}

      <Button
        variant="primary"
        size="lg"
        loading={isSubmitting}
        disabled={!isValid || isSubmitting}
        onClick={onSubmit}
        style={{ width: '100%', marginTop: 'var(--space-4)' }}
        data-testid="submit-render-button"
      >
        {isSubmitting ? 'Starting...' : 'Start Render'}
      </Button>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt style={dtStyle}>{label}</dt>
      <dd style={ddStyle}>{value}</dd>
    </>
  )
}

const cardStyle: React.CSSProperties = {
  position: 'sticky',
  top: 'var(--space-6)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)',
  padding: 'var(--space-5)',
}

const headingStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-base)',
  fontWeight: 'var(--font-weight-semibold)' as unknown as number,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-4) 0',
}

const dlStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  gap: '6px var(--space-3)',
  margin: 0,
}

const dtStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  whiteSpace: 'nowrap',
}

const ddStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-primary)',
  margin: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const validationHintStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-error)',
  margin: 'var(--space-3) 0 0 0',
  textAlign: 'center',
}
