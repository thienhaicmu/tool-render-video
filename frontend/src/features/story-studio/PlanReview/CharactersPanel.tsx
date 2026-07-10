/**
 * CharactersPanel — Story v2 review (F3): edit each character's name +
 * canonical description, show the auto-cast voice, and (optionally) generate a
 * canonical reference sheet for visual consistency. Studio BASE only.
 */
import { useState } from 'react'
import { StudioCard, StudioField } from '../../../components/studio'
import type { StoryPlanV2, CharacterDef } from '../../../api/story'
import { generateReferenceSheet } from '../../../api/story'

export function CharactersPanel({ vi, plan, artStyle, onChange }: {
  vi: boolean
  plan: StoryPlanV2
  artStyle: string
  onChange: (id: string, up: Partial<CharacterDef>) => void
}) {
  if (!plan.characters.length) return null
  return (
    <StudioCard icon="🧑‍🎤" title={vi ? 'Nhân vật' : 'Characters'}
      aside={`${plan.characters.length}`}>
      <div className="st-char-list">
        {plan.characters.map((c) => (
          <CharacterRow key={c.id} vi={vi} c={c} artStyle={artStyle}
            voice={plan.render?.voices?.[c.id]} onChange={onChange} />
        ))}
      </div>
    </StudioCard>
  )
}

function CharacterRow({ vi, c, artStyle, voice, onChange }: {
  vi: boolean
  c: CharacterDef
  artStyle: string
  voice?: [string, string]
  onChange: (id: string, up: Partial<CharacterDef>) => void
}) {
  const [sheet, setSheet] = useState<'idle' | 'busy' | 'done' | 'err'>('idle')

  async function makeSheet() {
    setSheet('busy')
    try {
      const r = await generateReferenceSheet({
        name: c.name, description: c.canonical_desc, art_style: artStyle,
      })
      setSheet(r.path ? 'done' : 'err')
    } catch { setSheet('err') }
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
        <span className="st-tag">
          🎙 {voice ? `${voice[0]}${voice[1] ? ' · ' + voice[1] : ''}` : (vi ? 'tự động' : 'auto')}
        </span>
        {(c.gender || c.voice_gender) && (
          <span className="st-tag st-tag--dim">{c.voice_gender || c.gender}</span>
        )}
        <button type="button" className="st-btn st-btn--sm" disabled={sheet === 'busy'} onClick={makeSheet}>
          {sheet === 'busy' ? (vi ? 'Đang tạo…' : 'Making…')
            : sheet === 'done' ? (vi ? '✓ Ảnh chuẩn' : '✓ Sheet')
            : sheet === 'err' ? (vi ? '⚠ Thử lại' : '⚠ Retry')
            : (vi ? 'Ảnh chuẩn' : 'Ref sheet')}
        </button>
      </div>
    </div>
  )
}
