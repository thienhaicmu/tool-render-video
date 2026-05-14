/* Source screen — upload/select source video, configure session metadata. */

import { sessionStore } from '../store/session.js';
import { draftStore } from '../store/draft.js';
import { desktopAdapter } from '../desktop-adapter.js';
import { router } from '../router.js';
import { emptyState, ICONS } from '../components/empty-state.js';

function renderDropZone() {
  return `
    <div class="card" id="source-dropzone" style="border:2px dashed var(--color-border);text-align:center;padding:var(--sp-16) var(--sp-8);cursor:pointer;transition:border-color 0.15s">
      <div style="color:var(--color-text-faint);font-size:32px;margin-bottom:var(--sp-3)">⬆</div>
      <div class="text-section">Drop video file here</div>
      <div class="text-caption mt-2">MP4, MOV, MKV · up to 10 GB</div>
      <button class="btn btn-secondary mt-4" id="source-browse-btn">Browse files</button>
    </div>
  `;
}

function renderSessionList(sessions) {
  if (!sessions.length) return '';
  return `
    <div style="margin-top:var(--sp-6)">
      <div class="text-section" style="margin-bottom:var(--sp-3)">Recent sources</div>
      <div class="card" style="padding:0;overflow:hidden">
        ${sessions.map(s => `
          <div class="part-item session-item" data-session-id="${s.id}">
            <div class="part-item__index">${s.id.slice(-4)}</div>
            <div class="part-item__title">${s.sourceFile ?? s.id}</div>
            <div class="text-caption">${s.platform ?? ''}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

async function mount(el) {
  el.innerHTML = `
    <div class="screen__header">
      <div class="screen__title">Source</div>
      <div class="screen__subtitle">Select a video to begin</div>
    </div>
    <div class="screen__body" id="source-body">
      ${renderDropZone()}
      <div id="source-sessions"></div>
    </div>
  `;

  await sessionStore.load();

  const { sessions } = sessionStore.getState();
  const sessionsEl = el.querySelector('#source-sessions');
  if (sessionsEl) sessionsEl.innerHTML = renderSessionList(sessions);

  const browseBtn = el.querySelector('#source-browse-btn');
  browseBtn?.addEventListener('click', async () => {
    const file = await desktopAdapter.pickVideoFile();
    if (file) {
      draftStore.patch({ sourceFile: file });
      router.go('/studio');
    }
  });

  const dropzone = el.querySelector('#source-dropzone');
  dropzone?.addEventListener('dragover', e => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--color-accent)';
  });
  dropzone?.addEventListener('dragleave', () => {
    dropzone.style.borderColor = '';
  });
  dropzone?.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.style.borderColor = '';
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      draftStore.patch({ sourceFile: file.path ?? file.name });
      router.go('/studio');
    }
  });

  el.addEventListener('click', e => {
    const item = e.target.closest('.session-item');
    if (item?.dataset.sessionId) {
      sessionStore.setActive(item.dataset.sessionId);
      router.go('/studio');
    }
  });
}

export const sourceScreen = { mount };
