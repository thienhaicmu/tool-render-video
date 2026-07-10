/**
 * InputScreen — Story v2 phase 1 (F2): source A (paste chapter) / B (idea) +
 * minimal config, with validation, live char counts, sample templates, and an
 * idea→narration budget hint. Uses the Studio BASE (F0) only — no content-studio.
 *
 * The AI decides tone / image count / voices, so the input stays intentionally
 * small: text (A) or idea+duration+genre (B) · language · aspect · art (optional)
 * · output folder.
 */
import { StudioCard, StudioField, SegRow, RatioPicker } from '../../components/studio'
import {
  STORY_LANGS, ART_STYLE_PRESETS, GENRE_PRESETS, ASPECTS,
  type StoryConfig, type StorySource, type StoryLang, type Aspect,
} from './types'

// Chars/sec per language (mirror backend story_plan_v2.CPS) — used for the
// idea-mode narration budget hint (duration × cps ≈ target narration chars).
const CPS: Record<StoryLang, number> = { vi: 15, en: 14, ja: 8 }
const MIN_CHAPTER_CHARS = 200

const SAMPLE_CHAPTER: Record<'vi' | 'other', string> = {
  vi: 'Đêm khuya, gió lạnh rít qua khe cửa Vân Tiêu Các. Hàn Phong ngồi kiết già trên bồ đoàn, ' +
    'kinh mạch trong người cuộn trào như sóng dữ. Ba năm bị phế võ công, hôm nay hắn quyết phá cảnh. ' +
    'Đột nhiên, một luồng nhiệt nóng bỏng từ đan điền xông thẳng lên bách hội — hắn bừng tỉnh, ánh mắt ' +
    'sắc như đao. "Những kẻ từng sỉ nhục ta… giờ hãy chờ đấy." Ngoài cửa, Tuyết Nhi khẽ gọi: "Sư huynh, ' +
    'người… đã thành công rồi sao?"',
  other: 'Late at night, a cold wind howled through the halls of the Cloudveil Pavilion. Han Feng sat in ' +
    'silent meditation, the energy in his meridians surging like a storm. For three years his cultivation ' +
    'had been crippled; tonight he would break through. A sudden heat erupted from his core and shot upward — ' +
    'his eyes snapped open, sharp as a blade. "Those who once humiliated me… now wait." Outside the door, ' +
    'Xue\'er whispered: "Senior brother, have you… succeeded?"',
}
const SAMPLE_IDEA: Record<'vi' | 'other', string> = {
  vi: 'Một kiếm khách trẻ bị hãm hại mất hết công lực, tình cờ có được bí kíp thượng cổ, từng bước ' +
    'báo thù môn phái đã phản bội mình.',
  other: 'A young swordsman, stripped of his power by betrayal, stumbles upon an ancient manual and rises ' +
    'step by step to avenge the sect that wronged him.',
}

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
  const chapterChars = cfg.chapterText.trim().length
  const ideaChars = cfg.idea.trim().length
  const budgetChars = Math.round(cfg.durationSec * CPS[cfg.language])
  const sampleKey = cfg.language === 'vi' ? 'vi' : 'other'

  // Validation — collect missing / weak conditions for an honest CTA hint.
  const issues: string[] = []
  if (cfg.source === 'paste' && chapterChars === 0) issues.push(vi ? 'nội dung truyện' : 'chapter text')
  if (cfg.source === 'idea' && ideaChars === 0) issues.push(vi ? 'ý tưởng' : 'an idea')
  if (!cfg.outputDir.trim()) issues.push(vi ? 'thư mục lưu' : 'an output folder')
  const shortChapter = cfg.source === 'paste' && chapterChars > 0 && chapterChars < MIN_CHAPTER_CHARS
  const canGenerate = ready && !!cfg.outputDir.trim() && !busy

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
            hint={vi ? 'Dán cả chương — AI tự hiểu, chia phân đoạn, chọn giọng, dựng key-visual.'
                     : 'Paste the whole chapter — the AI segments it, casts voices, designs key visuals.'}>
            <textarea className="st-textarea" rows={12}
              placeholder={vi ? 'Dán nội dung chương truyện ở đây…' : 'Paste the chapter here…'}
              value={cfg.chapterText} onChange={(e) => setKey('chapterText', e.target.value)} />
            <div className="st-field-foot">
              <span className={shortChapter ? 'st-warn' : ''}>
                {chapterChars.toLocaleString()} {vi ? 'ký tự' : 'chars'}
                {shortChapter && (vi ? ' · hơi ngắn' : ' · a bit short')}
              </span>
              <span className="st-foot-actions">
                <button type="button" className="st-link" onClick={() => setKey('chapterText', SAMPLE_CHAPTER[sampleKey])}>
                  {vi ? 'Chèn mẫu' : 'Insert sample'}
                </button>
                {chapterChars > 0 && (
                  <button type="button" className="st-link" onClick={() => setKey('chapterText', '')}>
                    {vi ? 'Xoá' : 'Clear'}
                  </button>
                )}
              </span>
            </div>
          </StudioField>
        ) : (
          <>
            <StudioField label={vi ? 'Ý tưởng' : 'Idea'}
              hint={vi ? 'Mô tả ngắn — AI sẽ tự sáng tác truyện theo thời lượng bên dưới.'
                       : 'A short brief — the AI authors the story to the target length below.'}>
              <textarea className="st-textarea" rows={5}
                placeholder={vi ? 'VD: Kiếm khách trẻ báo thù môn phái…' : 'e.g. A young swordsman seeks revenge…'}
                value={cfg.idea} onChange={(e) => setKey('idea', e.target.value)} />
              <div className="st-field-foot">
                <span>{ideaChars.toLocaleString()} {vi ? 'ký tự' : 'chars'}</span>
                <span className="st-foot-actions">
                  <button type="button" className="st-link" onClick={() => setKey('idea', SAMPLE_IDEA[sampleKey])}>
                    {vi ? 'Chèn mẫu' : 'Insert sample'}
                  </button>
                  {ideaChars > 0 && (
                    <button type="button" className="st-link" onClick={() => setKey('idea', '')}>
                      {vi ? 'Xoá' : 'Clear'}
                    </button>
                  )}
                </span>
              </div>
            </StudioField>
            <div className="st-grid-2">
              <StudioField label={`${vi ? 'Thời lượng' : 'Duration'}: ${mins} ${vi ? 'phút' : 'min'}`}
                hint={vi ? `≈ ${budgetChars.toLocaleString()} ký tự lời kể` : `≈ ${budgetChars.toLocaleString()} narration chars`}>
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
          <StudioField label={vi ? 'Ngôn ngữ' : 'Language'}
            hint={vi ? 'Quyết định giọng đọc (vi→Gemini, en/ja→ElevenLabs).' : 'Drives the TTS engine (vi→Gemini, en/ja→ElevenLabs).'}>
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
            <input className={`st-input${issues.includes(vi ? 'thư mục lưu' : 'an output folder') ? ' st-input--invalid' : ''}`}
              value={cfg.outputDir}
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

      <div className="st-actions st-actions--col">
        <button type="button" className="st-btn st-btn--primary st-btn--lg"
          disabled={!canGenerate} onClick={onGenerate}>
          {busy ? (vi ? 'Đang tạo…' : 'Generating…') : (vi ? '✨ Tạo kế hoạch' : '✨ Generate plan')}
        </button>
        {issues.length > 0 && (
          <span className="st-muted st-actions-hint">
            {vi ? 'Cần: ' : 'Missing: '}{issues.join(vi ? ', ' : ', ')}
          </span>
        )}
      </div>
    </>
  )
}
