/**
 * ProjectBar — Story Studio project persistence UI (SP2).
 *
 * A compact bar above the phases: rename the current project, see the autosave
 * status, and open / create / delete saved projects. State + persistence live in
 * StoryStudio; this is presentation + a small dropdown only.
 */
import { useEffect, useRef, useState } from 'react'
import type { StoryProjectListItem } from '../../api/storyProjects'

export type SaveTag = 'idle' | 'saving' | 'saved'

export function ProjectBar({ vi, name, saveTag, projects, canUndo, canRedo,
  onUndo, onRedo, onDuplicate, onName, onOpen, onNew, onDelete, onRefresh }: {
  vi: boolean
  name: string
  saveTag: SaveTag
  projects: StoryProjectListItem[]
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onDuplicate: () => void
  onName: (v: string) => void
  onOpen: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRefresh: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  // Close the dropdown on an outside click.
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const tag = saveTag === 'saving' ? (vi ? 'Đang lưu…' : 'Saving…')
    : saveTag === 'saved' ? (vi ? '✓ Đã lưu' : '✓ Saved') : ''

  return (
    <div className="st-project-bar">
      <span className="st-project-icon">🗂️</span>
      <input className="st-input st-input--sm st-project-name" value={name}
        placeholder={vi ? 'Tên dự án…' : 'Project name…'}
        onChange={(e) => onName(e.target.value)} />
      <span className="st-project-save st-muted">{tag}</span>
      <button type="button" className="st-icon-btn" disabled={!canUndo} onClick={onUndo}
        title={vi ? 'Hoàn tác (sửa kế hoạch)' : 'Undo (plan edit)'}>↶</button>
      <button type="button" className="st-icon-btn" disabled={!canRedo} onClick={onRedo}
        title={vi ? 'Làm lại' : 'Redo'}>↷</button>
      <div className="st-project-menu" ref={ref}>
        <button type="button" className="st-btn st-btn--sm"
          onClick={() => { if (!open) onRefresh(); setOpen((o) => !o) }}>
          {vi ? 'Dự án ▾' : 'Projects ▾'}
        </button>
        {open && (
          <div className="st-project-dropdown">
            <button type="button" className="st-project-item st-project-new"
              onClick={() => { setOpen(false); onNew() }}>
              {vi ? '＋ Dự án mới' : '＋ New project'}
            </button>
            <button type="button" className="st-project-item st-project-new"
              onClick={() => { setOpen(false); onDuplicate() }}>
              {vi ? '⧉ Nhân bản dự án này' : '⧉ Duplicate this project'}
            </button>
            {projects.length === 0 && (
              <div className="st-project-empty st-muted">{vi ? 'Chưa có dự án đã lưu' : 'No saved projects'}</div>
            )}
            {projects.map((p) => (
              <div key={p.id} className="st-project-item">
                <button type="button" className="st-project-open"
                  onClick={() => { setOpen(false); onOpen(p.id) }}>
                  <span className="st-project-title">{p.name || (vi ? '(chưa đặt tên)' : '(untitled)')}</span>
                  <span className="st-project-meta st-muted">
                    {p.status === 'ready' ? (vi ? 'đã dựng' : 'planned') : (vi ? 'nháp' : 'draft')} · {p.updated_at?.slice(0, 10)}
                  </span>
                </button>
                <button type="button" className="st-icon-btn st-icon-btn--danger"
                  title={vi ? 'Xoá dự án' : 'Delete project'}
                  onClick={() => onDelete(p.id)}>🗑</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
