/**
 * TrimControls — two number inputs (start/end in seconds) with validation.
 * UI-only; no backend calls.
 */
import { useState, useEffect } from 'react'
import { Button } from '../../components/ui/Button'
import { formatTime, clamp, validateTrim } from './editor.utils'

export interface TrimControlsProps {
  durationSec: number
  trimStartSec: number
  trimEndSec: number
  isDirty: boolean
  onTrimChange: (start: number, end: number) => void
  onReset: () => void
}

export function TrimControls({
  durationSec,
  trimStartSec,
  trimEndSec,
  isDirty,
  onTrimChange,
  onReset,
}: TrimControlsProps) {
  const [startInput, setStartInput] = useState(String(trimStartSec))
  const [endInput, setEndInput] = useState(String(trimEndSec))
  const [validationError, setValidationError] = useState<string | null>(null)

  // Sync inputs when external state changes (e.g., reset)
  useEffect(() => {
    setStartInput(String(trimStartSec))
  }, [trimStartSec])

  useEffect(() => {
    setEndInput(String(trimEndSec))
  }, [trimEndSec])

  function handleStartChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value
    setStartInput(raw)
    const parsed = parseFloat(raw)
    if (!isNaN(parsed)) {
      // Validate against the raw parsed value first (shows user errors for out-of-range)
      const err = validateTrim(parsed, trimEndSec, durationSec)
      setValidationError(err)
      if (!err) {
        // Only clamp and propagate when valid
        const clamped = clamp(parsed, 0, durationSec > 0 ? durationSec : Infinity)
        onTrimChange(clamped, trimEndSec)
      }
    }
  }

  function handleEndChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value
    setEndInput(raw)
    const parsed = parseFloat(raw)
    if (!isNaN(parsed)) {
      // Validate against the raw parsed value first (shows user errors for out-of-range)
      const err = validateTrim(trimStartSec, parsed, durationSec)
      setValidationError(err)
      if (!err) {
        // Only clamp and propagate when valid
        const clamped = durationSec > 0 ? clamp(parsed, 0, durationSec) : Math.max(0, parsed)
        onTrimChange(trimStartSec, clamped)
      }
    }
  }

  const trimDuration = trimEndSec - trimStartSec

  return (
    <div
      data-testid="trim-controls"
      style={{
        padding: 'var(--space-4)',
        backgroundColor: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
      }}
    >
      <div
        style={{
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-text-secondary)',
          fontWeight: 'var(--font-weight-medium)' as unknown as number,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        Trim
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-start' }}>
        {/* Start */}
        <div style={{ flex: 1 }}>
          <label
            htmlFor="trim-start"
            style={{
              display: 'block',
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-secondary)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Start (sec)
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <input
              id="trim-start"
              data-testid="trim-start-input"
              type="number"
              value={startInput}
              min={0}
              max={durationSec > 0 ? durationSec : undefined}
              step={0.1}
              onChange={handleStartChange}
              style={inputStyle}
            />
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)' }}>
              {formatTime(trimStartSec)}
            </span>
          </div>
        </div>

        {/* End */}
        <div style={{ flex: 1 }}>
          <label
            htmlFor="trim-end"
            style={{
              display: 'block',
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-secondary)',
              marginBottom: 'var(--space-1)',
            }}
          >
            End (sec)
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <input
              id="trim-end"
              data-testid="trim-end-input"
              type="number"
              value={endInput}
              min={0}
              max={durationSec > 0 ? durationSec : undefined}
              step={0.1}
              onChange={handleEndChange}
              style={inputStyle}
            />
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)' }}>
              {formatTime(trimEndSec)}
            </span>
          </div>
        </div>
      </div>

      {/* Trim duration */}
      <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
        Trim duration:{' '}
        <span
          data-testid="trim-duration-display"
          style={{ color: 'var(--color-text-primary)', fontWeight: 'var(--font-weight-medium)' as unknown as number }}
        >
          {formatTime(Math.max(0, trimDuration))}
        </span>
        {durationSec > 0 && (
          <span style={{ marginLeft: 'var(--space-2)', color: 'var(--color-text-secondary)' }}>
            / {formatTime(durationSec)}
          </span>
        )}
      </div>

      {/* Validation error */}
      {validationError && (
        <div
          data-testid="trim-validation-error"
          style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-error)' }}
        >
          {validationError}
        </div>
      )}

      {/* Reset button */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          disabled={!isDirty}
          onClick={onReset}
          data-testid="trim-reset-btn"
        >
          Reset Trim
        </Button>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '80px',
  padding: '4px 8px',
  backgroundColor: 'var(--color-bg-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--color-text-primary)',
  fontSize: 'var(--font-size-sm)',
  fontFamily: 'var(--font-family-mono, monospace)',
}
