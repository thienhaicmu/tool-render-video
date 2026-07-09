/**
 * BiblePhase.tsx — Story Studio phase 2: review the AI Story Bible (characters +
 * environments) and generate a Character Reference Sheet per character so the
 * same character stays visually consistent across every shot.
 */
import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { HeroHeader } from '../content-studio/shared'
import { generateReferenceSheet, type StoryBible } from '../../api/story'
import type { StoryConfig as Cfg } from './types'

export function BiblePhase({ vi, bible, setBible, cfg, busy, error, onBack, onNext }: {
  vi: boolean; bible: StoryBible; setBible: (b: StoryBible) => void; cfg: Cfg
  busy: boolean; error: string | null; onBack: () => void; onNext: () => void
}) {
  const [genId, setGenId] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const chars = bible.characters.filter((c) => c.name || c.id)

  async function makeSheet(charId: string, name: string, description: string) {
    if (genId) return
    setGenId(charId); setNote(null)
    try {
      const r = await generateReferenceSheet({
        series_id: cfg.seriesId || undefined, character_id: charId,
        name, description, art_style: cfg.artStyle || undefined,
      })
      setBible({
        ...bible,
        characters: bible.characters.map((c) => c.id === charId ? { ...c, reference_image_path: r.path } : c),
      })
      setNote(`✓ ${vi ? 'Đã tạo ảnh chuẩn cho' : 'Reference sheet ready for'} ${name}`)
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e))
    } finally { setGenId(null) }
  }

  return (
    <div className="cs-screen">
      <HeroHeader icon="🎭" title={vi ? 'Nhân vật & bối cảnh' : 'Characters & world'}
        subtitle={vi
          ? 'AI đã hiểu truyện. Duyệt nhân vật/bối cảnh; tạo "ảnh chuẩn" cho nhân vật để giữ nhất quán qua mọi shot.'
          : 'The AI understood the story. Review the cast/world; generate a reference sheet per character to keep them consistent across shots.'} />

      {(bible.hook || bible.setting) && (
        <section className="cs-card">
          {bible.setting && <div style={{ marginBottom: bible.hook ? 8 : 0 }}><b>{vi ? 'Bối cảnh: ' : 'Setting: '}</b>{bible.setting}</div>}
          {bible.hook && <div><b>Hook: </b>{bible.hook}</div>}
        </section>
      )}

      <section className="cs-card">
        <div className="cs-card-hd">
          <span className="cs-card-title">{vi ? 'Nhân vật' : 'Characters'}</span>
          <span className="cs-count">{chars.length}</span>
        </div>
        {chars.length === 0 && <div className="cs-hint">{vi ? 'Không có nhân vật tái xuất hiện trong chương này.' : 'No recurring characters in this chapter.'}</div>}
        {chars.map((c) => (
          <div key={c.id} className="st-entity">
            <div style={{ minWidth: 0 }}>
              <b>{c.name || c.id}</b>
              <div className="st-entity-desc">{c.description}</div>
              {c.reference_image_path && <span className="st-ref-badge">📌 {vi ? 'ảnh chuẩn' : 'reference'}</span>}
            </div>
            <Button variant="ghost" size="sm" disabled={!!genId}
              onClick={() => makeSheet(c.id, c.name || c.id, c.description)}>
              {genId === c.id ? '…' : (c.reference_image_path ? (vi ? 'Tạo lại' : 'Regenerate') : (vi ? '🖼️ Ảnh chuẩn' : '🖼️ Reference'))}
            </Button>
          </div>
        ))}
        {note && <div className="cs-hint" style={{ marginTop: 8 }}>{note}</div>}
      </section>

      {bible.environments.length > 0 && (
        <section className="cs-card">
          <div className="cs-card-hd">
            <span className="cs-card-title">{vi ? 'Bối cảnh' : 'Environments'}</span>
            <span className="cs-count">{bible.environments.length}</span>
          </div>
          {bible.environments.map((e) => (
            <div key={e.id} className="st-entity">
              <div style={{ minWidth: 0 }}>
                <b>{e.name || e.id}</b>
                <div className="st-entity-desc">{e.description}</div>
              </div>
            </div>
          ))}
        </section>
      )}

      <div className="cs-footer">
        <Button variant="ghost" onClick={onBack} disabled={busy}>{vi ? '← Quay lại' : '← Back'}</Button>
        {error && <span className="cs-error">{error}</span>}
        <Button variant="primary" className="cs-cta" disabled={busy} onClick={onNext}>
          {busy ? (vi ? 'AI đang dựng storyboard…' : 'Building storyboard…') : (vi ? 'Dựng Storyboard →' : 'Build Storyboard →')}
        </Button>
      </div>
    </div>
  )
}
