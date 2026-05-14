/* Monitor screen — live job stream, premium stage banner, transport badge,
   clip status table, terminal CTAs (View Results / Retry / Resume), logs drawer.
   Route recovery: if no jobId given but renderSessionStore has an active render,
   redirects immediately. If jobId present, always loads from transport.
   Loading timeout: 20s with inline retry if no data arrives.
*/

import { monitorStore }       from '../store/monitor.js';
import { renderSessionStore } from '../store/render-session.js';
import { statusChip }         from '../components/status-chip.js';
import { partStatusList }     from '../components/part-status-list.js';
import { logDrawerShell, wireLogDrawer } from '../components/log-drawer.js';
import { router }             from '../router.js';
import { renderApi }          from '../api/render.js';

const TERMINAL       = new Set(['completed', 'completed_with_errors', 'failed', 'interrupted']);
const CONNECT_TIMEOUT_MS = 20_000;

const STAGE_LABELS = {
  queued:              'Waiting to start',
  starting:            'Starting up…',
  downloading:         'Fetching your video',
  scene_detection:     'Finding scenes',
  segment_building:    'Cutting clips',
  transcribing_full:   'Transcribing speech',
  rendering:           'Rendering your clips',
  rendering_parallel:  'Rendering clips',
  writing_report:      'Finalising results',
  done:                'Done',
  failed:              'Failed',
};

/* ── Sub-renders ──────────────────────────────────────────────────────── */

function renderTransportBadge(mode) {
  const map = {
    websocket:     { label: '● Live',       color: 'var(--color-success)'    },
    polling:       { label: '○ Polling',    color: 'var(--color-warning)'    },
    connecting:    { label: '⋯ Connecting', color: 'var(--color-text-faint)' },
    terminal_poll: { label: '● Done',       color: 'var(--color-success)'    },
  };
  const { label, color } = map[mode] ?? { label: mode ?? '—', color: 'var(--color-text-faint)' };
  return `<span class="transport-badge" style="color:${color}">${label}</span>`;
}

function renderProgressCard(state) {
  const { job, summary, transportMode } = state;

  if (!job) {
    return `
      <div class="monitor-progress-card col gap-3">
        <div class="skeleton-line" style="height:14px;width:40%"></div>
        <div class="skeleton-block" style="height:6px;border-radius:3px"></div>
        <div class="skeleton-line" style="height:12px;width:30%"></div>
      </div>
    `;
  }

  const rawStatus   = job.status === 'completed_with_errors' ? 'partial' : job.status;
  const pct         = Math.min(100, job.progressPercent ?? summary?.overall_progress_percent ?? 0);
  const stage       = job.stage ?? summary?.current_stage ?? '';
  const stageLabel  = STAGE_LABELS[stage] || (stage ? stage.replace(/_/g, ' ') : '');
  const isRunning   = rawStatus === 'running';
  const totalParts  = summary?.total_parts ?? 0;
  const doneParts   = summary?.completed_parts ?? 0;
  const failedParts = summary?.failed_parts ?? 0;
  const activeParts = summary?.processing_parts ?? summary?.in_progress_count ?? 0;

  return `
    <div class="monitor-progress-card">
      <div class="row gap-3" style="align-items:center;margin-bottom:var(--sp-3);flex-wrap:wrap">
        ${statusChip(rawStatus)}
        <code class="text-caption" style="font-family:monospace;color:var(--color-text-faint)">${job.jobId.slice(0, 14)}…</code>
        <span class="flex-1"></span>
        ${renderTransportBadge(transportMode)}
      </div>

      ${stageLabel ? `<div class="monitor-stage-text">${_esc(stageLabel)}</div>` : ''}
      ${job.message && !stageLabel ? `<div class="text-body" style="color:var(--color-text-muted)">${_esc(job.message)}</div>` : ''}

      <div class="progress-bar ${isRunning ? 'progress-bar--running' : ''}"
           style="height:6px;margin:var(--sp-3) 0">
        <div class="progress-bar__fill" style="width:${pct}%"></div>
      </div>

      <div class="row gap-4 text-caption text-faint" style="flex-wrap:wrap">
        <span style="font-variant-numeric:tabular-nums;font-weight:600;color:var(--color-text)">${pct}%</span>
        ${totalParts  > 0 ? `<span>${doneParts} / ${totalParts} clips</span>` : ''}
        ${activeParts > 0 ? `<span style="color:var(--color-running)">${activeParts} running</span>` : ''}
        ${failedParts > 0 ? `<span style="color:var(--color-failed)">${failedParts} failed</span>` : ''}
        ${job.message && stageLabel ? `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--color-text-muted)">${_esc(job.message)}</span>` : ''}
      </div>
    </div>
  `;
}

function renderTerminalBanner(state) {
  const status = state.job?.status ?? state.terminalStatus;
  if (!status || !TERMINAL.has(status)) return '';

  if (status === 'completed' || status === 'completed_with_errors') {
    const completedParts = state.summary?.completed_parts ?? 0;
    const totalParts     = state.summary?.total_parts ?? 0;
    const clipNote       = totalParts > 0
      ? `${completedParts} of ${totalParts} clips ranked and ready.`
      : 'Your ranked clips are ready to review.';

    return `
      <div class="card terminal-banner terminal-banner--success">
        <div class="row gap-4" style="align-items:center;flex-wrap:wrap">
          <div>
            <div class="terminal-banner__title" style="color:var(--color-success)">
              ${status === 'completed' ? 'Render complete' : 'Render complete — some clips failed'}
            </div>
            <div class="text-caption text-faint mt-1">${_esc(clipNote)}</div>
          </div>
          <span class="flex-1"></span>
          <button class="btn btn-primary" id="monitor-to-results">View Results →</button>
        </div>
      </div>
    `;
  }

  // failed | interrupted
  const canRetry  = status === 'failed';
  const canResume = status === 'interrupted';
  const reasonMsg = state.job?.message ?? 'An error occurred during rendering.';
  const hintMsg   = canResume
    ? 'You can resume where it left off.'
    : 'Check logs below for more detail.';

  return `
    <div class="card terminal-banner terminal-banner--failed">
      <div class="row gap-4" style="align-items:center;flex-wrap:wrap">
        <div>
          <div class="terminal-banner__title" style="color:var(--color-failed)">
            ${status === 'failed' ? 'Render failed' : 'Render interrupted'}
          </div>
          <div class="text-caption text-faint mt-1">${_esc(reasonMsg)}</div>
          <div class="text-caption text-faint">${hintMsg}</div>
        </div>
        <span class="flex-1"></span>
        ${canResume ? `<button class="btn btn-secondary" id="monitor-resume-btn">Resume render</button>` : ''}
        ${canRetry  ? `<button class="btn btn-secondary" id="monitor-retry-btn">Retry render</button>`  : ''}
        <button class="btn btn-ghost" id="monitor-to-source">Start over</button>
      </div>
    </div>
  `;
}

/* ── UI update (partial DOM patch — no full re-render) ────────────────── */

function updateUI(el, state) {
  const prog = el.querySelector('#mon-progress');
  if (prog) prog.innerHTML = renderProgressCard(state);

  const parts = el.querySelector('#mon-parts');
  if (parts) parts.innerHTML = partStatusList(state.parts);

  const term = el.querySelector('#mon-terminal');
  if (term) {
    term.innerHTML = renderTerminalBanner(state);
    _wireTerminalButtons(el, term, state);
  }

  const errEl = el.querySelector('#mon-error');
  if (errEl) errEl.textContent = state.error ?? '';
}

function _wireTerminalButtons(el, term, state) {
  const jobId = state.job?.jobId ?? monitorStore.getState().jobId;

  term.querySelector('#monitor-to-results')?.addEventListener('click', () =>
    router.go(`/projects/${jobId}`)
  );
  term.querySelector('#monitor-to-source')?.addEventListener('click', () =>
    router.go('/create')
  );
  term.querySelector('#monitor-retry-btn')?.addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    try { await renderApi.retry(jobId); } catch { /* backend will report status */ }
  });
  term.querySelector('#monitor-resume-btn')?.addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    try { await renderApi.resume(jobId); } catch { /* backend will report status */ }
  });
}

/* ── Mount ────────────────────────────────────────────────────────────── */

export async function mount(el, params) {
  const jobId = params[0];

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Monitor</div>
          <div class="screen__subtitle">Live render progress</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-secondary btn-sm" id="mon-cancel-btn" style="display:none">Cancel render</button>
        <button class="btn btn-ghost" id="mon-back-btn">← Create</button>
      </div>
    </div>
    <div class="screen__body col gap-5">
      <div id="mon-progress"></div>
      <div id="mon-timeout-banner" style="display:none"></div>
      <div id="mon-terminal"></div>
      <div>
        <div class="text-section" style="margin-bottom:var(--sp-3)">Clips</div>
        <div id="mon-parts"></div>
      </div>
      <div style="margin-top:var(--sp-2)">
        ${logDrawerShell()}
      </div>
      <div id="mon-error" class="text-caption" style="color:var(--color-failed)"></div>
    </div>
  `;

  el.querySelector('#mon-back-btn')?.addEventListener('click', () => router.go('/create'));

  if (!jobId) {
    // Route recovery — redirect to active render if one is known
    const session = renderSessionStore.getState();
    if (session.jobId && session.active) {
      router.go(`/monitor/${session.jobId}`);
      return;
    }

    // No active render — show helpful empty state
    const prog = el.querySelector('#mon-progress');
    if (prog) {
      prog.innerHTML = `
        <div class="monitor-no-job col gap-4" style="padding:var(--sp-8) 0;text-align:center">
          <div style="font-size:40px;line-height:1;opacity:0.15" aria-hidden="true">▶</div>
          <div>
            <div class="text-body" style="font-weight:700;margin-bottom:var(--sp-1)">No render in progress</div>
            <div class="text-caption text-faint" style="max-width:300px;margin:0 auto">
              Start a render from Create, or review a past job in Projects.
            </div>
          </div>
          <div class="row gap-3" style="justify-content:center">
            <button class="btn btn-primary" id="mon-empty-studio">← Start Creating</button>
            <button class="btn btn-secondary" id="mon-empty-library">Open Projects</button>
          </div>
        </div>
      `;
      prog.querySelector('#mon-empty-studio')?.addEventListener('click', () => router.go('/create'));
      prog.querySelector('#mon-empty-library')?.addEventListener('click', () => router.go('/projects'));
    }
    return;
  }

  // Cancel button
  const cancelBtn = el.querySelector('#mon-cancel-btn');
  cancelBtn?.addEventListener('click', async () => {
    cancelBtn.disabled = true;
    try { await renderApi.cancel(jobId); } catch { /* ignore */ }
  });

  // Connection timeout — if no job data arrives in 20s, show retry option
  let _connectTimer = setTimeout(() => {
    if (!monitorStore.getState().job) {
      _showTimeoutBanner(el, jobId);
    }
  }, CONNECT_TIMEOUT_MS);

  // Log drawer — lazy load on first open, refresh when terminal
  const logDrawerCtrl = wireLogDrawer(el, async () => {
    await monitorStore.loadLogs();
    return monitorStore.getState().logs ?? [];
  });

  // Subscribe
  const unsub = monitorStore.subscribe(state => {
    // Clear timeout once first data arrives
    if (state.job && _connectTimer) {
      clearTimeout(_connectTimer);
      _connectTimer = null;
      const banner = el.querySelector('#mon-timeout-banner');
      if (banner) banner.style.display = 'none';
    }

    updateUI(el, state);

    if (cancelBtn) {
      cancelBtn.style.display = state.job?.status === 'running' ? '' : 'none';
    }

    // Refresh logs if terminal and drawer has already been opened
    if (state.terminal && logDrawerCtrl?.isLoaded()) {
      monitorStore.loadLogs().then(() => {
        logDrawerCtrl.refresh(monitorStore.getState().logs ?? []);
      });
    }
  });

  monitorStore.start(jobId);

  el.addEventListener('unmount', () => {
    if (_connectTimer) { clearTimeout(_connectTimer); _connectTimer = null; }
    unsub();
    monitorStore.stop();
  });
}

function _showTimeoutBanner(el, jobId) {
  const banner = el.querySelector('#mon-timeout-banner');
  if (!banner) return;
  banner.style.display = '';
  banner.innerHTML = `
    <div class="card" style="border-color:var(--color-warning)">
      <div class="row gap-3" style="align-items:center;flex-wrap:wrap">
        <div>
          <div class="text-body" style="font-weight:600;color:var(--color-warning)">Taking longer than expected</div>
          <div class="text-caption text-faint mt-1">No job data has arrived yet. The backend may be busy or the job may not exist.</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-secondary" id="mon-timeout-retry">Retry</button>
        <button class="btn btn-ghost" onclick="window.location.hash='/library'">Library</button>
      </div>
    </div>
  `;
  banner.querySelector('#mon-timeout-retry')?.addEventListener('click', () => {
    banner.style.display = 'none';
    monitorStore.stop();
    monitorStore.start(jobId);
  });
}

export const monitorScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
