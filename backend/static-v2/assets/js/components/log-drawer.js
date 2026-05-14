/* logDrawerShell()            — returns HTML string for the drawer container.
   wireLogDrawer(container, loadFn) — wire toggle + lazy-load on first open.
     loadFn: async () => string[]   — called once on first open.
     returns: { refresh(lines), isLoaded() }
*/

export function logDrawerShell() {
  return `
    <div class="log-drawer">
      <button class="log-drawer__toggle" id="log-drawer-toggle">
        <div class="row gap-2" style="align-items:center">
          <span class="text-body" style="font-weight:600">Logs</span>
          <span class="flex-1"></span>
          <span id="log-drawer-count" class="text-caption text-faint"></span>
          <span id="log-drawer-chevron" class="log-drawer__chevron">▼</span>
        </div>
      </button>
      <div id="log-drawer-body" style="display:none;margin-top:var(--sp-2)">
        <div id="log-drawer-content" class="log-drawer__content"></div>
      </div>
    </div>
  `;
}

export function wireLogDrawer(container, loadFn) {
  let isOpen  = false;
  let loaded  = false;

  const toggle  = container.querySelector('#log-drawer-toggle');
  const body    = container.querySelector('#log-drawer-body');
  const chevron = container.querySelector('#log-drawer-chevron');
  const content = container.querySelector('#log-drawer-content');
  const count   = container.querySelector('#log-drawer-count');
  if (!toggle || !body) return null;

  toggle.addEventListener('click', async () => {
    isOpen = !isOpen;
    body.style.display = isOpen ? '' : 'none';
    if (chevron) chevron.textContent = isOpen ? '▲' : '▼';

    if (isOpen && !loaded && typeof loadFn === 'function') {
      loaded = true;
      if (content) content.innerHTML = '<div class="text-caption text-faint" style="padding:var(--sp-2)">Loading…</div>';
      try {
        const lines = await loadFn();
        _renderLines(content, count, lines);
      } catch {
        if (content) content.innerHTML = '<div class="text-caption text-faint" style="padding:var(--sp-2)">Failed to load logs.</div>';
      }
    }
  });

  return {
    refresh(lines) {
      if (!loaded || !isOpen) return;
      _renderLines(content, count, lines);
    },
    isLoaded() { return loaded; },
  };
}

function _renderLines(content, count, lines) {
  if (!content) return;
  if (Array.isArray(lines) && lines.length) {
    content.innerHTML = lines.map(l => `<div class="log-line">${_esc(l)}</div>`).join('');
    content.scrollTop = content.scrollHeight;
    if (count) count.textContent = `${lines.length} lines`;
  } else {
    content.innerHTML = '<div class="text-caption text-faint" style="padding:var(--sp-2)">No log entries.</div>';
    if (count) count.textContent = '';
  }
}

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
