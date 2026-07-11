/**
 * CharactersPanel — Story v2 review (F3): edit each character's name +
 * canonical description, show the auto-cast voice, and (optionally) generate a
 * canonical reference sheet for visual consistency. Studio BASE only.
 */
import { useEffect, useRef, useState } from 'react'
import { StudioCard, StudioField } from '../../../components/studio'
import { BASE_URL } from '../../../api/client'
import type { StoryPlanV2, CharacterDef, StoryVoicesResponse } from '../../../api/story'
import { generateReferenceSheet, getStoryVoices, previewNarration } from '../../../api/story'

// Short spoken sample when a character has no line yet in the timeline.
const SAMPLE: Record<string, string> = {
  vi: 'Xin chào, đây là giọng của nhân vật này.',
  en: 'Hello, this is how this character sounds.',
  ja: 'こんにちは、これはこのキャラクターの声です。',
  ko: '안녕하세요, 이것이 이 캐릭터의 목소리입니다.',
}

export function CharactersPanel({ vi, plan, artStyle, language, onChange, onVoiceChange }: {
  vi: boolean
  plan: StoryPlanV2
  artStyle: string
  language: string
  onChange: (id: string, up: Partial<CharacterDef>) => void
  onVoiceChange: (cid: string, engine: string, voiceId: string) => void
}) {
  // Available voices for this language's TTS engine (per-character override picker).
  const [avail, setAvail] = useState<StoryVoicesResponse | null>(null)
  useEffect(() => {
    let alive = true
    void getStoryVoices(language).then((r) => { if (alive) setAvail(r) }).catch(() => {})
    return () => { alive = false }
  }, [language])

  if (!plan.characters.length) return null
  const lang = (plan.language || 'vi').slice(0, 2)
  const sampleFor = (id: string): string => {
    const beat = plan.timeline.find((b) => b.speaker_id === id && (b.narration || '').trim())
    return (beat?.narration || SAMPLE[lang] || SAMPLE.en).slice(0, 160)
  }
  return (
    <StudioCard icon="🧑‍🎤" title={vi ? 'Nhân vật' : 'Characters'}
      aside={`${plan.characters.length}`}>
      <div className="st-char-list">
        {plan.characters.map((c) => (
          <CharacterRow key={c.id} vi={vi} c={c} artStyle={artStyle} language={lang}
            sample={sampleFor(c.id)} voice={plan.render?.voices?.[c.id]} avail={avail}
            onChange={onChange} onVoiceChange={onVoiceChange} />
        ))}
      </div>
    </StudioCard>
  )
}

function CharacterRow({ vi, c, artStyle, language, sample, voice, avail, onChange, onVoiceChange }: {
  vi: boolean
  c: CharacterDef
  artStyle: string
  language: string
  sample: string
  voice?: [string, string]
  avail: StoryVoicesResponse | null
  onChange: (id: string, up: Partial<CharacterDef>) => void
  onVoiceChange: (cid: string, engine: string, voiceId: string) => void
}) {
  const [sheet, setSheet] = useState<'idle' | 'busy' | 'done' | 'err'>('idle')
  const [master, setMaster] = useState<{ st: 'idle' | 'busy' | 'err'; url: string }>({ st: 'idle', url: '' })
  const [voiceState, setVoiceState] = useState<'idle' | 'busy' | 'playing' | 'err'>('idle')
  const audioRef = useRef<HTMLAudioElement | null>(null)

  async function makeSheet() {
    setSheet('busy')
    try {
      const r = await generateReferenceSheet({
        name: c.name, description: c.canonical_desc, art_style: artStyle,
      })
      setSheet(r.path ? 'done' : 'err')
    } catch { setSheet('err') }
  }

  // Cutout-ready character master (transparent PNG) — shown on a checkerboard so the
  // transparent areas are visible. One master/character, reusable for overlay.
  async function makeMaster() {
    if (master.st === 'busy') return
    setMaster({ st: 'busy', url: '' })
    try {
      const r = await generateReferenceSheet({
        name: c.name, description: c.canonical_desc, art_style: artStyle, transparent: true,
      })
      setMaster(r.url ? { st: 'idle', url: r.url } : { st: 'err', url: '' })
    } catch { setMaster({ st: 'err', url: '' }) }
  }

  async function hearVoice() {
    if (voiceState === 'busy') return
    // Toggle-stop if a preview is already playing.
    if (voiceState === 'playing' && audioRef.current) {
      audioRef.current.pause(); audioRef.current = null; setVoiceState('idle'); return
    }
    setVoiceState('busy')
    try {
      const r = await previewNarration({
        text: sample, language, gender: c.voice_gender || c.gender || 'female',
        voice_id: voice?.[1] || undefined, reading_speed: 1,
      })
      const audio = new Audio(`${BASE_URL}${r.url}`)
      audioRef.current = audio
      audio.onended = () => setVoiceState('idle')
      audio.onerror = () => setVoiceState('err')
      await audio.play()
      setVoiceState('playing')
    } catch { setVoiceState('err') }
  }

  return (
    <div className="st-char">
      <div className="st-char-main">
        <StudioField label={vi ? 'Tên' : 'Name'}>
          <input className="st-input" value={c.name}
            onChange={(e) => onChange(c.id, { name: e.target.value })} />
        </StudioField>
        <StudioField label={vi ? 'Mô tả chuẩn (giữ nhất quán)' : 'Canonical description (consistency)'}>
          <textarea className="st-textarea st-textarea--sm" rows={3} value={c.canonical_desc}
            onChange={(e) => onChange(c.id, { canonical_desc: e.target.value })} />
        </StudioField>
      </div>
      <div className="st-char-side">
        <button type="button" className="st-tag st-tag--voice" onClick={hearVoice}
          title={vi ? 'Nghe thử giọng' : 'Preview voice'}>
          {voiceState === 'busy' ? '⏳' : voiceState === 'playing' ? '⏸' : voiceState === 'err' ? '⚠' : '🔊'}{' '}
          {voice ? `${voice[0]}${voice[1] ? ' · ' + voice[1] : ''}` : (vi ? 'tự động' : 'auto')}
        </button>
        {(c.gender || c.voice_gender) && (
          <span className="st-tag st-tag--dim">{c.voice_gender || c.gender}</span>
        )}
        {avail && (avail.female.length > 0 || avail.male.length > 0) && (
          <select className="st-select st-select--sm" value={voice?.[1] || ''}
            title={vi ? 'Chọn giọng (mặc định: tự động)' : 'Pick voice (default: auto)'}
            onChange={(e) => onVoiceChange(c.id, avail.engine, e.target.value)}>
            <option value="">{vi ? 'Giọng: tự động' : 'Voice: auto'}</option>
            {avail.female.length > 0 && (
              <optgroup label={vi ? 'Nữ' : 'Female'}>
                {avail.female.map((vid) => <option key={vid} value={vid}>{vid}</option>)}
              </optgroup>
            )}
            {avail.male.length > 0 && (
              <optgroup label={vi ? 'Nam' : 'Male'}>
                {avail.male.map((vid) => <option key={vid} value={vid}>{vid}</option>)}
              </optgroup>
            )}
          </select>
        )}
        <button type="button" className="st-btn st-btn--sm" disabled={sheet === 'busy'} onClick={makeSheet}>
          {sheet === 'busy' ? (vi ? 'Đang tạo…' : 'Making…')
            : sheet === 'done' ? (vi ? '✓ Ảnh chuẩn' : '✓ Sheet')
            : sheet === 'err' ? (vi ? '⚠ Thử lại' : '⚠ Retry')
            : (vi ? 'Ảnh chuẩn' : 'Ref sheet')}
        </button>
        <button type="button" className="st-btn st-btn--sm" disabled={master.st === 'busy'} onClick={makeMaster}
          title={vi ? 'Ảnh nhân vật nền trong (để chèn lên video)' : 'Transparent character master (for overlay)'}>
          {master.st === 'busy' ? (vi ? 'Đang tạo…' : 'Making…')
            : master.st === 'err' ? (vi ? '⚠ Thử lại' : '⚠ Retry')
            : master.url ? (vi ? '↻ Nhân vật' : '↻ Master')
            : (vi ? '🧍 Nhân vật' : '🧍 Master')}
        </button>
        {master.url && (
          <div className="st-char-master"
            style={{ background: 'repeating-conic-gradient(#c8c8c8 0% 25%, #fff 0% 50%) 50% / 14px 14px' }}>
            <img src={`${BASE_URL}${master.url}`} alt={c.name || c.id} />
          </div>
        )}
      </div>
    </div>
  )
}
