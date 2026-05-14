/* EmptyState — renders a centered placeholder with icon, title, optional body + CTA. */

export function emptyState({ icon = '', title, body = '', ctaLabel = '', onCta = null }) {
  const html = `
    <div class="empty-state">
      ${icon ? `<div class="empty-state__icon">${icon}</div>` : ''}
      <div class="empty-state__title">${title}</div>
      ${body ? `<div class="empty-state__body">${body}</div>` : ''}
      ${ctaLabel ? `<button class="btn btn-primary empty-state__cta">${ctaLabel}</button>` : ''}
    </div>
  `;

  const el = document.createElement('div');
  el.innerHTML = html.trim();
  const node = el.firstChild;

  if (ctaLabel && onCta) {
    node.querySelector('.empty-state__cta')?.addEventListener('click', onCta);
  }

  return node;
}

export const ICONS = {
  video: `<svg viewBox="0 0 48 48" fill="none"><rect x="4" y="8" width="40" height="28" rx="4" stroke="currentColor" stroke-width="2.5"/><path d="M20 18l12 6-12 6V18z" fill="currentColor" opacity=".5"/><path d="M16 42h16M24 36v6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>`,
  search: `<svg viewBox="0 0 48 48" fill="none"><circle cx="20" cy="20" r="13" stroke="currentColor" stroke-width="2.5"/><path d="M30 30l10 10" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>`,
  empty:  `<svg viewBox="0 0 48 48" fill="none"><rect x="8" y="8" width="32" height="32" rx="4" stroke="currentColor" stroke-width="2.5" stroke-dasharray="6 4"/></svg>`,
  clock:  `<svg viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="16" stroke="currentColor" stroke-width="2.5"/><path d="M24 14v11l6 4" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};
