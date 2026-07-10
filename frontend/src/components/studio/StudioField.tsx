/**
 * StudioField.tsx — a labelled form field wrapper (label + control + optional
 * hint). Mode-agnostic base; the control is passed as children so any input /
 * textarea / picker can be dropped in. Tokens only.
 */
import React from 'react'

export function StudioField({ label, hint, htmlFor, children }: {
  label?: string
  hint?: React.ReactNode
  htmlFor?: string
  children: React.ReactNode
}) {
  return (
    <div className="st-field">
      {label && <label className="st-field-label" htmlFor={htmlFor}>{label}</label>}
      {children}
      {hint != null && <div className="st-field-hint">{hint}</div>}
    </div>
  )
}
