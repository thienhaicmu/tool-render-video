import React from 'react'
import { useEditStore } from '../../../stores/editStore'
import type { TargetPlatform, RenderProfile, PartOrder } from '../../../stores/editStore'

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={s.section}>
      <div style={s.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      style={{
        width: '38px',
        height: '22px',
        borderRadius: '11px',
        border: 'none',
        backgroundColor: value ? 'var(--accent-primary)' : 'var(--surface-input)',
        position: 'relative',
        cursor: 'pointer',
        transition: 'background-color 0.2s ease',
        flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute',
        top: '3px',
        left: value ? '19px' : '3px',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        backgroundColor: '#fff',
        transition: 'left 0.2s ease',
      }} />
    </button>
  )
}

// ── Segment control (- N +) ────────────────────────────────────────────────────

function Stepper({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <div style={s.stepper}>
      <button
        style={s.stepBtn}
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
      >−</button>
      <span style={s.stepValue}>{value}</span>
      <button
        style={s.stepBtn}
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
      >+</button>
    </div>
  )
}

// ── SegmentedButtons ───────────────────────────────────────────────────────────

function SegButtons<T extends string>({ options, value, onChange }: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div style={s.segButtons}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            ...s.segBtn,
            backgroundColor: value === opt.value ? 'var(--accent-primary)' : 'var(--surface-input)',
            color: value === opt.value ? '#fff' : 'var(--text-secondary)',
            border: value === opt.value ? 'none' : '1px solid var(--border-default)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Row ────────────────────────────────────────────────────────────────────────

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={s.row}>
      <div style={s.rowLeft}>
        <span style={s.rowLabel}>{label}</span>
        {hint && <span style={s.rowHint}>{hint}</span>}
      </div>
      <div style={s.rowRight}>{children}</div>
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────

function Select<T extends string>({ value, options, onChange }: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      style={s.select}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

// ── Platform cards ─────────────────────────────────────────────────────────────

const PLATFORMS: { value: TargetPlatform; label: string; sub: string; icon: string }[] = [
  { value: 'tiktok',          label: 'TikTok',    sub: '9:16 · 30fps', icon: '♪' },
  { value: 'youtube_shorts',  label: 'YT Shorts', sub: '9:16 · 60fps', icon: '▶' },
  { value: 'instagram_reels', label: 'Reels',     sub: '9:16 · 30fps', icon: '◈' },
]

const PROFILES: { value: RenderProfile; label: string; sub: string }[] = [
  { value: 'fast',     label: 'Fast',     sub: '~1 min' },
  { value: 'balanced', label: 'Balanced', sub: 'Recommended' },
  { value: 'quality',  label: 'Quality',  sub: 'Slower' },
  { value: 'best',     label: 'Best',     sub: 'Slowest' },
]

const SUBTITLE_STYLES = [
  { value: 'standard',  label: 'Standard' },
  { value: 'karaoke',   label: 'Karaoke' },
  { value: 'highlight', label: 'Highlight' },
] as const

const PART_ORDERS: { value: PartOrder; label: string }[] = [
  { value: 'viral',      label: 'Viral first' },
  { value: 'sequential', label: 'Sequential' },
]

const VOICE_LANGS = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' },
  { value: 'vi-VN', label: 'Tiếng Việt' },
  { value: 'ja-JP', label: '日本語' },
] as const

// ── EditStep ───────────────────────────────────────────────────────────────────

export function EditStep() {
  const { settings, update, setPlatform } = useEditStore()

  return (
    <div style={s.wrap}>
      {/* Platform */}
      <Section title="Platform">
        <div style={s.platformGrid}>
          {PLATFORMS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPlatform(p.value)}
              style={{
                ...s.platformCard,
                borderColor: settings.targetPlatform === p.value ? 'var(--accent-primary)' : 'var(--border-default)',
                backgroundColor: settings.targetPlatform === p.value ? 'var(--accent-subtle)' : 'var(--surface-input)',
              }}
            >
              <span style={s.platformIcon}>{p.icon}</span>
              <span style={{ ...s.platformLabel, color: settings.targetPlatform === p.value ? 'var(--accent-primary)' : 'var(--text-primary)' }}>
                {p.label}
              </span>
              <span style={s.platformSub}>{p.sub}</span>
            </button>
          ))}
        </div>
      </Section>

      {/* AI & Clips */}
      <Section title="AI & Clips">
        <Row label="AI Director" hint="Auto-select best moments">
          <Toggle value={settings.aiDirectorEnabled} onChange={(v) => update({ aiDirectorEnabled: v })} />
        </Row>
        <Row label="Max clips">
          <Stepper value={settings.maxExportParts} min={1} max={12} onChange={(v) => update({ maxExportParts: v })} />
        </Row>
        <Row label="Sort order">
          <SegButtons<PartOrder>
            options={PART_ORDERS}
            value={settings.partOrder}
            onChange={(v) => update({ partOrder: v })}
          />
        </Row>
        <Row label="Duration" hint="seconds per clip">
          <div style={s.durationRow}>
            <input
              type="number"
              min={10}
              max={settings.maxPartSec - 5}
              value={settings.minPartSec}
              onChange={(e) => update({ minPartSec: Math.max(10, parseInt(e.target.value) || 10) })}
              style={s.numInput}
            />
            <span style={s.durationSep}>–</span>
            <input
              type="number"
              min={settings.minPartSec + 5}
              max={600}
              value={settings.maxPartSec}
              onChange={(e) => update({ maxPartSec: Math.min(600, parseInt(e.target.value) || 90) })}
              style={s.numInput}
            />
            <span style={s.durationUnit}>s</span>
          </div>
        </Row>
      </Section>

      {/* Quality */}
      <Section title="Render Quality">
        <div style={s.profileGrid}>
          {PROFILES.map((p) => (
            <button
              key={p.value}
              onClick={() => update({ renderProfile: p.value })}
              style={{
                ...s.profileCard,
                borderColor: settings.renderProfile === p.value ? 'var(--accent-primary)' : 'var(--border-default)',
                backgroundColor: settings.renderProfile === p.value ? 'var(--accent-subtle)' : 'var(--surface-input)',
              }}
            >
              <span style={{ ...s.profileLabel, color: settings.renderProfile === p.value ? 'var(--accent-primary)' : 'var(--text-primary)' }}>
                {p.label}
              </span>
              <span style={s.profileSub}>{p.sub}</span>
            </button>
          ))}
        </div>
      </Section>

      {/* Subtitles */}
      <Section title="Subtitles">
        <Row label="Enable subtitles">
          <Toggle value={settings.addSubtitle} onChange={(v) => update({ addSubtitle: v })} />
        </Row>
        {settings.addSubtitle && (
          <>
            <Row label="Style">
              <Select
                value={settings.subtitleStyle as any}
                options={SUBTITLE_STYLES as unknown as { value: typeof settings.subtitleStyle; label: string }[]}
                onChange={(v) => update({ subtitleStyle: v })}
              />
            </Row>
            <Row label="Font size">
              <div style={s.durationRow}>
                <input
                  type="range"
                  min={16}
                  max={52}
                  value={settings.subFontSize}
                  onChange={(e) => update({ subFontSize: parseInt(e.target.value) })}
                  style={s.slider}
                />
                <span style={s.sliderValue}>{settings.subFontSize}px</span>
              </div>
            </Row>
            <Row label="Highlight per word">
              <Toggle value={settings.highlightPerWord} onChange={(v) => update({ highlightPerWord: v })} />
            </Row>
          </>
        )}
      </Section>

      {/* Voice */}
      <Section title="Voice Narration">
        <Row label="Enable voice">
          <Toggle value={settings.voiceEnabled} onChange={(v) => update({ voiceEnabled: v })} />
        </Row>
        {settings.voiceEnabled && (
          <>
            <Row label="Language">
              <Select
                value={settings.voiceLanguage}
                options={VOICE_LANGS as unknown as { value: typeof settings.voiceLanguage; label: string }[]}
                onChange={(v) => update({ voiceLanguage: v })}
              />
            </Row>
            <Row label="Gender">
              <SegButtons
                options={[{ value: 'female', label: 'Female' }, { value: 'male', label: 'Male' }]}
                value={settings.voiceGender}
                onChange={(v) => update({ voiceGender: v })}
              />
            </Row>
          </>
        )}
      </Section>
    </div>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  wrap: {
    flex: 1,
    overflowY: 'auto',
    padding: 'var(--space-3) var(--space-4)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  sectionTitle: {
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    color: 'var(--text-tertiary)',
  },
  platformGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '8px',
  },
  platformCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '4px',
    padding: '10px 6px',
    border: '1px solid',
    borderRadius: '10px',
    cursor: 'pointer',
    transition: 'border-color 0.15s ease, background-color 0.15s ease',
  },
  platformIcon: {
    fontSize: '18px',
  },
  platformLabel: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
  },
  platformSub: {
    fontSize: '10px',
    color: 'var(--text-tertiary)',
  },
  profileGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '6px',
  },
  profileCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '3px',
    padding: '8px 4px',
    border: '1px solid',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'border-color 0.15s ease, background-color 0.15s ease',
  },
  profileLabel: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
  },
  profileSub: {
    fontSize: '10px',
    color: 'var(--text-tertiary)',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: '32px',
    gap: 'var(--space-3)',
  },
  rowLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    minWidth: 0,
  },
  rowLabel: {
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  rowHint: {
    fontSize: '10px',
    color: 'var(--text-tertiary)',
  },
  rowRight: {
    flexShrink: 0,
  },
  stepper: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  stepBtn: {
    width: '26px',
    height: '26px',
    border: '1px solid var(--border-default)',
    borderRadius: '6px',
    backgroundColor: 'var(--surface-input)',
    color: 'var(--text-secondary)',
    fontSize: '16px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
  },
  stepValue: {
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    minWidth: '20px',
    textAlign: 'center' as const,
    fontFamily: 'var(--font-mono)',
  },
  segButtons: {
    display: 'flex',
    gap: '4px',
  },
  segBtn: {
    height: '26px',
    padding: '0 var(--space-2)',
    borderRadius: '6px',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background-color 0.15s ease, color 0.15s ease',
    whiteSpace: 'nowrap' as const,
  },
  select: {
    height: '28px',
    padding: '0 var(--space-2)',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: '6px',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-xs)',
    outline: 'none',
    cursor: 'pointer',
  },
  durationRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  numInput: {
    width: '52px',
    height: '28px',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: '6px',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font-mono)',
    padding: '0 var(--space-2)',
    outline: 'none',
    textAlign: 'center' as const,
  },
  durationSep: {
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-xs)',
  },
  durationUnit: {
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-xs)',
  },
  slider: {
    width: '80px',
    accentColor: 'var(--accent-primary)',
  },
  sliderValue: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
    minWidth: '34px',
  },
}
