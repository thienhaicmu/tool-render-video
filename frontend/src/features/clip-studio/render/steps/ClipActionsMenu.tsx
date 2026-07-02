/**
 * ClipActionsMenu — P0.6 (frontend redesign): "···" overflow menu on a
 * result clip card.
 *
 * The card's action row previously showed seven equal-weight controls
 * (Save / 👍 / 👎 / Copy / 📂 / 🗑 / ···) — decision paralysis on the one
 * card where the user makes their most important call. Save + feedback
 * stay visible; the utility actions live here.
 */
import { useEffect, useRef, useState } from 'react'

export interface ClipMenuItem {
  id: string
  label: string
  danger?: boolean
  onClick: () => void
}

export function ClipActionsMenu({ items }: { items: ClipMenuItem[] }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (items.length === 0) return null

  return (
    <div ref={rootRef} style={{ position: 'relative', marginLeft: 'auto' }}>
      <button
        className="clip-more-btn"
        title="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); setOpen((p) => !p) }}
      >
        ···
      </button>
      {open && (
        <div role="menu" style={styles.menu} onClick={(e) => e.stopPropagation()}>
          {items.map((it) => (
            <button
              key={it.id}
              role="menuitem"
              style={{
                ...styles.item,
                color: it.danger ? 'var(--fail)' : 'var(--text-1)',
              }}
              onClick={() => { setOpen(false); it.onClick() }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  menu: {
    position: 'absolute',
    right: 0,
    bottom: 'calc(100% + 4px)',
    minWidth: 150,
    background: 'var(--bg-panel)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    padding: 4,
    zIndex: 50,
    display: 'flex',
    flexDirection: 'column',
    gap: 1,
  },
  item: {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '6px 10px',
    borderRadius: 5,
    border: 'none',
    background: 'transparent',
    fontSize: 11,
    fontWeight: 500,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
  },
}
