/**
 * StoryModelCard — renders the Story Intelligence StoryModel: what the AI
 * understood about the whole film before it selected clips / scenes.
 *
 * Dumb + defensive: takes a StoryModel (or null/undefined) and renders nothing
 * when there is no usable content, so callers can drop it in unconditionally.
 *
 * Two data sources feed it (same shape):
 *   • clips path  → GET /jobs/{id}/ai-summary → story_model
 *   • recap path  → recap.plan.ready WS event → context.story_model
 */
import type { StoryModel } from '@/types/api'

// A StoryModel with no field carrying content — mirror backend StoryModel.is_empty().
function _isEmpty(sm: StoryModel): boolean {
  return !(
    sm.summary || sm.theme || sm.genre || sm.conflict || sm.resolution ||
    sm.climax || sm.ending ||
    (sm.characters && sm.characters.length > 0) ||
    (sm.beats && sm.beats.length > 0) ||
    (sm.emotional_curve && sm.emotional_curve.length > 0)
  )
}

function Chip({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <span style={{ fontSize: 10, color: 'var(--text-2)', background: 'rgba(255,255,255,.04)', border: '1px solid var(--border)', borderRadius: 5, padding: '2px 7px' }}>
      <span style={{ color: 'var(--text-3)', marginRight: 4 }}>{label}</span>{value}
    </span>
  )
}

export function StoryModelCard({ storyModel }: { storyModel?: StoryModel | null }) {
  if (!storyModel || _isEmpty(storyModel)) return null
  const sm = storyModel
  const chars = (sm.characters ?? []).filter(c => c && (c.name || c.role))
  const curve = (sm.emotional_curve ?? []).filter(Boolean)
  // Coverage: fraction of plot turns bound to a concrete scene (recap only).
  const beats = (sm.beats ?? [])
  const bound = beats.filter(b => (b?.bound_scene_index ?? -1) >= 0).length
  const coverage = beats.length > 0 ? Math.round((bound / beats.length) * 100) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderLeft: '2px solid var(--accent)', paddingLeft: 10 }}>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-3)' }}>
        Story Intelligence — AI đã hiểu gì về phim
      </div>

      {sm.summary && (
        <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.5 }}>{sm.summary}</div>
      )}

      {(sm.theme || sm.genre || sm.conflict || sm.resolution) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <Chip label="Chủ đề" value={sm.theme} />
          <Chip label="Thể loại" value={sm.genre} />
          <Chip label="Mâu thuẫn" value={sm.conflict} />
          <Chip label="Kết" value={sm.resolution} />
        </div>
      )}

      {(sm.climax || sm.ending) && (
        <div style={{ fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5 }}>
          {sm.climax && <div>★ Cao trào: {sm.climax}</div>}
          {sm.ending && <div>⤷ Kết thúc: {sm.ending}</div>}
        </div>
      )}

      {chars.length > 0 && (
        <div>
          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 4 }}>
            Nhân vật
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {chars.map((c, i) => (
              <div key={i} style={{ fontSize: 10, color: 'var(--text-2)' }}>
                <span style={{ fontWeight: 700 }}>{c.name || '—'}</span>
                {c.role && <span style={{ color: 'var(--text-3)' }}> · {c.role}</span>}
                {c.want && <span style={{ color: 'var(--text-3)' }}> (muốn {c.want})</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {curve.length > 0 && (
        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
          Mạch cảm xúc: {curve.join(' → ')}
        </div>
      )}

      {coverage !== null && (
        <div style={{ fontSize: 10, color: coverage >= 80 ? 'var(--ok, #10b981)' : 'var(--warn, #f59e0b)' }}>
          Độ phủ mạch truyện: {coverage}% ({bound}/{beats.length} nút thắt được kể)
        </div>
      )}
    </div>
  )
}
