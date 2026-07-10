/**
 * InputScreen — Story v2 phase 1 (source A paste / B idea + minimal config).
 *
 * F1 scaffold: functional-minimal so the flow works end-to-end. F2 polishes
 * (duration presets, genre helper text, validation, templates). Uses the Studio
 * BASE (F0) only — no content-studio import.
 */
import { StudioCard, StudioField, SegRow, RatioPicker } from '../../components/studio'
import {
  STORY_LANGS, ART_STYLE_PRESETS, GENRE_PRESETS, ASPECTS,
  type StoryConfig, type StorySource, type StoryLang, type Aspect,
} from './types'

export function InputScreen({ vi, cfg, setKey, busy, ready, hasPicker, pickOutputDir, onGenerate }: {
  vi: boolean
  cfg: StoryConfig
  setKey: <K extends keyof StoryConfig>(k: K, v: StoryConfig[K]) => void
  busy: boolean
  ready: boolean
  hasPicker: boolean
  pickOutputDir: () => void
  onGenerate: () => void
}) {
  const mins = Math.round(cfg.durationSec / 60)
  return (
    <>
      <StudioCard icon="✍️" title={vi ? 'Nguồn truyện' : 'Story source'}>
        <SegRow<StorySource>
          ariaLabel={vi ? 'Nguồn' : 'Source'}
          value={cfg.source}
          onChange={(v) => setKey('source', v)}
          options={[
            { value: 'paste', label: vi ? 'Truyện có sẵn' : 'Paste chapter', icon: '📄' },
            { value: 'idea', label: vi ? 'Sáng tác từ ý tưởng' : 'From an idea', icon: '💡' },
          ]}
        />

        {cfg.source === 'paste' ? (
          <StudioField label={vi ? 'Nội dung truyện' : 'Chapter text'}
            hint={vi ? 'Dán cả chương — AI tự hiểu, chia phân đoạn, chọn giọng.'
                     : 'Paste the whole chapter — the AI segments and casts voices.'}>
            <textarea className="st-textarea" rows={12}
              placeholder={vi ? 'Dán nội dung chương truyện ở đây…' : 'Paste the chapter here…'}
              value={cfg.chapterText} onChange={(e) => setKey('chapterText', e.target.value)} />
          </StudioField>
        ) : (
          <>
            <StudioField label={vi ? 'Ý tưởng' : 'Idea'}
              hint={vi ? 'Mô tả ngắn — AI sẽ tự sáng tác truyện theo thời lượng.'
                       : 'A short brief — the AI authors the story to the target length.'}>
              <textarea className="st-textarea" rows={5}
                placeholder={vi ? 'VD: Kiếm khách trẻ báo thù môn phái…' : 'e.g. A young swordsman seeks revenge…'}
                value={cfg.idea} onChange={(e) => setKey('idea', e.target.value)} />
            </StudioField>
            <div className="st-grid-2">
              <StudioField label={`${vi ? 'Thời lượng' : 'Duration'}: ${mins} ${vi ? 'phút' : 'min'}`}>
                <input className="st-range" type="range" min={1} max={15} step={1}
                  value={mins} onChange={(e) => setKey('durationSec', Math.max(1, Number(e.target.value) || 1) * 60)} />
              </StudioField>
              <StudioField label={vi ? 'Thể loại' : 'Genre'}>
                <select className="st-select" value={cfg.genre} onChange={(e) => setKey('genre', e.target.value)}>
                  <option value="">{vi ? '— AI tự chọn —' : '— AI decides —'}</option>
                  {GENRE_PRESETS.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </StudioField>
            </div>
          </>
        )}
      </StudioCard>

      <StudioCard icon="⚙️" title={vi ? 'Cấu hình' : 'Config'}>
        <div className="st-grid-2">
          <StudioField label={vi ? 'Ngôn ngữ' : 'Language'}>
            <SegRow<StoryLang>
              value={cfg.language} onChange={(v) => setKey('language', v)}
              options={STORY_LANGS.map((l) => ({ value: l.code, label: l.label }))}
            />
          </StudioField>
          <StudioField label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
            <RatioPicker value={cfg.aspect}
              onChange={(r) => setKey('aspect', r as Aspect)}
              options={ASPECTS.map((a) => ({ value: a, label: a }))} />
          </StudioField>
        </div>
        <StudioField label={vi ? 'Phong cách hình (tùy chọn)' : 'Art style (optional)'}>
          <input className="st-input" list="story-art-styles" value={cfg.artStyle}
            placeholder={vi ? '— AI tự chọn —' : '— AI decides —'}
            onChange={(e) => setKey('artStyle', e.target.value)} />
          <datalist id="story-art-styles">
            {ART_STYLE_PRESETS.map((s) => <option key={s} value={s} />)}
          </datalist>
        </StudioField>
        <StudioField label={vi ? 'Thư mục lưu' : 'Output folder'}>
          <div className="st-row">
            <input className="st-input" value={cfg.outputDir}
              placeholder={vi ? 'Chọn thư mục lưu video…' : 'Choose an output folder…'}
              onChange={(e) => setKey('outputDir', e.target.value)} />
            {hasPicker && (
              <button type="button" className="st-btn" onClick={pickOutputDir}>
                {vi ? 'Chọn…' : 'Browse…'}
              </button>
            )}
          </div>
        </StudioField>
      </StudioCard>

      <div className="st-actions">
        <button type="button" className="st-btn st-btn--primary"
          disabled={!ready || !cfg.outputDir || busy} onClick={onGenerate}>
          {busy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? '✨ Tạo kế hoạch' : '✨ Generate plan')}
        </button>
      </div>
    </>
  )
}
