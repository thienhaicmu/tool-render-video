import { useState, useEffect } from 'react'
import { submitRender } from '../../../api/render'
import { useI18n } from '../../../i18n/useI18n'
import { useEditStore, type TargetPlatform, type RenderProfile } from '../../../stores/editStore'

interface RenderStepProps {
  sessionId: string | null
  sessionDuration: number
  sessionSourceMode: 'youtube' | 'local'
  sessionOutputDir: string
  onRenderStarted: (jobId: string) => void
}

// ── Format preset definitions ──────────────────────────────────────────────────

interface FormatDef {
  ratio: string
  label: string
  platforms: string[]
  isAIPick?: boolean
  shapeW: number
  shapeH: number
}

const FORMAT_DEFS: FormatDef[] = [
  { ratio: '9:16', label: 'Vertical',  platforms: ['TikTok', 'Reels', 'Shorts'],    isAIPick: true,  shapeW: 36, shapeH: 64 },
  { ratio: '3:4',  label: 'Portrait',  platforms: ['Instagram', 'Pinterest'],                        shapeW: 48, shapeH: 64 },
  { ratio: '1:1',  label: 'Square',    platforms: ['Instagram', 'Twitter'],                          shapeW: 60, shapeH: 60 },
  { ratio: '16:9', label: 'Landscape', platforms: ['YouTube', 'LinkedIn'],                           shapeW: 64, shapeH: 36 },
]

// ── Format card ────────────────────────────────────────────────────────────────

interface FormatCardProps extends FormatDef {
  selected: boolean
  onToggle: () => void
}

function FormatCard({ ratio, label, platforms, isAIPick, shapeW, shapeH, selected, onToggle }: FormatCardProps) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: `${isAIPick ? '18px' : '14px'} 8px 12px`,
        borderRadius: '14px',
        cursor: 'pointer',
        position: 'relative' as const,
        backgroundColor: selected
          ? 'rgba(168,85,247,0.08)'
          : hovered
          ? 'rgba(255,255,255,0.02)'
          : 'var(--surface-card)',
        border: `1.5px solid ${selected ? '#a855f7' : hovered ? 'rgba(255,255,255,0.08)' : 'var(--border-subtle)'}`,
        boxShadow: selected
          ? '0 0 0 3px rgba(168,85,247,0.15), 0 4px 16px rgba(0,0,0,0.25)'
          : hovered
          ? '0 2px 8px rgba(0,0,0,0.15)'
          : 'none',
        transition: 'all 0.15s ease',
        userSelect: 'none' as const,
      }}
    >
      {/* AI Pick badge — floats above top edge */}
      {isAIPick && (
        <div style={{
          position: 'absolute',
          top: '-11px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
          borderRadius: '100px',
          padding: '3px 9px',
          fontSize: '8.5px',
          fontWeight: 700,
          color: '#fff',
          letterSpacing: '0.06em',
          textTransform: 'uppercase' as const,
          whiteSpace: 'nowrap' as const,
          boxShadow: '0 2px 8px rgba(168,85,247,0.5)',
          pointerEvents: 'none' as const,
        }}>
          AI Pick
        </div>
      )}

      {/* Ratio shape — 72×72 canvas */}
      <div style={{
        width: '72px',
        height: '72px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: '10px',
        flexShrink: 0,
      }}>
        <div style={{
          width: `${shapeW}px`,
          height: `${shapeH}px`,
          borderRadius: '3px',
          background: selected
            ? 'linear-gradient(145deg, rgba(168,85,247,0.55), rgba(77,124,255,0.55))'
            : 'rgba(255,255,255,0.06)',
          border: `1.5px solid ${selected ? 'rgba(168,85,247,0.55)' : 'rgba(255,255,255,0.10)'}`,
          boxShadow: selected ? '0 0 12px rgba(168,85,247,0.3)' : 'none',
          transition: 'all 0.15s ease',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          {selected && (
            <span style={{
              fontSize: `${Math.round(Math.min(shapeW, shapeH) * 0.36)}px`,
              color: 'rgba(255,255,255,0.9)',
              lineHeight: 1,
            }}>✓</span>
          )}
        </div>
      </div>

      {/* Ratio label */}
      <span style={{
        fontSize: '13px',
        fontWeight: 700,
        color: selected ? '#d8b4fe' : 'var(--text-primary)',
        fontFamily: 'var(--font-mono)',
        letterSpacing: '-0.01em',
        lineHeight: 1,
        marginBottom: '3px',
      }}>{ratio}</span>

      {/* Format name */}
      <span style={{
        fontSize: '10px',
        fontWeight: 500,
        color: selected ? 'rgba(216,180,254,0.7)' : 'var(--text-tertiary)',
        marginBottom: '9px',
      }}>{label}</span>

      {/* Platform chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: '3px', justifyContent: 'center' }}>
        {platforms.map((p) => (
          <span key={p} style={{
            fontSize: '9px',
            padding: '2px 5px',
            borderRadius: '4px',
            backgroundColor: selected ? 'rgba(168,85,247,0.15)' : 'rgba(255,255,255,0.05)',
            color: selected ? 'rgba(216,180,254,0.8)' : 'rgba(255,255,255,0.28)',
            fontWeight: 500,
            whiteSpace: 'nowrap' as const,
          }}>{p}</span>
        ))}
      </div>
    </div>
  )
}

// ── Platform targeting chip ────────────────────────────────────────────────────

interface PlatformChipProps {
  id: TargetPlatform
  name: string
  icon: string
  selected: boolean
  onSelect: () => void
}

function PlatformChip({ id: _id, name, icon, selected, onSelect }: PlatformChipProps) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: 1,
        height: '34px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '5px',
        borderRadius: '8px',
        cursor: 'pointer',
        backgroundColor: selected ? 'rgba(168,85,247,0.1)' : hovered ? 'rgba(255,255,255,0.03)' : 'var(--surface-input)',
        border: `1px solid ${selected ? '#a855f7' : hovered ? 'var(--border-default)' : 'var(--border-subtle)'}`,
        transition: 'all 0.12s ease',
        fontSize: 'var(--text-xs)',
        fontWeight: selected ? 600 : 400,
        color: selected ? '#d8b4fe' : 'var(--text-secondary)',
        userSelect: 'none' as const,
      }}
    >
      <span style={{ fontSize: '13px', lineHeight: 1 }}>{icon}</span>
      <span>{name}</span>
    </div>
  )
}

// ── Toggle switch ──────────────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled = false }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div
      onClick={() => !disabled && onChange(!checked)}
      style={{
        width: '32px',
        height: '18px',
        borderRadius: '9px',
        backgroundColor: checked ? '#a855f7' : 'var(--surface-input)',
        border: '1.5px solid ' + (checked ? '#a855f7' : 'var(--border-subtle)'),
        position: 'relative',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background-color 0.2s ease',
        flexShrink: 0,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <div style={{
        position: 'absolute',
        top: '1px',
        left: checked ? '14px' : '1px',
        width: '12px',
        height: '12px',
        borderRadius: '50%',
        backgroundColor: '#fff',
        transition: 'left 0.2s ease',
      }} />
    </div>
  )
}

// ── Section label ──────────────────────────────────────────────────────────────

function SectionLabel({ text, hint }: { text: string; hint?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: 'var(--space-2)' }}>
      <div style={{
        fontSize: '10px',
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        color: 'var(--text-tertiary)',
      }}>
        {text}
      </div>
      {hint && (
        <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.2)', fontStyle: 'italic' }}>{hint}</span>
      )}
    </div>
  )
}

// ── Toggle row ──────────────────────────────────────────────────────────────────

interface ToggleRowProps {
  label: string
  sublabel: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}

function ToggleRow({ label, sublabel, checked, onChange, disabled }: ToggleRowProps) {
  return (
    <div style={tr.row}>
      <div style={tr.text}>
        <span style={tr.label}>{label}</span>
        <span style={tr.sublabel}>{sublabel}</span>
      </div>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  )
}

const tr: Record<string, React.CSSProperties> = {
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 'var(--space-3)',
    padding: 'var(--space-3)',
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
  },
  text: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    flex: 1,
    minWidth: 0,
  },
  label: {
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  sublabel: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
  },
}

// ── Quality / fps options ──────────────────────────────────────────────────────

const QUALITY_OPTIONS: Array<{ label: string; profile: RenderProfile }> = [
  { label: '480p',               profile: 'fast' },
  { label: '720p',               profile: 'balanced' },
  { label: '1080p (Recommended)', profile: 'quality' },
  { label: '4K',                 profile: 'best' },
]

const FPS_OPTIONS: Array<{ label: string; value: 30 | 60 }> = [
  { label: '24fps', value: 30 },
  { label: '30fps', value: 30 },
  { label: '60fps', value: 60 },
]

// ── RenderStep ─────────────────────────────────────────────────────────────────

export function RenderStep({
  sessionId,
  sessionDuration,
  sessionSourceMode,
  sessionOutputDir,
  onRenderStarted,
}: RenderStepProps) {
  const { t } = useI18n()
  const { settings, setPlatform, toggleFormat, update } = useEditStore()
  const [renderLoading, setRenderLoading] = useState(false)
  const [renderError, setRenderError] = useState<string | null>(null)
  const [customOutputDir, setCustomOutputDir] = useState(sessionOutputDir)

  const [broll, setBroll] = useState(true)
  const [zoom, setZoom] = useState(true)
  const [enhanceAudio, setEnhanceAudio] = useState(false)
  const [watermark, setWatermark] = useState(false)

  useEffect(() => {
    setCustomOutputDir(sessionOutputDir)
  }, [sessionOutputDir])

  const pickOutputDir = async () => {
    const api = (window as any).electronAPI
    if (!api?.pickOutputDir) return
    const picked: string | null = await api.pickOutputDir()
    if (picked) { setCustomOutputDir(picked); setRenderError(null) }
  }

  const handleSubmit = async () => {
    if (!sessionId) return
    const outDir = customOutputDir.trim() || sessionOutputDir
    if (!outDir) {
      setRenderError(t('render_error_no_dir'))
      return
    }
    setRenderLoading(true)
    setRenderError(null)
    try {
      const resp = await submitRender({
        source_mode: sessionSourceMode,
        edit_session_id: sessionId,
        output_dir: outDir,
        output_mode: 'manual',
        target_platform: settings.targetPlatform,
        aspect_ratio: settings.aspectRatio,
        output_fps: settings.outputFps,
        render_profile: settings.renderProfile,
        ai_director_enabled: settings.aiDirectorEnabled,
        max_export_parts: settings.maxExportParts,
        min_part_sec: settings.minPartSec,
        max_part_sec: settings.maxPartSec,
        part_order: settings.partOrder,
        add_subtitle: settings.addSubtitle,
        subtitle_style: settings.subtitleStyle,
        sub_font_size: settings.subFontSize,
        highlight_per_word: settings.highlightPerWord,
        voice_enabled: settings.voiceEnabled,
        ...(settings.voiceEnabled ? {
          voice_language: settings.voiceLanguage,
          voice_gender: settings.voiceGender,
          voice_source: 'subtitle' as const,
        } : {}),
        motion_aware_crop: settings.motionAwareCrop,
        ...(settings.motionAwareCrop ? { reframe_mode: settings.reframeMode } : {}),
        ...(settings.clipLock && settings.clipLock.length > 0
          ? { clip_lock: settings.clipLock }
          : {}),
      })
      onRenderStarted(resp.job_id)
    } catch {
      setRenderError(t('render_error_submit'))
    } finally {
      setRenderLoading(false)
    }
  }

  const estSecs = sessionDuration > 0 ? Math.max(15, Math.floor(sessionDuration * 0.12)) : null
  const selectedCount = settings.selectedFormats.length

  return (
    <div style={s.page}>
      <div style={s.scroll}>
        <div style={s.inner}>

          {/* ── Section 1: Format ──────────────────────────────────────────── */}
          <div style={s.section}>
            <SectionLabel text="Output Format" hint="select one or more" />

            <div style={s.formatGrid}>
              {FORMAT_DEFS.map((def) => (
                <FormatCard
                  key={def.ratio}
                  {...def}
                  selected={settings.selectedFormats.includes(def.ratio)}
                  onToggle={() => toggleFormat(def.ratio)}
                />
              ))}
            </div>

            {/* Multi-select hint */}
            {selectedCount > 1 && (
              <div style={s.multiHint}>
                <span style={{ color: '#d8b4fe', fontWeight: 700 }}>{selectedCount} formats</span>
                {' '}selected · primary render: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{settings.aspectRatio}</span>
                <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '6px' }}>· multi-format batch coming soon</span>
              </div>
            )}
          </div>

          {/* ── Section 2: Platform targeting ─────────────────────────────── */}
          <div style={s.section}>
            <SectionLabel text="Platform Targeting" hint="optimizes AI & metadata" />
            <div style={s.platformRow}>
              <PlatformChip id="tiktok"          name="TikTok"    icon="🎵" selected={settings.targetPlatform === 'tiktok'}         onSelect={() => setPlatform('tiktok')} />
              <PlatformChip id="youtube_shorts"  name="YT Shorts" icon="▶" selected={settings.targetPlatform === 'youtube_shorts'}  onSelect={() => setPlatform('youtube_shorts')} />
              <PlatformChip id="instagram_reels" name="Reels"     icon="◈" selected={settings.targetPlatform === 'instagram_reels'} onSelect={() => setPlatform('instagram_reels')} />
            </div>
          </div>

          {/* ── Section 3: Quality ────────────────────────────────────────── */}
          <div style={s.section}>
            <SectionLabel text="Quality Settings" />
            <div style={s.qualityGrid}>
              <div style={s.fieldGroup}>
                <label style={s.fieldLabel}>Resolution</label>
                <select
                  style={s.select}
                  value={settings.renderProfile}
                  onChange={(e) => update({ renderProfile: e.target.value as RenderProfile })}
                >
                  {QUALITY_OPTIONS.map((o) => (
                    <option key={o.profile} value={o.profile}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div style={s.fieldGroup}>
                <label style={s.fieldLabel}>Frame Rate</label>
                <select
                  style={s.select}
                  value={settings.outputFps}
                  onChange={(e) => update({ outputFps: Number(e.target.value) as 30 | 60 })}
                >
                  {FPS_OPTIONS.map((o) => (
                    <option key={o.label} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div style={s.fieldGroup}>
                <label style={s.fieldLabel}>Codec</label>
                <select style={s.select} disabled>
                  <option>H.264 (MP4)</option>
                </select>
              </div>
            </div>
          </div>

          {/* ── Section 4: Enhancements ───────────────────────────────────── */}
          <div style={s.section}>
            <SectionLabel text={t('render_advanced_label')} />
            <div style={s.toggleGrid}>
              <ToggleRow
                label={t('render_auto_captions')}
                sublabel="Burn subtitles into video"
                checked={settings.addSubtitle}
                onChange={(v) => update({ addSubtitle: v })}
              />
              <ToggleRow
                label="AI Director"
                sublabel="AI optimizes clip selection"
                checked={settings.aiDirectorEnabled}
                onChange={(v) => update({ aiDirectorEnabled: v })}
              />
              <ToggleRow
                label={t('render_broll')}
                sublabel="AI inserts B-roll cuts"
                checked={broll}
                onChange={setBroll}
                disabled
              />
              <ToggleRow
                label={t('render_zoom')}
                sublabel="Dynamic zoom & crop"
                checked={zoom}
                onChange={setZoom}
                disabled
              />
              <ToggleRow
                label={t('render_enhance_audio')}
                sublabel="Normalize & de-noise"
                checked={enhanceAudio}
                onChange={setEnhanceAudio}
                disabled
              />
              <ToggleRow
                label={t('render_watermark')}
                sublabel="Add branding watermark"
                checked={watermark}
                onChange={setWatermark}
                disabled
              />
            </div>
          </div>

          {/* ── Section 5: Output folder ──────────────────────────────────── */}
          <div style={s.section}>
            <SectionLabel text={t('render_output_label')} />
            <div style={s.dirRow}>
              <input
                type="text"
                value={customOutputDir}
                onChange={(e) => { setCustomOutputDir(e.target.value); setRenderError(null) }}
                placeholder={t('render_output_placeholder')}
                style={s.dirInput}
              />
              <button onClick={pickOutputDir} style={s.browseBtn} title="Browse">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
              </button>
            </div>
            <span style={s.dirHint}>{t('render_output_hint')}</span>
          </div>

          {/* Estimate + errors */}
          {estSecs !== null && (
            <p style={s.estText}>~{estSecs}s estimated render time</p>
          )}
          {renderError && (
            <span style={s.errorText}>{renderError}</span>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={renderLoading || !sessionId}
            style={{
              ...s.submitBtn,
              background: renderLoading || !sessionId
                ? 'var(--surface-panel)'
                : 'linear-gradient(135deg, #a855f7 0%, #4d7cff 100%)',
              color: renderLoading || !sessionId ? 'var(--text-tertiary)' : '#fff',
              cursor: renderLoading || !sessionId ? 'not-allowed' : 'pointer',
              boxShadow: renderLoading || !sessionId
                ? 'none'
                : '0 4px 16px rgba(168,85,247,0.35)',
            }}
          >
            {renderLoading ? t('render_starting') : `${t('render_start_btn')} →`}
          </button>

        </div>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  page: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--surface-base)',
  },
  scroll: {
    flex: 1,
    overflowY: 'auto',
    minHeight: 0,
  },
  inner: {
    maxWidth: 'min(720px, 100%)',
    margin: '0 auto',
    padding: 'var(--space-6) var(--space-6) var(--space-8)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
  },
  formatGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: 'var(--space-3)',
    paddingTop: '14px',
  },
  multiHint: {
    marginTop: '10px',
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    padding: '6px 10px',
    backgroundColor: 'rgba(168,85,247,0.06)',
    borderRadius: '8px',
    border: '1px solid rgba(168,85,247,0.15)',
  },
  platformRow: {
    display: 'flex',
    gap: 'var(--space-2)',
  },
  qualityGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 'var(--space-3)',
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  fieldLabel: {
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
    color: 'var(--text-secondary)',
  },
  select: {
    height: '34px',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-xs)',
    padding: '0 var(--space-2)',
    cursor: 'pointer',
    outline: 'none',
  },
  toggleGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: 'var(--space-2)',
  },
  dirRow: {
    display: 'flex',
    gap: 'var(--space-2)',
  },
  dirInput: {
    flex: 1,
    height: '34px',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font-mono)',
    padding: '0 var(--space-3)',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  browseBtn: {
    width: '34px',
    height: '34px',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--surface-input)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
  },
  dirHint: {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    marginTop: '4px',
  },
  estText: {
    margin: 0,
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
  },
  errorText: {
    fontSize: 'var(--text-xs)',
    color: 'var(--status-error)',
  },
  submitBtn: {
    height: '46px',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    transition: 'opacity 0.15s ease, box-shadow 0.15s ease',
    letterSpacing: '0.02em',
    width: '100%',
  },
}
