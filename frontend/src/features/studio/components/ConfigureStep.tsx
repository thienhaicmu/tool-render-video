import React, { useState } from 'react'
import { useEditStore } from '../../../stores/editStore'
import type { TargetPlatform, RenderProfile } from '../../../stores/editStore'

// ── Types ──────────────────────────────────────────────────────────────────────

interface ConfigureStepProps {
  defaultOutputDir?: string
  onContinue: (outputDir: string) => void
}

// ── Constants ──────────────────────────────────────────────────────────────────

const SAMPLE_TEXT = 'The future of AI is creator tools'

const FORMAT_DEFS: {
  ratio: string
  shapeW: number
  shapeH: number
  aiPick?: boolean
}[] = [
  { ratio: '9:16',  shapeW: 28, shapeH: 50, aiPick: true },
  { ratio: '1:1',   shapeW: 44, shapeH: 44 },
  { ratio: '3:4',   shapeW: 34, shapeH: 46 },
  { ratio: '16:9',  shapeW: 56, shapeH: 32 },
  { ratio: '4:5',   shapeW: 38, shapeH: 47 },
]

const PLATFORM_DEFS: { value: TargetPlatform; label: string; icon: string }[] = [
  { value: 'tiktok',          label: 'TikTok',         icon: 'TT' },
  { value: 'youtube_shorts',  label: 'YouTube Shorts', icon: 'YT' },
  { value: 'instagram_reels', label: 'Instagram',      icon: 'IG' },
]

const QUALITY_DEFS: { value: RenderProfile; label: string; hint: string }[] = [
  { value: 'fast',     label: 'Fast',     hint: '~1 min' },
  { value: 'balanced', label: 'Balanced', hint: 'Best value' },
  { value: 'quality',  label: 'Quality',  hint: 'Slower' },
  { value: 'best',     label: 'Best',     hint: 'Max quality' },
]

const SUBTITLE_STYLE_DEFS = [
  { value: 'standard',  icon: 'Aa', label: 'Standard',  desc: 'Clean text' },
  { value: 'karaoke',   icon: '♪',  label: 'Karaoke',   desc: 'Word highlight' },
  { value: 'highlight', icon: '■',  label: 'Highlight', desc: 'Word boxes' },
] as const

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '22px', marginBottom: '10px' }}>
      <div style={{ width: '2px', height: '12px', background: 'var(--accent-primary)', borderRadius: '999px', flexShrink: 0 }} />
      <span style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' as const, color: 'var(--accent-primary)' }}>
        {children}
      </span>
    </div>
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      aria-pressed={value}
      style={{
        width: '40px',
        height: '24px',
        borderRadius: '12px',
        border: 'none',
        backgroundColor: value ? '#a855f7' : 'var(--surface-input)',
        position: 'relative',
        cursor: 'pointer',
        transition: 'background-color 0.2s ease',
        flexShrink: 0,
        outline: 'none',
      }}
    >
      <span style={{
        position: 'absolute',
        top: '4px',
        left: value ? '20px' : '4px',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        backgroundColor: '#fff',
        transition: 'left 0.2s ease',
        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
      }} />
    </button>
  )
}

// ── Phone mockup with live subtitle preview ────────────────────────────────────

interface PhoneMockupProps {
  subtitleStyle: string
  addSubtitle: boolean
  selectedFormat: string
}

function SubtitlePreview({ subtitleStyle, text }: { subtitleStyle: string; text: string }) {
  const words = text.split(' ')

  if (subtitleStyle === 'standard') {
    return (
      <div style={{
        textAlign: 'center' as const,
        padding: '4px 8px',
      }}>
        <span style={{
          fontSize: '10px',
          fontWeight: 700,
          color: '#fff',
          lineHeight: 1.4,
          textShadow: '0 1px 4px rgba(0,0,0,0.8)',
          letterSpacing: '0.01em',
        }}>
          {text}
        </span>
      </div>
    )
  }

  if (subtitleStyle === 'karaoke') {
    const highlightIdx = 5 // "creator" (index 5 in "The future of AI is creator tools")
    return (
      <div style={{
        textAlign: 'center' as const,
        padding: '4px 8px',
        display: 'flex',
        flexWrap: 'wrap' as const,
        justifyContent: 'center',
        gap: '3px',
      }}>
        {words.map((word, i) => (
          <span
            key={i}
            style={{
              fontSize: '10px',
              fontWeight: i === highlightIdx ? 800 : 700,
              color: i === highlightIdx ? '#FFD700' : '#fff',
              textShadow: i === highlightIdx
                ? '0 0 8px rgba(255,215,0,0.6), 0 1px 4px rgba(0,0,0,0.8)'
                : '0 1px 4px rgba(0,0,0,0.8)',
              lineHeight: 1.4,
              letterSpacing: '0.01em',
            }}
          >
            {word}
          </span>
        ))}
      </div>
    )
  }

  // highlight — each word in a pill
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap' as const,
      justifyContent: 'center',
      gap: '3px',
      padding: '4px 8px',
    }}>
      {words.map((word, i) => (
        <span
          key={i}
          style={{
            fontSize: '9px',
            fontWeight: 700,
            color: '#fff',
            backgroundColor: 'rgba(0,0,0,0.72)',
            padding: '1px 4px',
            borderRadius: '3px',
            lineHeight: 1.4,
            letterSpacing: '0.01em',
          }}
        >
          {word}
        </span>
      ))}
    </div>
  )
}

function PhoneMockup({ subtitleStyle, addSubtitle, selectedFormat }: PhoneMockupProps) {
  const PHONE_W = 200
  const PHONE_H = 354

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '14px',
    }}>
      {/* Phone frame */}
      <div style={{
        position: 'relative',
        width: `${PHONE_W}px`,
        height: `${PHONE_H}px`,
        borderRadius: '24px',
        overflow: 'hidden',
        border: '2px solid rgba(255,255,255,0.12)',
        boxShadow: '0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04), inset 0 1px 0 rgba(255,255,255,0.08)',
        backgroundColor: '#0a0a0c',
        flexShrink: 0,
      }}>
        {/* Notch */}
        <div style={{
          position: 'absolute',
          top: '10px',
          left: '50%',
          transform: 'translateX(-50%)',
          width: '60px',
          height: '10px',
          borderRadius: '5px',
          backgroundColor: 'rgba(0,0,0,0.9)',
          zIndex: 20,
        }} />

        {/* Video scene — simulated talking-head gradient */}
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(160deg, #1a1030 0%, #0e1a2e 40%, #0a0a0c 100%)',
        }}>
          {/* Ambient light blobs */}
          <div style={{
            position: 'absolute',
            top: '20%',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '120px',
            height: '140px',
            borderRadius: '50%',
            background: 'radial-gradient(ellipse, rgba(100,60,180,0.35) 0%, transparent 70%)',
            filter: 'blur(20px)',
          }} />
          {/* Simulated figure silhouette */}
          <div style={{
            position: 'absolute',
            bottom: '80px',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '70px',
            height: '100px',
            borderRadius: '50% 50% 40% 40% / 60% 60% 40% 40%',
            background: 'linear-gradient(180deg, rgba(140,100,200,0.25) 0%, rgba(80,60,140,0.1) 100%)',
            filter: 'blur(4px)',
          }} />
          {/* Face glow */}
          <div style={{
            position: 'absolute',
            top: '28%',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '44px',
            height: '44px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(200,170,255,0.2) 0%, transparent 70%)',
            filter: 'blur(6px)',
          }} />
          {/* Scanline texture */}
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.04) 3px, rgba(0,0,0,0.04) 4px)',
            pointerEvents: 'none',
          }} />
        </div>

        {/* Bottom gradient fade */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '120px',
          background: 'linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.5) 50%, transparent 100%)',
          pointerEvents: 'none',
        }} />

        {/* Subtitle overlay */}
        {addSubtitle && (
          <div style={{
            position: 'absolute',
            bottom: '24px',
            left: '8px',
            right: '8px',
            zIndex: 10,
          }}>
            <SubtitlePreview subtitleStyle={subtitleStyle} text={SAMPLE_TEXT} />
          </div>
        )}

        {/* No subtitle indicator */}
        {!addSubtitle && (
          <div style={{
            position: 'absolute',
            bottom: '28px',
            left: 0,
            right: 0,
            display: 'flex',
            justifyContent: 'center',
            zIndex: 10,
          }}>
            <span style={{
              fontSize: '9px',
              color: 'rgba(255,255,255,0.3)',
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.06em',
            }}>
              NO SUBTITLES
            </span>
          </div>
        )}

        {/* Format badge — top right */}
        <div style={{
          position: 'absolute',
          top: '16px',
          right: '12px',
          zIndex: 15,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: '4px',
        }}>
          <div style={{
            fontSize: '9px',
            fontWeight: 700,
            color: '#fff',
            backgroundColor: 'rgba(0,0,0,0.6)',
            padding: '2px 6px',
            borderRadius: '5px',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.04em',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255,255,255,0.1)',
          }}>
            {selectedFormat}
          </div>
          {selectedFormat === '9:16' && (
            <div style={{
              fontSize: '8px',
              fontWeight: 700,
              background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              letterSpacing: '0.04em',
            }}>
              AI PICK
            </div>
          )}
        </div>

        {/* Record indicator */}
        <div style={{
          position: 'absolute',
          top: '16px',
          left: '12px',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: '#ff3b30',
          boxShadow: '0 0 6px rgba(255,59,48,0.7)',
          zIndex: 15,
        }} />
      </div>

      {/* Label below */}
      <div style={{
        fontSize: '11px',
        color: 'var(--text-tertiary)',
        textAlign: 'center' as const,
        lineHeight: 1.4,
      }}>
        Live preview
      </div>
    </div>
  )
}

// ── Format card ────────────────────────────────────────────────────────────────

function FormatCard({
  ratio, shapeW, shapeH, aiPick, selected, onToggle,
}: {
  ratio: string
  shapeW: number
  shapeH: number
  aiPick?: boolean
  selected: boolean
  onToggle: () => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
      {/* AI Pick badge above card */}
      {aiPick ? (
        <span style={{
          fontSize: '8px',
          fontWeight: 800,
          background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          letterSpacing: '0.07em',
          textTransform: 'uppercase' as const,
          height: '12px',
          lineHeight: '12px',
        }}>
          AI PICK
        </span>
      ) : (
        <div style={{ height: '12px' }} />
      )}

      <button
        onClick={onToggle}
        style={{
          width: '72px',
          height: '88px',
          border: `${selected ? '2px' : '1.5px'} solid ${selected ? 'var(--accent-primary)' : 'var(--border-default)'}`,
          borderRadius: '10px',
          backgroundColor: selected ? 'rgba(77,124,255,0.1)' : 'var(--surface-input)',
          boxShadow: selected ? '0 0 0 1px rgba(77,124,255,.3), 0 0 12px rgba(77,124,255,.15)' : 'none',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          transition: 'border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease',
          padding: 0,
          outline: 'none',
        }}
      >
        {/* Shape rectangle */}
        <div style={{
          width: `${shapeW}px`,
          height: `${shapeH}px`,
          borderRadius: '3px',
          backgroundColor: selected
            ? 'rgba(77,124,255,0.45)'
            : 'rgba(255,255,255,0.12)',
          border: `1px solid ${selected ? 'rgba(77,124,255,0.5)' : 'rgba(255,255,255,0.18)'}`,
          transition: 'background-color 0.15s ease',
        }} />

        {/* Ratio label */}
        <span style={{
          fontSize: '10px',
          fontWeight: 700,
          color: selected ? 'var(--accent-primary)' : 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.02em',
          transition: 'color 0.15s ease',
        }}>
          {ratio}
        </span>
      </button>
    </div>
  )
}

// ── Slider with label ──────────────────────────────────────────────────────────

function LabeledSlider({
  label, min, max, value, onChange,
}: {
  label: string
  min: number
  max: number
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-tertiary)',
          fontWeight: 500,
        }}>
          {label}
        </span>
        <span style={{
          fontSize: '11px',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
        }}>
          {value}s
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value))}
        style={{
          width: '100%',
          accentColor: '#a855f7',
          cursor: 'pointer',
          height: '4px',
        }}
      />
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{min}s</span>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{max}s</span>
      </div>
    </div>
  )
}

// ── ConfigureStep (main export) ────────────────────────────────────────────────

export function ConfigureStep({ defaultOutputDir = '', onContinue }: ConfigureStepProps) {
  const { settings, update, setPlatform, toggleFormat } = useEditStore()
  const [outputDir, setOutputDir] = useState(defaultOutputDir)
  const selectedFormats = settings.selectedFormats
  const hasFormat = selectedFormats.length > 0
  const primaryFormat = selectedFormats[0] ?? '9:16'

  return (
    <>
      {/* Keyframe for subtle animation */}
      <style>{`
        @keyframes cfg-fadein { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
        .cfg-section { animation: cfg-fadein 0.25s ease both; }
        .cfg-format-scroll::-webkit-scrollbar { display: none; }
      `}</style>

      <div style={{
        flex: 1,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--surface-base)',
      }}>
        {/* ── Main body: two columns ── */}
        <div style={{
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
        }}>

          {/* LEFT — Phone mockup (38%) */}
          <div style={{
            width: '38%',
            flexShrink: 0,
            borderRight: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'var(--surface-card)',
            padding: '24px 16px',
            position: 'relative',
            overflow: 'hidden',
          }}>
            {/* Ambient glow behind phone */}
            <div style={{
              position: 'absolute',
              top: '40%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: '240px',
              height: '240px',
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(168,85,247,0.08) 0%, transparent 70%)',
              pointerEvents: 'none',
            }} />

            <PhoneMockup
              subtitleStyle={settings.subtitleStyle}
              addSubtitle={settings.addSubtitle}
              selectedFormat={primaryFormat}
            />

            {/* Style hint below */}
            {settings.addSubtitle && (
              <div style={{
                marginTop: '6px',
                fontSize: '10px',
                color: 'var(--text-tertiary)',
                textAlign: 'center' as const,
                letterSpacing: '0.04em',
                textTransform: 'uppercase' as const,
                fontWeight: 600,
              }}>
                {settings.subtitleStyle} style
              </div>
            )}
          </div>

          {/* RIGHT — Settings (62%) */}
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minWidth: 0,
          }}>
            {/* Header */}
            <div style={{
              height: '48px',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 24px',
              borderBottom: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--surface-panel)',
            }}>
              <span style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 600,
                color: 'var(--text-primary)',
                letterSpacing: '-0.01em',
              }}>
                Configure Output
              </span>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '16px',
                backgroundColor: 'rgba(168,85,247,0.1)',
                border: '1px solid rgba(168,85,247,0.2)',
              }}>
                <div style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: '#a855f7',
                  boxShadow: '0 0 6px rgba(168,85,247,0.8)',
                }} />
                <span style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  color: '#a855f7',
                  letterSpacing: '0.03em',
                }}>
                  Step 2
                </span>
              </div>
            </div>

            {/* Scrollable body */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
            }}>

              {/* ── Section 0: Output Directory ── */}
              <div className="cfg-section" style={{ animationDelay: '0ms' }}>
                <SectionLabel>Output Directory</SectionLabel>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  backgroundColor: 'var(--surface-input)',
                  borderRadius: '10px',
                  border: '1px solid var(--border-default)',
                }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                  </svg>
                  <input
                    type="text"
                    value={outputDir}
                    onChange={(e) => setOutputDir(e.target.value)}
                    placeholder="e.g. D:\MyVideos\output"
                    style={{
                      flex: 1,
                      background: 'none',
                      border: 'none',
                      outline: 'none',
                      color: 'var(--text-primary)',
                      fontSize: 'var(--text-sm)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  />
                </div>
                <div style={{ marginTop: '5px', fontSize: '10px', color: 'var(--text-tertiary)' }}>
                  Rendered clips will be saved here. Leave blank to use session folder.
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 1: Output Format ── */}
              <div className="cfg-section" style={{ animationDelay: '0ms' }}>
                <SectionLabel>Output Format</SectionLabel>
                <div className="cfg-format-scroll" style={{
                  display: 'flex',
                  flexWrap: 'wrap' as const,
                  gap: '10px',
                }}>
                  {FORMAT_DEFS.map((f) => (
                    <FormatCard
                      key={f.ratio}
                      ratio={f.ratio}
                      shapeW={f.shapeW}
                      shapeH={f.shapeH}
                      aiPick={f.aiPick}
                      selected={selectedFormats.includes(f.ratio)}
                      onToggle={() => toggleFormat(f.ratio)}
                    />
                  ))}
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 2: Clip Duration ── */}
              <div className="cfg-section" style={{ animationDelay: '40ms' }}>
                <SectionLabel>Clip Duration</SectionLabel>
                <div style={{
                  display: 'flex',
                  gap: '20px',
                  padding: '16px',
                  backgroundColor: 'var(--surface-card)',
                  borderRadius: '12px',
                  border: '1px solid var(--border-subtle)',
                }}>
                  <LabeledSlider
                    label="Min"
                    min={10}
                    max={120}
                    value={settings.minPartSec}
                    onChange={(v) => update({ minPartSec: Math.min(v, settings.maxPartSec - 5) })}
                  />
                  <div style={{
                    width: '1px',
                    alignSelf: 'stretch',
                    backgroundColor: 'var(--border-subtle)',
                  }} />
                  <LabeledSlider
                    label="Max"
                    min={15}
                    max={300}
                    value={settings.maxPartSec}
                    onChange={(v) => update({ maxPartSec: Math.max(v, settings.minPartSec + 5) })}
                  />
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 3: Max Clips Output ── */}
              <div className="cfg-section" style={{ animationDelay: '60ms' }}>
                <SectionLabel>Output Count</SectionLabel>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '14px 16px',
                  backgroundColor: 'var(--surface-card)',
                  borderRadius: '12px',
                  border: '1px solid var(--border-subtle)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <button
                      onClick={() => update({ maxExportParts: Math.max(1, settings.maxExportParts - 1) })}
                      disabled={settings.maxExportParts <= 1}
                      style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '8px',
                        border: '1px solid var(--border-default)',
                        backgroundColor: settings.maxExportParts <= 1 ? 'var(--surface-panel)' : 'var(--surface-input)',
                        color: settings.maxExportParts <= 1 ? 'var(--text-tertiary)' : 'var(--text-primary)',
                        fontSize: '18px',
                        cursor: settings.maxExportParts <= 1 ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        lineHeight: 1,
                        fontWeight: 400,
                        transition: 'background-color 0.15s ease, color 0.15s ease',
                        outline: 'none',
                      }}
                    >
                      −
                    </button>
                    <div style={{
                      minWidth: '52px',
                      textAlign: 'center' as const,
                    }}>
                      <span style={{
                        fontSize: '24px',
                        fontWeight: 800,
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono)',
                        letterSpacing: '-0.03em',
                        lineHeight: 1,
                      }}>
                        {settings.maxExportParts}
                      </span>
                    </div>
                    <button
                      onClick={() => update({ maxExportParts: Math.min(12, settings.maxExportParts + 1) })}
                      disabled={settings.maxExportParts >= 12}
                      style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '8px',
                        border: '1px solid var(--border-default)',
                        backgroundColor: settings.maxExportParts >= 12 ? 'var(--surface-panel)' : 'var(--surface-input)',
                        color: settings.maxExportParts >= 12 ? 'var(--text-tertiary)' : 'var(--text-primary)',
                        fontSize: '18px',
                        cursor: settings.maxExportParts >= 12 ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        lineHeight: 1,
                        fontWeight: 400,
                        transition: 'background-color 0.15s ease, color 0.15s ease',
                        outline: 'none',
                      }}
                    >
                      +
                    </button>
                  </div>
                  <div>
                    <span style={{
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      color: 'var(--text-secondary)',
                    }}>
                      {settings.maxExportParts === 1 ? 'clip' : 'clips'} will be generated
                    </span>
                    <div style={{
                      fontSize: '10px',
                      color: 'var(--text-tertiary)',
                      marginTop: '2px',
                    }}>
                      AI picks the highest-scoring segments
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 4: Subtitle Style ── */}
              <div className="cfg-section" style={{ animationDelay: '80ms' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '10px',
                }}>
                  <SectionLabel>Subtitle Style</SectionLabel>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    marginBottom: '10px',
                  }}>
                    <span style={{
                      fontSize: '11px',
                      color: settings.addSubtitle ? 'var(--text-primary)' : 'var(--text-tertiary)',
                      fontWeight: 500,
                      transition: 'color 0.2s ease',
                    }}>
                      {settings.addSubtitle ? 'ON' : 'OFF'}
                    </span>
                    <Toggle
                      value={settings.addSubtitle}
                      onChange={(v) => update({ addSubtitle: v })}
                    />
                  </div>
                </div>

                <div style={{
                  display: 'flex',
                  gap: '8px',
                  opacity: settings.addSubtitle ? 1 : 0.4,
                  transition: 'opacity 0.2s ease',
                  pointerEvents: settings.addSubtitle ? 'auto' : 'none',
                }}>
                  {SUBTITLE_STYLE_DEFS.map((style) => {
                    const isSelected = settings.subtitleStyle === style.value
                    return (
                      <button
                        key={style.value}
                        onClick={() => update({ subtitleStyle: style.value })}
                        style={{
                          flex: 1,
                          padding: '12px 8px',
                          border: `1.5px solid ${isSelected ? 'rgba(168,85,247,0.6)' : 'var(--border-default)'}`,
                          borderRadius: '10px',
                          backgroundColor: isSelected ? 'rgba(168,85,247,0.1)' : 'var(--surface-input)',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: '6px',
                          transition: 'border-color 0.15s ease, background-color 0.15s ease',
                          boxShadow: isSelected ? '0 0 10px rgba(168,85,247,0.2)' : 'none',
                          outline: 'none',
                        }}
                      >
                        <span style={{
                          fontSize: '18px',
                          color: isSelected ? '#a855f7' : 'var(--text-secondary)',
                          lineHeight: 1,
                          transition: 'color 0.15s ease',
                        }}>
                          {style.icon}
                        </span>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          color: isSelected ? '#a855f7' : 'var(--text-primary)',
                          transition: 'color 0.15s ease',
                          letterSpacing: '0.01em',
                        }}>
                          {style.label}
                        </span>
                        <span style={{
                          fontSize: '10px',
                          color: 'var(--text-tertiary)',
                          lineHeight: 1.3,
                        }}>
                          {style.desc}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 5: Platform ── */}
              <div className="cfg-section" style={{ animationDelay: '100ms' }}>
                <SectionLabel>Platform</SectionLabel>
                <div style={{
                  display: 'flex',
                  gap: '8px',
                }}>
                  {PLATFORM_DEFS.map((p) => {
                    const isSelected = settings.targetPlatform === p.value
                    return (
                      <button
                        key={p.value}
                        onClick={() => setPlatform(p.value)}
                        style={{
                          flex: 1,
                          height: '44px',
                          border: `1.5px solid ${isSelected ? 'rgba(168,85,247,0.6)' : 'var(--border-default)'}`,
                          borderRadius: '10px',
                          backgroundColor: isSelected ? 'rgba(168,85,247,0.12)' : 'var(--surface-input)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '7px',
                          transition: 'border-color 0.15s ease, background-color 0.15s ease',
                          outline: 'none',
                        }}
                      >
                        <span style={{
                          fontSize: '10px',
                          fontWeight: 800,
                          fontFamily: 'var(--font-mono)',
                          color: isSelected ? '#a855f7' : 'var(--text-tertiary)',
                          letterSpacing: '0.04em',
                          transition: 'color 0.15s ease',
                        }}>
                          {p.icon}
                        </span>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          color: isSelected ? '#a855f7' : 'var(--text-secondary)',
                          transition: 'color 0.15s ease',
                          whiteSpace: 'nowrap' as const,
                        }}>
                          {p.label}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              {/* ── Section 6: Quality ── */}
              <div className="cfg-section" style={{ animationDelay: '120ms' }}>
                <SectionLabel>Quality</SectionLabel>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: '8px',
                }}>
                  {QUALITY_DEFS.map((q) => {
                    const isSelected = settings.renderProfile === q.value
                    return (
                      <button
                        key={q.value}
                        onClick={() => update({ renderProfile: q.value })}
                        style={{
                          padding: '10px 6px',
                          border: `1.5px solid ${isSelected ? 'rgba(168,85,247,0.6)' : 'var(--border-default)'}`,
                          borderRadius: '10px',
                          backgroundColor: isSelected ? 'rgba(168,85,247,0.1)' : 'var(--surface-input)',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: '4px',
                          transition: 'border-color 0.15s ease, background-color 0.15s ease',
                          boxShadow: isSelected ? '0 0 8px rgba(168,85,247,0.2)' : 'none',
                          outline: 'none',
                        }}
                      >
                        <span style={{
                          fontSize: '12px',
                          fontWeight: 700,
                          color: isSelected ? '#a855f7' : 'var(--text-primary)',
                          transition: 'color 0.15s ease',
                          letterSpacing: '0.01em',
                        }}>
                          {q.label}
                        </span>
                        <span style={{
                          fontSize: '10px',
                          color: 'var(--text-tertiary)',
                          lineHeight: 1.2,
                        }}>
                          {q.hint}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Bottom spacer */}
              <div style={{ height: '4px' }} />
            </div>

            {/* ── Footer ── */}
            <div style={{
              flexShrink: 0,
              borderTop: '1px solid var(--border-subtle)',
              padding: '14px 24px',
              backgroundColor: 'var(--surface-panel)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}>
              {/* Selected format badges */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                flexWrap: 'wrap' as const,
                minWidth: 0,
                flex: 1,
              }}>
                <span style={{
                  fontSize: '11px',
                  color: 'var(--text-tertiary)',
                  fontWeight: 500,
                  flexShrink: 0,
                }}>
                  Formats:
                </span>
                {selectedFormats.length === 0 ? (
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--text-tertiary)',
                    fontStyle: 'italic',
                  }}>
                    none selected
                  </span>
                ) : (
                  selectedFormats.map((fmt) => (
                    <span
                      key={fmt}
                      style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        fontFamily: 'var(--font-mono)',
                        color: '#a855f7',
                        backgroundColor: 'rgba(168,85,247,0.12)',
                        border: '1px solid rgba(168,85,247,0.3)',
                        padding: '2px 7px',
                        borderRadius: '5px',
                        letterSpacing: '0.03em',
                      }}
                    >
                      {fmt}
                    </span>
                  ))
                )}
              </div>

              {/* CTA button */}
              <button
                onClick={hasFormat ? () => onContinue(outputDir || 'exports') : undefined}
                disabled={!hasFormat}
                style={{
                  flexShrink: 0,
                  height: '38px',
                  padding: '0 20px',
                  border: 'none',
                  borderRadius: '8px',
                  background: hasFormat
                    ? 'linear-gradient(135deg, #a855f7, #4d7cff)'
                    : 'var(--surface-input)',
                  color: hasFormat ? '#fff' : 'var(--text-tertiary)',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: hasFormat ? 'pointer' : 'not-allowed',
                  boxShadow: hasFormat
                    ? '0 0 0 1px rgba(168,85,247,.35), 0 0 16px rgba(168,85,247,.2)'
                    : 'none',
                  transition: 'opacity 0.15s ease',
                  outline: 'none',
                  whiteSpace: 'nowrap' as const,
                }}
                onMouseEnter={(e) => {
                  if (hasFormat) (e.currentTarget as HTMLButtonElement).style.opacity = '0.88'
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.opacity = '1'
                }}
              >
                Start Analysis →
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
