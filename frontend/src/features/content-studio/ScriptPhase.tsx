/**
 * ScriptPhase.tsx — Content Studio phase 1 (script + config) + the AI Director
 * planning overlay (CM-9 split). Extracted verbatim from ContentStudio.tsx.
 */
import React, { useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import type { ContentProjectSummary, VisualProviderInfo } from '../../api/content'
import { putDefaultOutputDir } from '../../api/outputDir'
import { Stepper, HeroHeader, SectionCard, Field, RatioPreview, DurationSlider, seg } from './shared'
import { VOICE_LANGS, TTS_ENGINES, SUB_STYLES, type Config, type BgKind, type ImagenTier } from './types'

export function ScriptPhase({ vi, script, setScript, cfg, setCfgKey, busy, error, onGenerate, drafts, onOpenDraft, providerAvail }: {
  vi: boolean; script: string; setScript: (s: string) => void
  cfg: Config; setCfgKey: <K extends keyof Config>(k: K, v: Config[K]) => void
  busy: boolean; error: string | null; onGenerate: () => void
  drafts: ContentProjectSummary[]; onOpenDraft: (id: string) => void
  providerAvail: Record<string, VisualProviderInfo> | null
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  // P3.1: per-source availability tag for the Visual-source dropdown.
  const availTag = (p: string): string => {
    const a = providerAvail?.[p]
    if (!a) return ''
    if (a.available) return a.free ? (vi ? ' — ✓ miễn phí' : ' — ✓ free') : (vi ? ' — ✓ sẵn sàng' : ' — ✓ ready')
    return vi ? ' — cần key' : ' — needs key'
  }
  const charCount = script.trim().length
  const hasPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickDirectory
  const [defaultSaved, setDefaultSaved] = useState(false)

  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) { setCfgKey('outputDir', dir); setDefaultSaved(false) }
  }
  async function saveAsDefaultDir() {
    if (!cfg.outputDir.trim()) return
    try { await putDefaultOutputDir(cfg.outputDir.trim()); setDefaultSaved(true) } catch { /* ignore */ }
  }

  function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => setScript(String(r.result || ''))
    r.readAsText(f)
    e.target.value = ''
  }

  return (
    <div className="cs-screen">
      <Stepper vi={vi} step={1} />
      <HeroHeader icon="✨" title="Content Studio"
        subtitle={vi
          ? 'Biến kịch bản thành video — AI lo cảnh, lời kể & hình ảnh để bạn duyệt trước khi render.'
          : 'Turn a script into a video — the AI drafts scenes, narration & visuals for you to review before rendering.'} />

      {drafts.length > 0 && (
        <section className="cs-card">
          <div className="cs-card-hd"><span className="cs-card-title">{vi ? 'Bản nháp gần đây' : 'Recent drafts'}</span></div>
          <div className="cs-draft-row">
            {drafts.slice(0, 8).map((d) => (
              <button key={d.id} className="cs-draft-chip" onClick={() => onOpenDraft(d.id)} title={d.updated_at}>
                <b>{d.title || (vi ? 'Không tên' : 'Untitled')}</b>
                <span className="cs-draft-meta">
                  {' · '}{d.scenes} {vi ? 'cảnh' : 'sc'}{d.status === 'rendered' ? ' ✓' : ''}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="cs-grid">
        <section className="cs-card cs-card--flush">
          <div className="cs-card-hd">
            <span className="cs-card-title">{vi ? 'Kịch bản' : 'Script'}</span>
            <span className="cs-count">{charCount} {vi ? 'ký tự' : 'chars'}</span>
          </div>
          <textarea className="cs-textarea" value={script} onChange={(e) => setScript(e.target.value)}
            placeholder={vi
              ? 'Dán kịch bản / bài viết / tin tức…\n\nVí dụ: "Hôm nay chúng ta tìm hiểu vì sao Napoleon thất bại ở Waterloo."'
              : 'Paste your script / article / news…\n\ne.g. "Today we explore why Napoleon lost at Waterloo."'} />
          <div className="cs-row">
            <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()}>{vi ? 'Nhập .txt / .md' : 'Import .txt / .md'}</Button>
            {script && <Button variant="ghost" size="sm" onClick={() => setScript('')}>{vi ? 'Xoá' : 'Clear'}</Button>}
            <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" hidden onChange={importFile} />
          </div>
        </section>

        <div className="cs-config-col">
          <SectionCard icon="🎨" title={vi ? 'Định dạng' : 'Format'}>
            <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
              <RatioPreview value={cfg.ratio} onChange={(r) => setCfgKey('ratio', r)} />
            </Field>
            <Field label={vi ? 'Thời lượng mục tiêu' : 'Target duration'}>
              <DurationSlider value={cfg.targetDuration} onChange={(v) => setCfgKey('targetDuration', v)} />
            </Field>
          </SectionCard>

          <SectionCard icon="🖼️" title={vi ? 'Hình ảnh' : 'Visuals'}>
            <Field label={vi ? 'Nguồn hình ảnh' : 'Visual source'}>
              <select className="cs-input" value={cfg.visualProvider} onChange={(e) => setCfgKey('visualProvider', e.target.value as Config['visualProvider'])}>
                <option value="local">{(vi ? 'Nền tự chọn (offline)' : 'Chosen background (offline)') + availTag('local')}</option>
                <option value="stock">{(vi ? 'Ảnh Stock (Pexels/Pixabay)' : 'Stock images (Pexels/Pixabay)') + availTag('stock')}</option>
                <option value="ai_image_free">{(vi ? 'Ảnh AI (Pollinations — miễn phí)' : 'AI Image (Pollinations — free)') + availTag('ai_image_free')}</option>
                <option value="ai_image">{(vi ? 'Ảnh AI (Imagen/DALL·E, trả phí)' : 'AI Image (Imagen/DALL·E, paid)') + availTag('ai_image')}</option>
                <option value="ai_video">{(vi ? 'Video AI (Veo, trả phí, chậm)' : 'AI Video (Veo, paid, slow)') + availTag('ai_video')}</option>
              </select>
              {providerAvail?.stock?.available && cfg.visualProvider === 'local' && (
                <div className="cs-hint">
                  {vi ? '💡 Bạn đã có key Pexels — chọn "Ảnh Stock" để có ảnh thật miễn phí thay nền màu.' : '💡 Pexels key detected — pick "Stock images" for free real footage instead of a solid background.'}
                </div>
              )}
              {cfg.visualProvider === 'ai_image_free' && (
                <div className="cs-hint">
                  {vi
                    ? '⚠️ Prompt từng cảnh (do AI viết, bám nội dung) được gửi tới dịch vụ bên thứ 3 (Pollinations) để tạo ảnh. Miễn phí, không cần key.'
                    : '⚠️ Each scene\'s AI-written (story-grounded) prompt is sent to a third-party service (Pollinations) to generate the image. Free, no key.'}
                </div>
              )}
              {cfg.visualProvider !== 'local' && (
                <div className="cs-hint">
                  {vi ? 'Mỗi cảnh lấy ảnh theo nội dung. Thiếu key/mạng → tự dùng nền đã chọn.' : 'Each scene fetches an image by its content. Missing key/network → falls back to your background.'}
                </div>
              )}
            </Field>
            {cfg.visualProvider === 'ai_image' && (
              <Field label={vi ? 'Chất lượng ảnh AI' : 'AI image quality'}>
                <div className="cs-seg-row">
                  {(['fast', 'standard', 'ultra'] as ImagenTier[]).map((tier) => (
                    <button key={tier} className={seg(cfg.imagenTier === tier)} onClick={() => setCfgKey('imagenTier', tier)}>
                      {tier === 'fast' ? (vi ? 'Nhanh' : 'Fast') : tier === 'standard' ? (vi ? 'Tiêu chuẩn' : 'Standard') : 'Ultra'}
                    </button>
                  ))}
                </div>
                <div className="cs-hint">
                  {cfg.imagenTier === 'fast'
                    ? (vi ? 'Imagen 4 Fast — cần key có Imagen 4.' : 'Imagen 4 Fast — needs Imagen 4 access.')
                    : cfg.imagenTier === 'ultra'
                    ? (vi ? 'Imagen 4 Ultra — cao nhất, cần key có Imagen 4.' : 'Imagen 4 Ultra — top quality, needs Imagen 4 access.')
                    : (vi ? 'Imagen 3 (mặc định, phổ biến). Cần key Gemini có bật billing.' : 'Imagen 3 (default, broadly available). Needs a billing-enabled Gemini key.')}
                </div>
              </Field>
            )}
            {(cfg.visualProvider === 'ai_image' || cfg.visualProvider === 'ai_video') && (
              <Field label={vi ? 'Trần chi phí AI ($)' : 'AI budget cap ($)'}>
                <input
                  className="cs-input" type="number" min={0} step={0.05}
                  value={cfg.aiBudget || ''}
                  onChange={(e) => setCfgKey('aiBudget', Math.max(0, Number(e.target.value) || 0))}
                  placeholder={vi ? '0 = không giới hạn' : '0 = unlimited'}
                />
                <div className="cs-hint">
                  {vi
                    ? 'Ước tính tương đối — khi vượt trần, các cảnh sau tự hạ về nguồn rẻ hơn/miễn phí. 0 = không giới hạn.'
                    : 'Relative estimate — once exceeded, later scenes downgrade to a cheaper/free source. 0 = unlimited.'}
                </div>
              </Field>
            )}
            <Field label={vi ? 'Nền (khi không có ảnh)' : 'Background (fallback)'}>
              <div className="cs-seg-row">
                {(['color', 'image', 'video'] as BgKind[]).map((k) => (
                  <button key={k} className={seg(cfg.bgKind === k)} onClick={() => setCfgKey('bgKind', k)}>
                    {k === 'color' ? (vi ? 'Màu' : 'Color') : k === 'image' ? (vi ? 'Ảnh' : 'Image') : 'Video'}
                  </button>
                ))}
              </div>
              {cfg.bgKind === 'color' ? (
                <div className="cs-row cs-row--top">
                  <input type="color" className="cs-color-swatch" value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} />
                  <input className="cs-input" value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} />
                </div>
              ) : (
                <input className="cs-input cs-row--top" value={cfg.bgAssetPath} onChange={(e) => setCfgKey('bgAssetPath', e.target.value)}
                  placeholder={vi ? 'Đường dẫn file trên máy…' : 'Local file path…'} />
              )}
            </Field>
          </SectionCard>

          <SectionCard icon="🎙️" title={vi ? 'Giọng & Phụ đề' : 'Voice & Subtitles'}>
            <Field label={vi ? 'Giọng đọc' : 'Voice'}>
              <div className="cs-row">
                <select className="cs-input" value={cfg.voiceLang} onChange={(e) => setCfgKey('voiceLang', e.target.value as typeof VOICE_LANGS[number])}>
                  {VOICE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
                <select className="cs-input" value={cfg.voiceGender} onChange={(e) => setCfgKey('voiceGender', e.target.value as 'female' | 'male')}>
                  <option value="female">{vi ? 'Nữ' : 'Female'}</option>
                  <option value="male">{vi ? 'Nam' : 'Male'}</option>
                </select>
                <select className="cs-input" value={cfg.ttsEngine} onChange={(e) => setCfgKey('ttsEngine', e.target.value as typeof TTS_ENGINES[number])}>
                  {TTS_ENGINES.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
                </select>
              </div>
            </Field>
            <Field label={vi ? 'Phụ đề' : 'Subtitles'}>
              <div className="cs-row">
                <button className={seg(cfg.subEnabled)} onClick={() => setCfgKey('subEnabled', !cfg.subEnabled)}>{cfg.subEnabled ? (vi ? 'Bật' : 'On') : (vi ? 'Tắt' : 'Off')}</button>
                {cfg.subEnabled && (
                  <select className="cs-input" value={cfg.subStyle} onChange={(e) => setCfgKey('subStyle', e.target.value)}>
                    {SUB_STYLES.map((s) => <option key={s} value={s}>{s === 'auto' ? (vi ? 'Tự động (AI chọn)' : 'Auto (AI picks)') : s}</option>)}
                  </select>
                )}
                {cfg.subEnabled && (
                  <label className="cs-mini-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <input type="checkbox" checked={cfg.wordByWord} onChange={(e) => setCfgKey('wordByWord', e.target.checked)} />
                    {vi ? 'Chữ động (Whisper)' : 'Word-by-word (Whisper)'}
                  </label>
                )}
              </div>
              {cfg.subEnabled && cfg.wordByWord && (
                <div className="cs-hint">
                  {vi ? '⚠ Chữ động chạy Whisper cho MỖI cảnh — render chậm hơn đáng kể. Tắt để phụ đề theo câu (nhanh hơn).' : '⚠ Word-by-word runs Whisper per scene — noticeably slower. Turn off for faster sentence-level subtitles.'}
                </div>
              )}
            </Field>
          </SectionCard>

          <SectionCard icon="⚙️" title={vi ? 'Khác' : 'More'}>
            <Field label={vi ? 'Nhạc nền (tuỳ chọn)' : 'Background music (optional)'}>
              <input className="cs-input" value={cfg.bgmPath} onChange={(e) => setCfgKey('bgmPath', e.target.value)}
                placeholder={vi ? 'Đường dẫn file nhạc… (tự ducking dưới giọng đọc)' : 'Music file path… (auto-ducked under narration)'} />
            </Field>
            <Field label={vi ? 'Thư mục lưu *' : 'Save folder *'}>
              <div className="cs-row">
                <input className="cs-input" value={cfg.outputDir}
                  onChange={(e) => { setCfgKey('outputDir', e.target.value); setDefaultSaved(false) }}
                  placeholder={vi ? 'Chọn nơi lưu video…' : 'Choose where to save…'} />
                {hasPicker && (
                  <Button variant="secondary" size="sm" onClick={pickOutputDir}>{vi ? '📁 Chọn…' : '📁 Browse…'}</Button>
                )}
              </div>
              {cfg.outputDir.trim() ? (
                <div className="cs-row cs-row--top">
                  <Button variant="ghost" size="sm" disabled={defaultSaved} onClick={saveAsDefaultDir}>
                    {defaultSaved ? (vi ? '✓ Đã đặt mặc định' : '✓ Set as default') : (vi ? 'Đặt làm mặc định' : 'Set as default')}
                  </Button>
                </div>
              ) : (
                <div className="cs-hint">{vi ? '⚠ Chưa chọn thư mục — bắt buộc trước khi render.' : '⚠ No folder chosen — required before rendering.'}</div>
              )}
              {!hasPicker && (
                <div className="cs-hint">{vi ? 'Nút chọn thư mục chỉ có trong app desktop — nhập đường dẫn tay khi dùng trình duyệt.' : 'The folder picker is desktop-app only — type a path when using the browser.'}</div>
              )}
            </Field>
          </SectionCard>
        </div>
      </div>

      <div className="cs-footer">
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!charCount || busy} onClick={onGenerate}>
          {busy ? (vi ? 'AI đang phân tích…' : 'AI analyzing…') : (vi ? '✨ Tạo kế hoạch (AI) →' : '✨ Generate Content Plan →')}
        </Button>
      </div>

      {busy && <AiDirectorConsole vi={vi} />}
    </div>
  )
}

// ── AI Director console (planning overlay, P5) ──────────────────────────────

const _DIRECTOR_STEPS_VI = [
  'Đọc & hiểu kịch bản',
  'Xác định chủ đề · giọng · khán giả',
  'Chia cảnh theo ý nghĩa',
  'Viết lời kể + cảm xúc + nhịp đọc',
  'Cân chỉnh thời lượng',
]
const _DIRECTOR_STEPS_EN = [
  'Reading & understanding the script',
  'Detecting topic · tone · audience',
  'Splitting into meaningful scenes',
  'Writing narration + emotion + pacing',
  'Fitting the duration',
]

// Shown while POST /api/content/plan is in flight. /plan is a single synchronous
// call with no sub-events, so we walk the AI's REAL internal steps on a timer
// and hold on the last one until the plan returns (this component unmounts) —
// honest progress framing, never a fake percentage.
function AiDirectorConsole({ vi }: { vi: boolean }) {
  const steps = vi ? _DIRECTOR_STEPS_VI : _DIRECTOR_STEPS_EN
  const [step, setStep] = useState(0)
  React.useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 1300)
    return () => clearInterval(id)
  }, [steps.length])
  return (
    <div className="cs-director-overlay">
      <div className="cs-director">
        <div className="cs-director-hd">
          <span className="cs-director-orb" />
          <div>
            <div className="cs-director-title">AI Content Director</div>
            <div className="cs-director-sub">{vi ? 'Đang lập kế hoạch video…' : 'Planning your video…'}</div>
          </div>
        </div>
        <ol className="cs-director-steps">
          {steps.map((label, i) => {
            const state = i < step ? 'done' : i === step ? 'active' : 'pending'
            return (
              <li key={i} className={`cs-director-step is-${state}`}>
                <span className="cs-director-mark">
                  {state === 'done' ? '✓' : state === 'active' ? <span className="cs-feed-spinner" /> : ''}
                </span>
                <span>{label}</span>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
