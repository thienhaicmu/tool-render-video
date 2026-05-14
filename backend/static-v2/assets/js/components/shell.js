/* Shell — mounts the 4-panel layout and wires up sub-components. */

import { navRail } from './nav-rail.js';
import { systemStore } from '../store/system.js';

function render() {
  return `
    <div class="shell">
      <nav class="shell__nav" id="shell-nav"></nav>
      <main class="shell__workspace" id="shell-workspace"></main>
      <aside class="shell__panel" id="shell-panel">
        <div class="panel-section">
          <div class="panel-section__title">Context</div>
          <div id="panel-content" class="text-caption text-faint">Select a job to see details.</div>
        </div>
      </aside>
      <footer class="shell__strip" id="shell-strip">
        <span class="text-caption text-faint" id="strip-status">Ready</span>
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
    const strip = root.querySelector('#strip-mode');
    if (strip) {
      strip.textContent = `Mode: ${state.executionMode}`;
    }
    const status = root.querySelector('#strip-status');
    if (status) {
      status.textContent = state.backendReady ? 'Backend ready' : state.error ? `Backend error` : 'Connecting…';
    }
  });
}

function setActiveNav(id) {
  navRail.setActive(id);
}

export const shell = { render, mount, setActiveNav };
