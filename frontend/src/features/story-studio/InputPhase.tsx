/**
 * InputPhase.tsx — Story Studio phase 1: paste a chapter + configure, then
 * "Analyze". Reuses the Content Studio design language (cs- classes + shared
 * SectionCard / Field / RatioPreview) so it matches the app, with real
 * validation (char count, required save folder, disabled CTA).
 */
import React, { useRef } from 'react'
import { Button } from '../../components/ui/Button'
import { HeroHeader, SectionCard, Field, RatioPreview, seg } from '../content-studio/shared'
import {
  STORY_LANGS, STORY_SUB_STYLES, ART_STYLE_PRESETS, READING_PACES,
  type StoryConfig,
} from './types'

const PACE_LABEL: Record<string, { vi: string; en: string }> = {
  slow: { vi: 'Chậm', en: 'Slow' }, normal: { vi: 'Vừa', en: 'Normal' }, fast: { vi: 'Nhanh', en: 'Fast' },
}

export function InputPhase({ vi, chapter, setChapter, cfg, setKey, busy, error, onAnalyze, hasPicker, pickOutputDir }: {
  vi: boolean
  chapter: string; setChapter: (s: string) => void
  cfg: StoryConfig; setKey: <K extends keyof StoryConfig>(k: K, v: StoryConfig[K]) => void
  busy: boolean; error: string | null; onAnalyze: () => void
  hasPicker: boolean; pickOutputDir: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const charCount = chapter.trim().length

  function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => setChapter(String(r.result || ''))
    r.readAsText(f)
    e.target.value = ''
  }

  return (
    <div className="cs-screen">
      <HeroHeader icon="✨" title="Story Studio"
        subtitle={vi
          ? 'Dán nguyên một chương truyện — AI hiểu truyện, dựng storyboard, sinh hình ảnh nhất quán & lời kể để bạn duyệt trước khi render.'
          : 'Paste a whole chapter — the AI understands the story, builds a storyboard, generates consistent images & narration for you to review before rendering.'} />

      <div className="cs-grid">
        <section className="cs-card cs-card--flush">
          <div className="cs-card-hd">
            <span className="cs-card-title">{vi ? 'Chương truyện' : 'Chapter'}</span>
            <span className="cs-count">{charCount} {vi ? 'ký tự' : 'chars'}</span>
          </div>
          <textarea className="cs-textarea" value={chapter} onChange={(e) => setChapter(e.target.value)}
            placeholder={vi
              ? 'Dán nội dung chương…\n\nVí dụ: "Chương 186 — Hàn Phong tỉnh dậy giữa Vạn Kiếm Tông…"'
              : 'Paste the chapter…\n\ne.g. "Chapter 186 — Han Phong wakes inside the Ten-Thousand Swords Sect…"'} />
          <div className="cs-row">
            <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()}>{vi ? 'Nhập .txt / .md' : 'Import .txt / .md'}</Button>
            {chapter && <Button variant="ghost" size="sm" onClick={() => setChapter('')}>{vi ? 'Xoá' : 'Clear'}</Button>}
            <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" hidden onChange={importFile} />
          </div>
        </section>

        <div className="cs-config-col">
          <SectionCard icon="🎨" title={vi ? 'Định dạng' : 'Format'}>
            <Field label={vi ? 'Ngôn ngữ truyện' : 'Story language'}>
              <select className="cs-input" value={cfg.language} onChange={(e) => setKey('language', e.target.value as StoryConfig['language'])}>
                {STORY_LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </Field>
            <Field label={vi ? 'Phong cách tranh' : 'Art style'}>
              <input className="cs-input" list="st-art-styles" value={cfg.artStyle}
                onChange={(e) => setKey('artStyle', e.target.value)}
                placeholder={vi ? 'wuxia / anime / realistic… (để trống = AI tự chọn)' : 'wuxia / anime / realistic… (blank = AI decides)'} />
              <datalist id="st-art-styles">
                {ART_STYLE_PRESETS.map((s) => <option key={s} value={s} />)}
              </datalist>
            </Field>
            <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
              <RatioPreview value={cfg.ratio} onChange={(r) => setKey('ratio', r)} />
            </Field>
            <Field label={vi ? 'Nhịp kể' : 'Reading pace'}>
              <div className="cs-seg-row">
                {READING_PACES.map((p) => (
                  <button key={p} className={seg(cfg.readingPace === p)} onClick={() => setKey('readingPace', p)}>
                    {vi ? PACE_LABEL[p].vi : PACE_LABEL[p].en}
                  </button>
                ))}
              </div>
              <div className="cs-hint">{vi ? 'Thời lượng video tự suy ra từ độ dài truyện; nhịp kể chỉ chỉnh tốc độ đọc.' : 'Duration derives from the chapter length; pace only tunes reading speed.'}</div>
            </Field>
          </SectionCard>

          <SectionCard icon="📚" title={vi ? 'Bộ truyện (tuỳ chọn)' : 'Series (optional)'}>
            <Field label={vi ? 'Mã series — nhớ nhân vật xuyên chương' : 'Series id — remembers characters across chapters'}>
              <input className="cs-input" value={cfg.seriesId} onChange={(e) => setKey('seriesId', e.target.value)}
                placeholder={vi ? 'vd: tienhiep-abc (để trống = truyện lẻ)' : 'e.g. tienhiep-abc (blank = one-off)'} />
            </Field>
            <Field label={vi ? 'Số chương' : 'Chapter no.'}>
              <input className="cs-input" type="number" min={0} value={cfg.chapterNo || ''}
                onChange={(e) => setKey('chapterNo', Math.max(0, Number(e.target.value) || 0))} />
            </Field>
            <Field label={vi ? 'Trần chi phí ảnh AI ($)' : 'AI image budget cap ($)'}>
              <input className="cs-input" type="number" min={0} step={0.05} value={cfg.aiBudget || ''}
                onChange={(e) => setKey('aiBudget', Math.max(0, Number(e.target.value) || 0))}
                placeholder={vi ? '0 = không giới hạn' : '0 = unlimited'} />
              <div className="cs-hint">{vi ? 'Vượt trần → các shot sau tự hạ chất lượng ảnh / dùng nền. 0 = không giới hạn.' : 'Once exceeded, later shots downgrade quality / use a background. 0 = unlimited.'}</div>
            </Field>
          </SectionCard>

          <SectionCard icon="💬" title={vi ? 'Phụ đề' : 'Subtitles'}>
            <div className="cs-row">
              <button className={seg(cfg.subEnabled)} onClick={() => setKey('subEnabled', !cfg.subEnabled)}>
                {cfg.subEnabled ? (vi ? 'Bật' : 'On') : (vi ? 'Tắt' : 'Off')}
              </button>
              {cfg.subEnabled && (
                <select className="cs-input" value={cfg.subStyle} onChange={(e) => setKey('subStyle', e.target.value)}>
                  {STORY_SUB_STYLES.map((s) => <option key={s} value={s}>{s === 'auto' ? (vi ? 'Tự động (AI chọn)' : 'Auto (AI picks)') : s}</option>)}
                </select>
              )}
              {cfg.subEnabled && (
                <label className="cs-mini-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  <input type="checkbox" checked={cfg.wordByWord} onChange={(e) => setKey('wordByWord', e.target.checked)} />
                  {vi ? 'Chữ động (Whisper)' : 'Word-by-word (Whisper)'}
                </label>
              )}
            </div>
            {cfg.subEnabled && cfg.wordByWord && (
              <div className="cs-hint">{vi ? '⚠ Chữ động chạy Whisper cho MỖI shot — chương dài sẽ render chậm hơn nhiều.' : '⚠ Word-by-word runs Whisper per shot — a long chapter renders much slower.'}</div>
            )}
          </SectionCard>

          <SectionCard icon="💾" title={vi ? 'Lưu' : 'Save'}>
            <Field label={vi ? 'Thư mục lưu *' : 'Save folder *'}>
              <div className="cs-row">
                <input className="cs-input" value={cfg.outputDir} onChange={(e) => setKey('outputDir', e.target.value)}
                  placeholder={vi ? 'Chọn nơi lưu video…' : 'Choose where to save…'} />
                {hasPicker && <Button variant="secondary" size="sm" onClick={pickOutputDir}>{vi ? '📁 Chọn…' : '📁 Browse…'}</Button>}
              </div>
              {!cfg.outputDir.trim() && (
                <div className="cs-hint">{vi ? '⚠ Chưa chọn thư mục — bắt buộc trước khi render.' : '⚠ No folder chosen — required before rendering.'}</div>
              )}
            </Field>
          </SectionCard>
        </div>
      </div>

      <div className="cs-footer">
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={!charCount || busy} onClick={onAnalyze}>
          {busy ? (vi ? 'AI đang phân tích…' : 'AI analyzing…') : (vi ? '✨ Phân tích truyện →' : '✨ Analyze chapter →')}
        </Button>
      </div>
    </div>
  )
}
