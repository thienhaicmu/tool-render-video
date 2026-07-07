/**
 * shared.tsx — presentational bits shared across the Content Studio phases
 * (CM-9 split). Extracted verbatim from the former single-file ContentStudio.tsx.
 */
import React, { useState } from 'react'
import { RATIO_INFO } from '../clip-studio/render/constants'
import type { Ratio } from '../clip-studio/render/types'
import type { ContentScene } from '../../api/content'
import { RATIOS, _CPS, type AuditFlag } from './types'

export function Stepper({ vi, step }: { vi: boolean; step: 1 | 2 | 3 }) {
  const labels = vi ? ['Kịch bản', 'Duyệt kế hoạch', 'Render'] : ['Script', 'Review', 'Render']
  return (
    <div className="cs-stepper">
      {labels.map((l, i) => {
        const n = (i + 1) as 1 | 2 | 3
        const active = n === step
        const done = n < step
        const cls = `cs-step${active ? ' is-active' : ''}${done ? ' is-done' : ''}`
        return (
          <div key={l} className={cls}>
            <span className="cs-step-dot">{done ? '✓' : n}</span>
            {l}{i < 2 && <span className="cs-step-sep">›</span>}
          </div>
        )
      })}
    </div>
  )
}

// V2 Bold — gradient hero header (icon + bold title + subtitle). Shared across
// the Compose / Review / Render screens. Strings are passed in (already i18n'd
// by callers) and all colours come from tokens → dark + light both work.
export function HeroHeader({ icon, title, subtitle }: { icon: string; title: string; subtitle?: React.ReactNode }) {
  return (
    <div className="cs-hero">
      <div className="cs-hero-row">
        <span className="cs-hero-icon" aria-hidden>{icon}</span>
        <div>
          <h1 className="cs-hero-h1">{title}</h1>
          {subtitle != null && <p className="cs-hero-sub">{subtitle}</p>}
        </div>
      </div>
    </div>
  )
}

// V2 Bold — a grouped config section with an icon chip + bold title.
export function SectionCard({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <section className="cs-section">
      <div className="cs-section-hd">
        <span className="cs-section-icon" aria-hidden>{icon}</span>
        <span className="cs-section-title">{title}</span>
      </div>
      {children}
    </section>
  )
}

// V2 Bold — visual aspect-ratio picker (real frames instead of 3 text buttons).
export function RatioPreview({ value, onChange }: { value: Ratio; onChange: (r: Ratio) => void }) {
  return (
    <div className="cs-ratio-row">
      {RATIOS.map((r) => (
        <button key={r} type="button" className={`cs-ratio${value === r ? ' is-on' : ''}`} onClick={() => onChange(r)}>
          <span className={`cs-ratio-frame cs-ratio-frame--${r}`} />
          <span className="cs-ratio-label">{RATIO_INFO[r].label}</span>
        </button>
      ))}
    </div>
  )
}

// V2 Bold — target-duration slider with a live value pill.
export function DurationSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="cs-dur">
      <input className="cs-dur-range" type="range" min={15} max={600} step={5}
        value={value} onChange={(e) => onChange(Math.max(15, Math.min(600, Number(e.target.value) || 90)))} />
      <span className="cs-dur-val">{value}s</span>
    </div>
  )
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cs-field">
      <div className="cs-field-label">{label}</div>
      {children}
    </div>
  )
}

export function PublishField({ vi, label, value, multiline }: {
  vi: boolean; label: string; value: string; multiline?: boolean
}) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }
  return (
    <div className="cs-field">
      <div className="cs-field-label cs-pub-label">
        <span>{label}</span>
        <button className="cs-copy-btn" onClick={copy} disabled={!value}>
          {copied ? (vi ? '✓ Đã copy' : '✓ Copied') : (vi ? 'Copy' : 'Copy')}
        </button>
      </div>
      {multiline
        ? <textarea className="cs-textarea cs-textarea--sm" readOnly value={value} />
        : <input className="cs-input" readOnly value={value} />}
    </div>
  )
}

export function seg(on: boolean): string {
  return `cs-seg${on ? ' is-on' : ''}`
}

// Client-side mirror of the backend narration_audit so the badges stay accurate
// as the user edits narration / speed / duration in Review. Same thresholds as
// ContentPlan.narration_audit (chars vs capacity at ~15 chars/sec × speed).
export function sceneAudit(s: ContentScene): { load: number | null; flag: AuditFlag } {
  const chars = (s.narration || '').trim().length
  const est = s.est_duration_sec ?? 0
  const spd = s.reading_speed ?? 1
  if (est <= 0 || chars <= 0) return { load: null, flag: 'none' }
  const cap = _CPS * spd * est
  const load = cap > 0 ? chars / cap : null
  if (load == null) return { load: null, flag: 'none' }
  if (load > 1.3) return { load, flag: 'overloaded' }
  if (load < 0.6) return { load, flag: 'sparse' }
  return { load, flag: 'ok' }
}
