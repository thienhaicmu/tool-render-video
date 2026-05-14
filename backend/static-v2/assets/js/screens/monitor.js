/* Monitor screen — live job stream via subscribeJob + polling fallback + logs drawer */

import { monitorStore } from '../store/monitor.js';
import { statusChip } from '../components/status-chip.js';
import { router } from '../router.js';
import { renderApi } from '../api/render.js';

const TERMINAL = new Set(['completed','completed_with_errors','failed','interrupted']);

/* ── Sub-renders ──────────────────────────────────────────────────── */

function renderTransportBadge(mode) {
  const map = {
    websocket: { label: '● Live',       color: 'var(--color-success)' },
    polling:   { label: '○ Polling',    color: 'var(--color-warning)' },
    connecting:{ label: '⋯ Connecting', color: 'var(--color-text-faint)' },
    terminal_poll:{ label:'● Done',     color: 'var(--color-success)' },
  };
  const { label, color } = map[mode] ?? { label: mode, color: 'var(--color-text-faint)' };
  return `<span class="text-caption" style="color:${color};font-weight:600">${label}</span>`;
}

function renderJobSummary(state) {
  const { job, summary, transportMode } = state;
  if (!job) {
    return `
      <div class="col gap-2">
        <div class="skeleton-line" style="height:28px;width:40%"></div>
        <div class="skeleton-line" style="height:6px"></div>
        <div class="skeleton-line" style="height:12px;width:30%"></div>
      </div>
    `;
  }

  const rawStatus   = job.status === 'completed_with_errors' ? 'partial' : job.status;
  const pct         = Math.min(100, job.progressPercent ?? summary?.overall_progress_percent ?? 0);
  const stage       = (job.stage ?? summary?.current_stage ?? '').replace(/_/g, ' ');
  const totalParts  = summary?.total_parts ?? 0;
  const doneParts   = summary?.completed_parts ?? 0;
  const failedParts = summary?.failed_parts ?? 0;

  return `
    <div class="col gap-3">
      <div class="row gap-3" style="align-items:center;flex-wrap:wrap">
        ${statusChip(rawStatus)}
        <span class="text-body" style="font-weight:600;font-family:monospace;font-size:11px">${job.jobId}</span>
        <span class="flex-1"></span>
        ${renderTransportBadge(transportMode)}
      </div>
      ${stage ? `<div class="text-caption text-faint">${stage}</div>` : ''}
      ${job.message ? `<div class="text-caption" style="color:var(--color-text-muted)">${_esc(job.message)}</div>` : ''}
      <div class="progress-bar ${rawStatus === 'running' ? 'progress-bar--running' : ''}" style="height:5px">
        <div class="progress-bar__fill" style="width:${pct}%"></div>
      </div>
      <div class="row gap-4 text-caption text-faint">
        <span>${pct}%</span>
        ${totalParts > 0 ? `<span>${doneParts}/${totalParts} parts done</span>` : ''}
        ${failedParts > 0 ? `<span style="color:var(--color-failed)">${failedParts} failed</span>` : ''}
      </div>
    </div>
  `;
}

function renderPartRow(part) {
  const pct = Math.min(100, part.progressPercent ?? 0);
  const active = ['cutting','transcribing','rendering','downloading'].includes(part.status);
  return `
    <div class="part-progress-row">
      <span class="part-progress-row__no text-caption text-faint">${part.partNo}</span>
      <div class="col gap-1 flex-1" style="min-width:0">
        <div class="row gap-2" style="align-items:center">
          <span class="part-item__title">${_esc(part.partName)}</span>
          ${statusChip(part.chipStatus)}
        </div>
        ${active || pct > 0 ? `
          <div class="progress-bar" style="height:2px">
            <div class="progress-bar__fill ${active ? 'progress-bar--running' : ''}" style="width:${pct}%"></div>
          </div>
        ` : ''}
        ${part.message ? `<div class="text-caption text-faint" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(part.message)}</div>` : ''}
      </div>
    </div>
  `;
}

function renderPartsSection(parts) {
  if (!parts.length) {
    return `<div class="text-caption text-faint" style="padding:var(--sp-3) 0">Waiting for parts to start…</div>`;
  }
  return `<div class="card" style="padding:0;overflow:hidden">${parts.map(p => renderPartRow(p)).join('')}</div>`;
}

function renderTerminalBanner(state) {
  const status = state.job?.status ?? state.terminalStatus;
  if (!status || !TERMINAL.has(status)) return '';

  if (status === 'completed' || status === 'completed_with_errors') {
    return `
      <div class="card" style="border-color:var(--color-success)">
        <div class="row gap-4" style="align-items:center;flex-wrap:wrap">
          <div>
            <div class="text-body" style="font-weight:600;color:var(--color-success)">
              ${status === 'completed' ? 'Render complete' : 'Render complete — some parts failed'}
            </div>
            <div class="text-caption text-faint mt-1">Your ranked clips are ready to review.</div>
          </div>
          <span class="flex-1"></span>
          <button class="btn btn-primary" id="monitor-to-results">View Results →</button>
        </div>
      </div>
    `;
  }
  // failed | interrupted
  return `
    <div class="card" style="border-color:var(--color-failed)">
      <div class="row gap-4" style="align-items:center;flex-wrap:wrap">
        <div>
          <div class="text-body" style="font-weight:600;color:var(--color-failed)">
            ${status === 'failed' ? 'Render failed' : 'Render interrupted'}
          </div>
          <div class="text-caption text-faint mt-1">${_esc(state.job?.message ?? 'Check logs for details.')}</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-ghost" id="monitor-to-source">New source</button>
      </div>
    </div>
  `;
}

function renderLogs(state) {
  if (state.logsLoading) return '<div class="text-caption text-faint">Loading…</div>';
  if (!state.logs || !state.logs.length) return '<div class="text-caption text-faint">No log entries.</div>';
  return `<div class="logs-lines">${state.logs.map(l => `<div class="log-line">${_esc(l)}</div>`).join('')}</div>`;
}

/* ── UI update ────────────────────────────────────────────────────── */

function updateUI(el, state) {
  const s = el.querySelector('#mon-summary');
  if (s) s.innerHTML = renderJobSummary(state);

  const p = el.querySelector('#mon-parts');
  if (p) p.innerHTML = renderPartsSection(state.parts);

  const t = el.querySelector('#mon-terminal');
  if (t) {
    t.innerHTML = renderTerminalBanner(state);
    el.querySelector('#monitor-to-results')?.addEventListener('click', () =>
      router.go(`/results/${state.job?.jobId}`)
    );
    el.querySelector('#monitor-to-source')?.addEventListener('click', () => router.go('/source'));
  }

  const e = el.querySelector('#mon-error');
  if (e) e.textContent = state.error ?? '';
}

/* ── Mount ────────────────────────────────────────────────────────── */

export async function mount(el, params) {
  const jobId = params[0];

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Monitor</div>
          <div class="screen__subtitle" style="font-family:monospace;font-size:11px;color:var(--color-text-faint)">${jobId ?? '—'}</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-secondary btn-sm" id="mon-cancel-btn" style="display:none">Cancel</button>
        <button class="btn btn-ghost" id="mon-back-btn">← Studio</button>
      </div>
    </div>
    <div class="screen__body col gap-5">
      <div id="mon-summary"></div>
      <div id="mon-terminal"></div>
      <div>
        <div class="text-section" style="margin-bottom:var(--sp-3)">Parts</div>
        <div id="mon-parts"></div>
      </div>
      <!-- Logs drawer -->
      <div>
        <button class="logs-toggle row gap-2" id="mon-logs-toggle"
          style="align-items:center;width:100%;text-align:left;padding:var(--sp-3) var(--sp-4);background:var(--color-surface);border-radius:var(--radius-control);border:1px solid var(--color-border)">
          <span class="text-body" style="font-weight:600">Logs</span>
          <span class="flex-1"></span>
          <span id="mon-logs-chevron" style="color:var(--color-text-faint);font-size:10px">▼</span>
        </button>
        <div id="mon-logs-body" style="display:none;margin-top:var(--sp-2)">
          <div id="mon-logs-content" class="logs-content" style="font-family:monospace;font-size:11px;line-height:1.6;background:var(--color-surface);border-radius:var(--radius-control);padding:var(--sp-3);max-height:220px;overflow-y:auto;color:var(--color-text-muted)"></div>
        </div>
      </div>
      <div id="mon-error" class="text-caption" style="color:var(--color-failed)"></div>
    </div>
  `;

  el.querySelector('#mon-back-btn')?.addEventListener('click', () => router.go('/studio'));

  if (!jobId) {
    el.querySelector('#mon-summary').innerHTML = `
      <div class="card" style="border-color:var(--color-failed)">
        <div class="text-body" style="color:var(--color-failed)">No job ID provided.</div>
      </div>
    `;
    return;
  }

  // Cancel button
  const cancelBtn = el.querySelector('#mon-cancel-btn');
  cancelBtn?.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    try { await renderApi.cancel(jobId); } catch { /* ignore */ }
  });

  // Logs drawer — lazy load on first open
  let logsOpened = false;
  const logsToggle  = el.querySelector('#mon-logs-toggle');
  const logsBody    = el.querySelector('#mon-logs-body');
  const logsContent = el.querySelector('#mon-logs-content');
  const chevron     = el.querySelector('#mon-logs-chevron');

  logsToggle?.addEventListener('click', async () => {
    const isOpen = logsBody.style.display !== 'none';
    logsBody.style.display = isOpen ? 'none' : '';
    if (chevron) chevron.textContent = isOpen ? '▼' : '▲';
    if (!isOpen && !logsOpened) {
      logsOpened = true;
      await monitorStore.loadLogs();
      if (logsContent) logsContent.innerHTML = renderLogs(monitorStore.getState());
    }
  });

  // Subscribe
  const unsub = monitorStore.subscribe(state => {
    updateUI(el, state);

    if (cancelBtn) cancelBtn.style.display = state.job?.status === 'running' ? '' : 'none';

    // Refresh logs if drawer is open and job is terminal
    if (logsOpened && state.terminal && logsContent) {
      monitorStore.loadLogs().then(() => {
        logsContent.innerHTML = renderLogs(monitorStore.getState());
      });
    }
  });

  monitorStore.start(jobId);

  el.addEventListener('unmount', () => { unsub(); monitorStore.stop(); });
}

export const monitorScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
