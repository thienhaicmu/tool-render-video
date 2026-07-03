/**
 * PreviewHarness — dev-only component gallery (WP0.4).
 *
 * Mounted ONLY in dev via `?preview=<name>` (see main.tsx). Never shipped in
 * the production bundle (guarded by import.meta.env.DEV). Lets us eyeball a
 * component in every state — including states that are hard to reach in a
 * live render (waiting / failed clips) — before wiring it into the flow.
 */
import React, { useState } from 'react'
import { ScoreRing } from '@/components/ui/ScoreRing'
import { ConicRing } from '@/components/ui/ConicRing'
import { Toggle } from '@/components/ui/Toggle'
import { IconFilm, IconScissors, IconCaptions, IconCheck, IconSpark } from '@/components/icons'
import { ClipTile } from '@/features/clip-studio/render/steps/ClipTile'
import type { ClipSlot } from '@/features/clip-studio/render/types'
import type { Strings } from '@/features/clip-studio/render/i18n'
import '@/features/clip-studio/render/RenderWorkflow.css'

function Row({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ font: '600 12px var(--font-ui)', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 12 }}>{title}</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'center' }}>{children}</div>
    </section>
  )
}

function ScoreRingCase() {
  return (
    <Row title="ScoreRing (quality score · tone by threshold)">
      {[92, 78, 61, 44, 20].map((v) => (
        <div key={v} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
          <ScoreRing value={v} size={68} />
          <span style={{ font: '11px var(--font-ui)', color: 'var(--text-tertiary)' }}>{v}</span>
        </div>
      ))}
      <ScoreRing value={87} size={34} />
    </Row>
  )
}

function ConicRingCase() {
  return (
    <Row title="ConicRing (live progress · accent gradient)">
      {[0, 18, 45, 72, 100].map((v) => (
        <ConicRing key={v} progress={v} size={72} />
      ))}
      <ConicRing progress={64} size={56}><IconFilm size={18} /></ConicRing>
    </Row>
  )
}

function IconCase() {
  const icons = [
    ['Film', IconFilm], ['Scissors', IconScissors], ['Captions', IconCaptions],
    ['Check', IconCheck], ['Spark', IconSpark],
  ] as const
  return (
    <Row title="Icons (WP0.2)">
      {icons.map(([name, Ico]) => (
        <div key={name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, color: 'var(--text-primary)' }}>
          <Ico size={22} />
          <span style={{ font: '11px var(--font-ui)', color: 'var(--text-tertiary)' }}>{name}</span>
        </div>
      ))}
    </Row>
  )
}

// WP1 — the ClipTile states. jobId is a stub so the "done" branch renders its
// layout (the thumbnail 404s offline and hides itself, which is fine — the
// chip / duration / play overlay still demonstrate the composition).
const MOCK_SLOTS: ClipSlot[] = [
  { part_no: 1, status: 'done',         progress_percent: 100, duration: 42 },
  { part_no: 2, status: 'done',         progress_percent: 100, duration: 55 },
  { part_no: 3, status: 'rendering',    progress_percent: 72 },
  { part_no: 4, status: 'cutting',      progress_percent: 20 },
  { part_no: 5, status: 'transcribing', progress_percent: 48 },
  { part_no: 6, status: 'waiting',      progress_percent: 0 },
  { part_no: 7, status: 'failed',       progress_percent: 0, message: 'ffmpeg exited with code 1' },
]

function ClipTileCase() {
  const [focus, setFocus] = useState<number>(3)
  const t = {} as unknown as Strings
  const statusLabel = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
  const ratios: Array<[string, string]> = [['9:16', '9 / 16'], ['16:9', '16 / 9']]
  return (
    <>
      {ratios.map(([label, ratio]) => (
        <Row key={label} title={`ClipTile grid · ${label} (click to focus)`}>
          <div className="ct-grid" style={{ width: '100%' }}>
            {MOCK_SLOTS.map((s) => (
              <ClipTile
                key={s.part_no}
                slot={s}
                jobId="preview-job"
                thumbRatio={ratio}
                isFocus={s.part_no === focus}
                onFocus={setFocus}
                t={t}
                getStatusLabel={statusLabel}
              />
            ))}
          </div>
        </Row>
      ))}
    </>
  )
}

function ToggleCase() {
  const [a, setA] = useState(true)
  const [b, setB] = useState(false)
  return (
    <Row title="Toggle (accessible switch)">
      <Toggle checked={a} onChange={setA} label="on" />
      <Toggle checked={b} onChange={setB} label="off" />
      <Toggle checked disabled onChange={() => {}} label="disabled on" />
      <Toggle checked={false} disabled onChange={() => {}} label="disabled off" />
    </Row>
  )
}

const CASES: Record<string, React.ComponentType> = {
  primitives: () => (<><ScoreRingCase /><ConicRingCase /><ToggleCase /><IconCase /></>),
  scorering: ScoreRingCase,
  conicring: ConicRingCase,
  toggle: ToggleCase,
  icons: IconCase,
  cliptile: ClipTileCase,
}

export function PreviewHarness({ name }: { name: string }) {
  const Case = CASES[name] ?? CASES.primitives
  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-base)', color: 'var(--text-primary)', padding: 40, fontFamily: 'var(--font-ui)' }}>
      <div style={{ font: '700 20px var(--font-display)', marginBottom: 6 }}>Preview · {name in CASES ? name : 'primitives'}</div>
      <div style={{ font: '12px var(--font-ui)', color: 'var(--text-tertiary)', marginBottom: 28 }}>
        Available: {Object.keys(CASES).map((k) => `?preview=${k}`).join('  ·  ')}
      </div>
      <Case />
    </div>
  )
}
