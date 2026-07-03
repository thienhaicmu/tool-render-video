/**
 * ContentStudio — dedicated UI for Content Mode (render_format="content").
 *
 * A SEPARATE workflow from clip-studio's RenderWorkflow (which is source-video
 * centric). Content Mode has no source footage: the user pastes a script, the
 * AI Content Director plans scenes + narration, and each scene is composited
 * over a chosen background. This screen reuses the shared building blocks
 * (renderStore.submitRender, useRenderSocket, RATIO_INFO, i18n, theme CSS vars)
 * without touching the clips/recap flow.
 *
 * Two views:
 *   compose  — script + config → "Generate Video" (submits a content job)
 *   monitor  — live progress via useRenderSocket (stage, per-scene parts, log)
 */
import React, { useMemo, useRef, useState } from 'react'
import type { RenderRequest } from '@/types/api'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { RATIO_INFO } from '../clip-studio/render/constants'
import type { Ratio } from '../clip-studio/render/types'

type BgKind = 'color' | 'image' | 'video'

const RATIOS: Ratio[] = ['r916', 'r11', 'r169']
const VOICE_LANGS = ['vi-VN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR'] as const
const TTS_ENGINES = ['edge', 'xtts', 'gemini'] as const
const SUB_STYLES = ['tiktok_bounce_v1', 'capcut_box', 'opus_pop', 'minimal_clean'] as const

export function ContentStudio() {
  const { t, lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()

  // ── compose state ─────────────────────────────────────────────────────────
  const [script, setScript] = useState('')
  const [ratio, setRatio] = useState<Ratio>('r916')
  const [targetDuration, setTargetDuration] = useState(90)
  const [bgKind, setBgKind] = useState<BgKind>('color')
  const [bgColor, setBgColor] = useState('#101820')
  const [bgAssetPath, setBgAssetPath] = useState('')
  const [voiceLang, setVoiceLang] = useState<typeof VOICE_LANGS[number]>('vi-VN')
  const [voiceGender, setVoiceGender] = useState<'female' | 'male'>('female')
  const [ttsEngine, setTtsEngine] = useState<typeof TTS_ENGINES[number]>('edge')
  const [subEnabled, setSubEnabled] = useState(true)
  const [subStyle, setSubStyle] = useState<string>('tiktok_bounce_v1')
  const [outputDir, setOutputDir] = useState('')

  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const charCount = script.trim().length
  const canSubmit = charCount > 0 && !submitting

  function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => setScript(String(reader.result || ''))
    reader.readAsText(f)
    e.target.value = ''
  }

  async function handleGenerate() {
    if (!canSubmit) return
    setError(null)
    setSubmitting(true)
    try {
      const bgValue = bgKind === 'color' ? bgColor : bgAssetPath.trim()
      if (bgKind !== 'color' && !bgValue) {
        setError(vi ? 'Chưa chọn ảnh/video nền.' : 'Pick a background image/video.')
        setSubmitting(false)
        return
      }
      const payload: RenderRequest = {
        source_mode: 'local',
        source_video_path: '',
        render_format: 'content',
        content_script: script.trim(),
        content_background_kind: bgKind,
        content_background_value: bgValue,
        content_visual_provider: 'local',
        output_dir: outputDir.trim() || 'output',
        aspect_ratio: RATIO_INFO[ratio].api,
        target_duration: targetDuration,
        add_subtitle: subEnabled,
        subtitle_style: subStyle,
        // Content narration always runs; voice_enabled stays false so the BE
        // voice validator is skipped, but the content path reads these directly.
        voice_language: voiceLang,
        voice_gender: voiceGender,
        tts_engine: ttsEngine,
        ai_provider: 'gemini',
      }
      const id = await submitRender(payload)
      setJobId(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (jobId) {
    return <ContentMonitor jobId={jobId} onNew={() => { setJobId(null); setError(null) }} vi={vi} t={t} />
  }

  return (
    <div style={S.screen}>
      <div style={S.header}>
        <h1 style={S.h1}>{vi ? 'Content Studio' : 'Content Studio'}</h1>
        <p style={S.sub}>
          {vi
            ? 'Tạo video từ kịch bản văn bản — AI lập kế hoạch cảnh, lời kể và phụ đề. Không cần video nguồn.'
            : 'Turn a text script into a video — AI plans scenes, narration and subtitles. No source footage needed.'}
        </p>
      </div>

      <div style={S.grid}>
        {/* ── Script ─────────────────────────────────────────────────── */}
        <section style={S.card}>
          <div style={S.cardHd}>
            <span style={S.cardTitle}>{vi ? 'Kịch bản' : 'Script'}</span>
            <span style={S.count}>{charCount} {vi ? 'ký tự' : 'chars'}</span>
          </div>
          <textarea
            style={S.textarea}
            value={script}
            onChange={(e) => setScript(e.target.value)}
            placeholder={vi
              ? 'Dán kịch bản / bài viết / tin tức ở đây…\n\nVí dụ: "Hôm nay chúng ta tìm hiểu vì sao Napoleon thất bại ở Waterloo."'
              : 'Paste your script / article / news here…\n\ne.g. "Today we explore why Napoleon lost at Waterloo."'}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={S.btnGhost} onClick={() => fileRef.current?.click()}>
              {vi ? 'Nhập .txt / .md' : 'Import .txt / .md'}
            </button>
            {script && (
              <button style={S.btnGhost} onClick={() => setScript('')}>
                {vi ? 'Xoá' : 'Clear'}
              </button>
            )}
            <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" hidden onChange={importFile} />
          </div>
        </section>

        {/* ── Config ─────────────────────────────────────────────────── */}
        <section style={S.card}>
          <div style={S.cardHd}><span style={S.cardTitle}>{vi ? 'Cấu hình' : 'Configuration'}</span></div>

          <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
            <div style={S.segRow}>
              {RATIOS.map((r) => (
                <button key={r} style={seg(ratio === r)} onClick={() => setRatio(r)}>
                  {RATIO_INFO[r].label}
                </button>
              ))}
            </div>
          </Field>

          <Field label={vi ? 'Thời lượng mục tiêu (giây)' : 'Target duration (sec)'}>
            <input type="number" min={15} max={600} style={S.input}
              value={targetDuration}
              onChange={(e) => setTargetDuration(Math.max(15, Math.min(600, Number(e.target.value) || 90)))} />
          </Field>

          <Field label={vi ? 'Nền' : 'Background'}>
            <div style={S.segRow}>
              {(['color', 'image', 'video'] as BgKind[]).map((k) => (
                <button key={k} style={seg(bgKind === k)} onClick={() => setBgKind(k)}>
                  {k === 'color' ? (vi ? 'Màu' : 'Color') : k === 'image' ? (vi ? 'Ảnh' : 'Image') : 'Video'}
                </button>
              ))}
            </div>
            {bgKind === 'color' ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                <input type="color" value={bgColor} onChange={(e) => setBgColor(e.target.value)}
                  style={{ width: 40, height: 32, border: 'none', background: 'none', cursor: 'pointer' }} />
                <input style={S.input} value={bgColor} onChange={(e) => setBgColor(e.target.value)} />
              </div>
            ) : (
              <input style={{ ...S.input, marginTop: 8 }} value={bgAssetPath}
                onChange={(e) => setBgAssetPath(e.target.value)}
                placeholder={vi ? 'Đường dẫn file trên máy…' : 'Local file path…'} />
            )}
          </Field>

          <Field label={vi ? 'Giọng đọc' : 'Voice'}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <select style={S.input} value={voiceLang} onChange={(e) => setVoiceLang(e.target.value as typeof VOICE_LANGS[number])}>
                {VOICE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
              <select style={S.input} value={voiceGender} onChange={(e) => setVoiceGender(e.target.value as 'female' | 'male')}>
                <option value="female">{vi ? 'Nữ' : 'Female'}</option>
                <option value="male">{vi ? 'Nam' : 'Male'}</option>
              </select>
              <select style={S.input} value={ttsEngine} onChange={(e) => setTtsEngine(e.target.value as typeof TTS_ENGINES[number])}>
                {TTS_ENGINES.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
              </select>
            </div>
          </Field>

          <Field label={vi ? 'Phụ đề' : 'Subtitles'}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button style={seg(subEnabled)} onClick={() => setSubEnabled(!subEnabled)}>
                {subEnabled ? (vi ? 'Bật' : 'On') : (vi ? 'Tắt' : 'Off')}
              </button>
              {subEnabled && (
                <select style={S.input} value={subStyle} onChange={(e) => setSubStyle(e.target.value)}>
                  {SUB_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
            </div>
          </Field>

          <Field label={vi ? 'Thư mục lưu' : 'Save folder'}>
            <input style={S.input} value={outputDir} onChange={(e) => setOutputDir(e.target.value)}
              placeholder={vi ? 'Mặc định: output' : 'Default: output'} />
          </Field>
        </section>
      </div>

      <div style={S.footer}>
        {error && <span style={{ color: 'var(--fail)' }}>{error}</span>}
        <button style={{ ...S.btnPrimary, opacity: canSubmit ? 1 : 0.5, cursor: canSubmit ? 'pointer' : 'not-allowed' }}
          disabled={!canSubmit} onClick={handleGenerate}>
          {submitting ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Tạo video' : 'Generate Video')}
        </button>
      </div>
    </div>
  )
}

// ── Live monitor ──────────────────────────────────────────────────────────────

function ContentMonitor({ jobId, onNew, vi, t: _t }: { jobId: string; onNew: () => void; vi: boolean; t: (k: never) => string }) {
  const { stage, jobStatus, jobMessage, progress, liveParts, liveEvents, isTerminal, error } = useRenderSocket(jobId)
  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'

  const planEvent = useMemo(
    () => liveEvents.find((e) => (e as { event?: string }).event === 'content.plan.ready'),
    [liveEvents],
  )

  return (
    <div style={S.screen}>
      <div style={S.header}>
        <h1 style={S.h1}>{vi ? 'Đang tạo video…' : 'Rendering…'}</h1>
        <p style={S.sub}>{jobMessage || stage || ''}</p>
      </div>

      <section style={S.card}>
        <div style={S.cardHd}>
          <span style={S.cardTitle}>{vi ? 'Tiến độ' : 'Progress'}</span>
          <span style={S.count}>{pct}%</span>
        </div>
        <div style={S.barTrack}><div style={{ ...S.barFill, width: `${pct}%` }} /></div>
        <div style={{ fontSize: 12, color: 'var(--text-3, #999)', marginTop: 6 }}>
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>
          {planEvent && <> · {vi ? 'Kế hoạch AI đã sẵn sàng' : 'AI plan ready'}</>}
        </div>
      </section>

      {liveParts.length > 0 && (
        <section style={S.card}>
          <div style={S.cardHd}><span style={S.cardTitle}>{vi ? 'Cảnh' : 'Scenes'} ({liveParts.length})</span></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {liveParts.map((p) => (
              <div key={p.part_no} style={S.partRow}>
                <span>#{p.part_no}</span>
                <span style={{ flex: 1, color: 'var(--text-3, #999)' }}>{p.message || p.status}</span>
                <span style={{ color: statusColor(p.status) }}>{p.status} {p.progress_percent ? `${p.progress_percent}%` : ''}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {isTerminal && (
        <section style={{ ...S.card, borderColor: ok ? 'var(--ok, #22c55e)' : 'var(--fail, #ef4444)' }}>
          <div style={S.cardHd}>
            <span style={{ ...S.cardTitle, color: ok ? 'var(--ok, #22c55e)' : 'var(--fail, #ef4444)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-2, #ccc)' }}>{jobMessage || error || ''}</p>
          <button style={S.btnPrimary} onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</button>
        </section>
      )}

      {!isTerminal && (
        <div style={{ marginTop: 12 }}>
          <button style={S.btnGhost} onClick={onNew}>{vi ? 'Tạo cái khác' : 'Start another'}</button>
        </div>
      )}
    </div>
  )
}

// ── small helpers ──────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2, #ccc)', marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

function statusColor(status: string): string {
  if (status === 'done') return 'var(--ok, #22c55e)'
  if (status === 'failed') return 'var(--fail, #ef4444)'
  if (status === 'rendering') return 'var(--accent-primary, #8b5cf6)'
  return 'var(--text-3, #999)'
}

function seg(on: boolean): React.CSSProperties {
  return {
    flex: 1, padding: '8px 10px', textAlign: 'center', cursor: 'pointer',
    borderRadius: 8, fontSize: 13, fontWeight: 600, border: '1px solid var(--border-subtle, #333)',
    background: on ? 'var(--accent-subtle, rgba(139,92,246,.18))' : 'transparent',
    color: on ? 'var(--accent-primary, #8b5cf6)' : 'var(--text-2, #ccc)',
  }
}

const S: Record<string, React.CSSProperties> = {
  screen: { padding: 'var(--space-6, 24px)', maxWidth: 980, margin: '0 auto', width: '100%' },
  header: { marginBottom: 20 },
  h1: { fontSize: 22, fontWeight: 700, margin: 0, color: 'var(--text-1, #fff)' },
  sub: { fontSize: 13, color: 'var(--text-3, #999)', marginTop: 6, maxWidth: 640, lineHeight: 1.5 },
  grid: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 16, alignItems: 'start' },
  card: {
    background: 'var(--surface-card, #17171c)', border: '1px solid var(--border-subtle, #2a2a30)',
    borderRadius: 12, padding: 16, marginBottom: 16,
  },
  cardHd: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  cardTitle: { fontSize: 14, fontWeight: 700, color: 'var(--text-1, #fff)' },
  count: { fontSize: 12, color: 'var(--text-3, #999)' },
  textarea: {
    width: '100%', minHeight: 220, resize: 'vertical', padding: 12, borderRadius: 8,
    border: '1px solid var(--border-subtle, #2a2a30)', background: 'var(--surface-input, #0f0f13)',
    color: 'var(--text-1, #fff)', fontSize: 14, lineHeight: 1.6, fontFamily: 'inherit', marginBottom: 10,
  },
  input: {
    padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle, #2a2a30)',
    background: 'var(--surface-input, #0f0f13)', color: 'var(--text-1, #fff)', fontSize: 13, minWidth: 0, flex: 1,
  },
  segRow: { display: 'flex', gap: 6 },
  footer: { display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16, marginTop: 8 },
  btnPrimary: {
    padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 700,
    color: '#fff', background: 'var(--brand-gradient, linear-gradient(135deg,#8b5cf6,#6366f1))',
  },
  btnGhost: {
    padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
    border: '1px solid var(--border-subtle, #2a2a30)', background: 'transparent', color: 'var(--text-2, #ccc)',
  },
  barTrack: { height: 8, borderRadius: 4, background: 'var(--surface-input, #0f0f13)', overflow: 'hidden' },
  barFill: { height: '100%', background: 'var(--brand-gradient, linear-gradient(90deg,#8b5cf6,#6366f1))', transition: 'width .3s ease' },
  partRow: { display: 'flex', gap: 10, alignItems: 'center', fontSize: 12, padding: '4px 0' },
}
