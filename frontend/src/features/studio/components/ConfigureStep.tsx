import React, { useState } from 'react'
import { useEditStore } from '../../../stores/editStore'
import type { TargetPlatform, RenderProfile, VideoType, EnergyStyle, HookStrength, FocusMode, TargetMarket } from '../../../stores/editStore'

interface ConfigureStepProps {
  defaultOutputDir?: string
  onContinue: (outputDir: string) => void
}

// ── Primitives ─────────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' as const, color: 'var(--accent-primary)', marginBottom: 10 }}>
      {children}
    </div>
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!value)} aria-pressed={value} style={{
      width: 36, height: 20, borderRadius: 10, border: 'none', flexShrink: 0,
      backgroundColor: value ? '#a855f7' : 'var(--surface-input)',
      position: 'relative', cursor: 'pointer', transition: 'background-color .2s', outline: 'none',
    }}>
      <span style={{
        position: 'absolute', top: 3, left: value ? 18 : 3,
        width: 14, height: 14, borderRadius: '50%', backgroundColor: '#fff',
        transition: 'left .2s', boxShadow: '0 1px 3px rgba(0,0,0,.3)',
      }} />
    </button>
  )
}

function Row({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
      <div>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</span>
        {hint && <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 6 }}>{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function NumberInput({ value, onChange, min, max, step = 1, unit }: {
  value: number; onChange: (v: number) => void; min: number; max: number; step?: number; unit?: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <input
        type="number" value={value} min={min} max={max} step={step}
        onChange={e => {
          const v = parseInt(e.target.value, 10)
          if (!isNaN(v)) onChange(Math.max(min, Math.min(max, v)))
        }}
        style={{
          width: 72, padding: '5px 8px', borderRadius: 6, fontSize: 12,
          border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
          color: 'var(--text-primary)', outline: 'none', textAlign: 'right' as const,
        }}
      />
      {unit && <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{unit}</span>}
    </div>
  )
}

function PathInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string
}) {
  return (
    <input
      value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      style={{
        flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 11,
        border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
        color: 'var(--text-primary)', outline: 'none', minWidth: 0,
      }}
    />
  )
}

function PillGroup<T extends string>({ options, value, onChange }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 5 }}>
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
          border: `1px solid ${value === o.value ? '#a855f7' : 'var(--border-default)'}`,
          backgroundColor: value === o.value ? 'rgba(168,85,247,.15)' : 'transparent',
          color: value === o.value ? '#a855f7' : 'var(--text-secondary)',
          transition: 'all .12s',
        }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Select<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value as T)} style={{
      padding: '5px 8px', borderRadius: 6, fontSize: 11,
      border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
      color: 'var(--text-primary)', cursor: 'pointer', outline: 'none',
    }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

// ── Platform card ──────────────────────────────────────────────────────────────

const PLATFORMS: { value: TargetPlatform; label: string; icon: string; ratio: string }[] = [
  { value: 'tiktok',          label: 'TikTok',    icon: '🎵', ratio: '9:16' },
  { value: 'youtube_shorts',  label: 'YT Shorts', icon: '▶️', ratio: '9:16' },
  { value: 'instagram_reels', label: 'Instagram', icon: '📸', ratio: '9:16' },
]

function PlatformCards({ value, onChange }: { value: TargetPlatform; onChange: (v: TargetPlatform) => void }) {
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      {PLATFORMS.map(p => {
        const active = value === p.value
        return (
          <button key={p.value} onClick={() => onChange(p.value)} style={{
            flex: 1, padding: '10px 8px', borderRadius: 8, cursor: 'pointer',
            border: `1px solid ${active ? '#a855f7' : 'var(--border-default)'}`,
            backgroundColor: active ? 'rgba(168,85,247,.12)' : 'var(--surface-panel)',
            transition: 'all .12s',
          }}>
            <div style={{ fontSize: 18, marginBottom: 4 }}>{p.icon}</div>
            <div style={{ fontSize: 11, fontWeight: 700, color: active ? '#a855f7' : 'var(--text-primary)' }}>{p.label}</div>
            <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 2 }}>{p.ratio}</div>
          </button>
        )
      })}
    </div>
  )
}

// ── Advanced accordion ─────────────────────────────────────────────────────────

function AdvancedSection({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 12 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
          cursor: 'pointer', padding: 0, marginBottom: open ? 16 : 0,
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' as const, color: 'var(--text-tertiary)' }}>
          Advanced
        </span>
        <span style={{
          fontSize: 9, color: 'var(--text-tertiary)',
          transform: open ? 'rotate(180deg)' : 'none',
          transition: 'transform .2s', display: 'inline-block',
        }}>▼</span>
      </button>
      {open && children}
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────

export function ConfigureStep({ defaultOutputDir = '', onContinue }: ConfigureStepProps) {
  const { settings, update, setPlatform } = useEditStore()
  const [localOutputDir, setLocalOutputDir] = useState(settings.outputDir || defaultOutputDir)

  const s = settings
  const canContinue = s.sourceVideoPath.trim() !== '' && localOutputDir.trim() !== ''

  function handleOutputDirChange(v: string) {
    setLocalOutputDir(v)
    update({ outputDir: v })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, height: '100%', overflowY: 'auto' as const }}>
      <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column' as const, gap: 22, maxWidth: 440, width: '100%', margin: '0 auto' }}>

        {/* ── SOURCE ───────────────────────────────────────────────────── */}
        <section>
          <SectionLabel>Source</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const, width: 70, flexShrink: 0 }}>Video file</span>
              <PathInput value={s.sourceVideoPath} onChange={v => update({ sourceVideoPath: v })} placeholder="Path to local video..." />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const, width: 70, flexShrink: 0 }}>Save to</span>
              <PathInput value={localOutputDir} onChange={handleOutputDirChange} placeholder="Output folder..." />
            </div>
          </div>
        </section>

        {/* ── PLATFORM ─────────────────────────────────────────────────── */}
        <section>
          <SectionLabel>Platform</SectionLabel>
          <PlatformCards
            value={s.targetPlatform}
            onChange={v => setPlatform(v)}
          />
        </section>

        {/* ── OUTPUT GOALS ─────────────────────────────────────────────── */}
        <section>
          <SectionLabel>Output</SectionLabel>
          <Row label="Duration" hint="60–350s">
            <NumberInput value={s.targetDuration} onChange={v => update({ targetDuration: v })} min={60} max={350} step={10} unit="sec" />
          </Row>
          <Row label="Videos">
            <NumberInput value={s.outputCount} onChange={v => update({ outputCount: v })} min={1} max={20} unit="clips" />
          </Row>
        </section>

        {/* ── SUBTITLE + NARRATION ─────────────────────────────────────── */}
        <section>
          <SectionLabel>Options</SectionLabel>

          <Row label="Subtitle">
            <Toggle value={s.addSubtitle} onChange={v => update({ addSubtitle: v })} />
          </Row>
          {s.addSubtitle && (
            <div style={{ marginBottom: 10, paddingLeft: 0 }}>
              <PillGroup<string>
                value={s.subtitleStyle}
                onChange={v => update({ subtitleStyle: v })}
                options={[
                  { value: 'tiktok_bounce_v1', label: 'Bounce' },
                  { value: 'karaoke',          label: 'Karaoke' },
                  { value: 'minimal',          label: 'Minimal' },
                ]}
              />
            </div>
          )}

          <Row label="Narration">
            <Toggle value={s.narrationEnabled} onChange={v => update({ narrationEnabled: v })} />
          </Row>
          {s.narrationEnabled && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <PillGroup<string>
                value={s.narrationLanguage}
                onChange={v => update({ narrationLanguage: v })}
                options={[
                  { value: 'vi', label: 'VI' },
                  { value: 'en', label: 'EN' },
                  { value: 'ja', label: 'JA' },
                  { value: 'ko', label: 'KO' },
                ]}
              />
            </div>
          )}
        </section>

        {/* ── ADVANCED ─────────────────────────────────────────────────── */}
        <AdvancedSection>
          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 16 }}>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Output language</div>
              <Select<string>
                value={s.outputLanguage}
                onChange={v => update({ outputLanguage: v })}
                options={[
                  { value: 'auto', label: 'Auto (keep original)' },
                  { value: 'vi',   label: 'Vietnamese' },
                  { value: 'en',   label: 'English' },
                  { value: 'ja',   label: 'Japanese' },
                  { value: 'ko',   label: 'Korean' },
                  { value: 'zh',   label: 'Chinese' },
                ]}
              />
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Target market</div>
              <PillGroup<TargetMarket>
                value={s.targetMarket}
                onChange={v => update({ targetMarket: v })}
                options={[
                  { value: 'US',  label: 'US' },
                  { value: 'VN',  label: 'VN' },
                  { value: 'JP',  label: 'JP' },
                  { value: 'KR',  label: 'KR' },
                  { value: 'EU',  label: 'EU' },
                  { value: 'SEA', label: 'SEA' },
                ]}
              />
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Video type</div>
              <PillGroup<VideoType>
                value={s.videoType}
                onChange={v => update({ videoType: v })}
                options={[
                  { value: 'auto',           label: 'Auto' },
                  { value: 'viral',          label: 'Viral' },
                  { value: 'storytelling',   label: 'Story' },
                  { value: 'educational',    label: 'Edu' },
                  { value: 'emotional',      label: 'Emotional' },
                  { value: 'high_retention', label: 'Retention' },
                ]}
              />
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>AI style</div>
              <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
                <Row label="Energy">
                  <PillGroup<EnergyStyle>
                    value={s.energyStyle}
                    onChange={v => update({ energyStyle: v })}
                    options={[
                      { value: 'auto',     label: 'Auto' },
                      { value: 'fast',     label: 'Fast' },
                      { value: 'balanced', label: 'Balanced' },
                      { value: 'slow',     label: 'Slow' },
                    ]}
                  />
                </Row>
                <Row label="Hook">
                  <PillGroup<HookStrength>
                    value={s.hookStrength}
                    onChange={v => update({ hookStrength: v })}
                    options={[
                      { value: 'aggressive', label: 'Aggressive' },
                      { value: 'balanced',   label: 'Balanced' },
                      { value: 'soft',       label: 'Soft' },
                    ]}
                  />
                </Row>
                <Row label="Focus">
                  <PillGroup<FocusMode>
                    value={s.focusMode}
                    onChange={v => update({ focusMode: v })}
                    options={[
                      { value: 'auto',   label: 'Auto' },
                      { value: 'face',   label: 'Face' },
                      { value: 'object', label: 'Object' },
                      { value: 'center', label: 'Center' },
                    ]}
                  />
                </Row>
              </div>
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Render quality</div>
              <PillGroup<RenderProfile>
                value={s.renderProfile}
                onChange={v => update({ renderProfile: v })}
                options={[
                  { value: 'fast',     label: 'Fast' },
                  { value: 'balanced', label: 'Balanced' },
                  { value: 'quality',  label: 'Quality' },
                  { value: 'best',     label: 'Best' },
                ]}
              />
            </div>

          </div>
        </AdvancedSection>

        {/* ── CTA ──────────────────────────────────────────────────────── */}
        <div style={{ paddingBottom: 20 }}>
          <button
            onClick={() => canContinue && onContinue(localOutputDir)}
            disabled={!canContinue}
            style={{
              width: '100%', padding: '12px 0', borderRadius: 10, border: 'none',
              fontSize: 13, fontWeight: 700, cursor: canContinue ? 'pointer' : 'not-allowed',
              background: canContinue
                ? 'linear-gradient(135deg,#a855f7,#4d7cff)'
                : 'var(--surface-input)',
              color: canContinue ? '#fff' : 'var(--text-tertiary)',
              transition: 'opacity .15s',
            }}
          >
            {canContinue ? 'Start Render' : 'Select a video to continue'}
          </button>
        </div>

      </div>
    </div>
  )
}
