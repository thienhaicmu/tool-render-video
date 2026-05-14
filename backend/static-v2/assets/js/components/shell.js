/* Shell — mounts the 4-panel layout and wires up sub-components.
   #shell-backend-banner and #shell-render-bar both live inside #shell-workspace
   so they persist across route changes. The router only removes .screen elements.
*/

import { navRail }            from './nav-rail.js';
import { systemStore }        from '../store/system.js';
import { renderSessionStore } from '../store/render-session.js';
import { router }             from '../router.js';

const _STAGE_LABELS = {
  queued:             'Waiting to start',
  downloading:        'Fetching video',
  scene_detection:    'Finding scenes',
  segment_building:   'Cutting clips',
  transcribing_full:  'Transcribing speech',
  rendering:          'Rendering clips',
  rendering_parallel: 'Rendering clips',
  writing_report:     'Finalising results',
};

function render() {
  return `
    <div class="shell">
      <nav class="shell__nav" id="shell-nav"></nav>
      <main class="shell__workspace" id="shell-workspace">
        <div id="shell-backend-banner" class="shell-backend-banner" style="display:none" role="alert" aria-live="polite"></div>
        <div id="shell-render-bar" class="shell-render-bar" style="display:none" role="status" aria-live="polite"></div>
      </main>
      <aside class="shell__panel" id="shell-panel">
        <div class="panel-section">
          <div class="panel-section__title">Context</div>
          <div id="panel-content" class="text-caption text-faint">Select a job to see details.</div>
        </div>
      </aside>
      <footer class="shell__strip" id="shell-strip">
        <span class="text-caption text-faint" id="strip-status">Connecting…</span>
        <span class="flex-1"></span>
        <span class="text-caption text-faint" id="strip-mode"></span>
      </footer>
    </div>
  `.trim();
}

function mount(root) {
  const nav = root.querySelector('#shell-nav');
  navRail.mount(nav);

  systemStore.subscribe(state => {
    _updateStrip(root, state);
    _updateBanner(root, state);
  });

  renderSessionStore.subscribe(state => {
    _updateRenderBar(root, state);
  });
}

function _updateStrip(root, state) {
  const strip = root.querySelector('#strip-status');
  if (strip) {
    if (state.backendReady)  strip.textContent = 'Backend ready';
    else if (state.error)    strip.textContent = 'Backend unavailable';
    else                     strip.textContent = 'Connecting…';
  }
  const mode = root.querySelector('#strip-mode');
  if (mode) {
    mode.textContent = state.backendReady ? `Mode: ${state.executionMode}` : '';
  }
}

function _updateBanner(root, state) {
  const banner = root.querySelector('#shell-backend-banner');
  if (!banner) return;

  if (state.backendReady) {
    banner.style.display = 'none';
    banner.innerHTML = '';
    return;
  }

  banner.style.display = '';
  banner.innerHTML = `
    <div class="backend-banner row gap-3" style="align-items:center">
      <span class="backend-banner__icon" aria-hidden="true">⚡</span>
      <span class="text-caption">Backend is not ready yet. Try again in a moment.</span>
      <span class="flex-1"></span>
      <button class="btn btn-ghost backend-banner__retry" style="font-size:12px;padding:2px 10px" id="banner-retry">Retry</button>
    </div>
  `;
  banner.querySelector('#banner-retry')?.addEventListener('click', () => {
    systemStore.refresh();
  });
}

function _updateRenderBar(root, state) {
  const bar = root.querySelector('#shell-render-bar');
  if (!bar) return;

  if (!state.active) {
    bar.style.display = 'none';
    bar.innerHTML = '';
    return;
  }

  const pct        = Math.round(state.progressPercent ?? 0);
  const rawStage   = state.stage ?? '';
  const stageLabel = _STAGE_LABELS[rawStage] || (rawStage ? rawStage.replace(/_/g, ' ') : 'Rendering');
  const clipsText  = state.totalParts > 0
    ? `${state.doneParts}/${state.totalParts} clips`
    : '';

  bar.style.display = '';
  bar.innerHTML = `
    <div class="render-bar row gap-3" style="align-items:center">
      <div class="render-bar__progress-track" aria-hidden="true">
        <div class="render-bar__progress-fill" style="width:${pct}%"></div>
      </div>
      <span class="render-bar__stage text-caption">${_esc(stageLabel)}</span>
      ${clipsText ? `<span class="render-bar__sep text-caption text-faint" aria-hidden="true">·</span><span class="render-bar__clips text-caption text-faint">${_esc(clipsText)}</span>` : ''}
      <span class="render-bar__sep text-caption text-faint" aria-hidden="true">·</span>
      <span class="text-caption" style="font-variant-numeric:tabular-nums;font-weight:600">${pct}%</span>
      <span class="flex-1"></span>
      <button class="btn btn-ghost render-bar__btn" id="render-bar-open">Open Monitor</button>
    </div>
  `;

  bar.querySelector('#render-bar-open')?.addEventListener('click', () => {
    const { jobId } = renderSessionStore.getState();
    if (jobId) router.go(`/monitor/${jobId}`);
  });
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setActiveNav(id) {
  navRail.setActive(id);
}

export const shell = { render, mount, setActiveNav };
