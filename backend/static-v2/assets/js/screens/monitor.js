/* Monitor screen — live job progress via WebSocket + polling fallback. */

import { monitorStore } from '../store/monitor.js';
import { statusChip } from '../components/status-chip.js';
import { aiBadge } from '../components/ai-badge.js';
import { router } from '../router.js';
import { renderApi } from '../api/render.js';

function renderJobHeader(job) {
  if (!job) return '<div class="text-caption text-faint">Loading…</div>';
  return `
    <div class="row gap-3" style="align-items:center;flex-wrap:wrap">
      <div class="text-section">${job.id.slice(0, 16)}…</div>
      ${statusChip(job.status)}
      <span class="flex-1"></span>
      ${job.status === 'running' ? `<button class="btn btn-secondary btn-sm" id="monitor-cancel-btn">Cancel</button>` : ''}
      ${(job.status === 'completed' || job.status === 'partial')
          ? `<button class="btn btn-primary" id="monitor-results-btn">View results →</button>`
          : ''}
    </div>
    <div class="text-caption text-faint mt-2">
      ${job.platform ?? ''} · ${job.partsOk ?? 0}/${job.partsTotal ?? 0} parts
      ${job.executionMode ? `· mode: ${job.executionMode}` : ''}
    </div>
  `;
}

function renderParts(parts) {
  if (!parts.length) {
    return '<div class="text-caption text-faint" style="padding:var(--sp-4)">No parts yet…</div>';
  }
  return `
    <div class="card" style="padding:0;overflow:hidden">
      ${parts.map(p => `
        <div class="part-item">
          <div class="part-item__index">${p.index}</div>
          <div class="part-item__title">${p.title ?? `Part ${p.index}`}</div>
          <div class="row gap-2">
            ${statusChip(p.status)}
            ${aiBadge(p.aiState)}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function updateUI(el, state) {
  const headerEl = el.querySelector('#monitor-job-header');
  const partsEl  = el.querySelector('#monitor-parts');
  const connEl   = el.querySelector('#monitor-conn');

  if (headerEl) headerEl.innerHTML = renderJobHeader(state.job);
  if (partsEl)  partsEl.innerHTML  = renderParts(state.parts);
  if (connEl) {
    connEl.textContent = state.connected ? '● Live' : '○ Polling';
    connEl.style.color = state.connected ? 'var(--color-success)' : 'var(--color-text-faint)';
  }
}

async function mount(el, params) {
  const jobId = params[0];

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Monitor</div>
          <div class="screen__subtitle">Job: <code style="font-family:monospace">${jobId ?? '—'}</code></div>
        </div>
        <span class="flex-1"></span>
        <span class="text-caption" id="monitor-conn">Connecting…</span>
        <button class="btn btn-ghost" id="monitor-back-btn">← Studio</button>
      </div>
    </div>
    <div class="screen__body col gap-4">
      <div id="monitor-job-header"></div>
      <div>
        <div class="text-section" style="margin-bottom:var(--sp-3)">Parts</div>
        <div id="monitor-parts"></div>
      </div>
      ${el.querySelector('#monitor-error') ? '' : '<div id="monitor-error" class="text-caption" style="color:var(--color-failed)"></div>'}
    </div>
  `;

  el.querySelector('#monitor-back-btn')?.addEventListener('click', () => router.go('/studio'));

  if (!jobId) {
    el.querySelector('#monitor-job-header').innerHTML = '<div class="text-caption" style="color:var(--color-failed)">No job ID.</div>';
    return;
  }

  const unsub = monitorStore.subscribe(state => {
    updateUI(el, state);

    const resultsBtn = el.querySelector('#monitor-results-btn');
    resultsBtn?.addEventListener('click', () => router.go(`/results/${jobId}`));

    const cancelBtn = el.querySelector('#monitor-cancel-btn');
    cancelBtn?.addEventListener('click', async () => {
      cancelBtn.disabled = true;
      try { await renderApi.cancel(jobId); } catch { /* ignore */ }
    });

    const errEl = el.querySelector('#monitor-error');
    if (errEl) errEl.textContent = state.error ?? '';
  });

  monitorStore.start(jobId);

  el.addEventListener('unmount', () => {
    unsub();
    monitorStore.stop();
  });
}

export const monitorScreen = { mount };
