/* Shell — mounts the 4-panel layout and wires up sub-components.
   #shell-backend-banner lives inside #shell-workspace so it persists across
   route changes. The router removes only .screen elements, not the banner.
*/

import { navRail }     from './nav-rail.js';
import { systemStore } from '../store/system.js';

function render() {
  return `
    <div class="shell">
      <nav class="shell__nav" id="shell-nav"></nav>
      <main class="shell__workspace" id="shell-workspace">
        <div id="shell-backend-banner" class="shell-backend-banner" style="display:none" role="alert" aria-live="polite"></div>
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
    import('../store/system.js').then(m => m.systemStore.refresh());
  });
}

function setActiveNav(id) {
  navRail.setActive(id);
}

export const shell = { render, mount, setActiveNav };
