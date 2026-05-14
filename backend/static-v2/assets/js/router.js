import { sourceScreen }    from './screens/source.js';
import { studioScreen }    from './screens/studio.js';
import { monitorScreen }   from './screens/monitor.js';
import { resultsScreen }   from './screens/results.js';
import { libraryScreen }   from './screens/library.js';
import { downloadsScreen } from './screens/downloads.js';
import { systemScreen }    from './screens/system.js';
import { shell }           from './components/shell.js';

const ROUTES = [
  { pattern: /^\/source$/,           screen: sourceScreen,    id: 'source'    },
  { pattern: /^\/studio$/,           screen: studioScreen,    id: 'studio'    },
  { pattern: /^\/monitor\/([^/]+)$/, screen: monitorScreen,   id: 'monitor'   },
  { pattern: /^\/results\/([^/]+)$/, screen: resultsScreen,   id: 'results'   },
  { pattern: /^\/library$/,          screen: libraryScreen,   id: 'library'   },
  { pattern: /^\/downloads$/,        screen: downloadsScreen, id: 'downloads' },
  { pattern: /^\/system$/,           screen: systemScreen,    id: 'system'    },
];

const DEFAULT_PATH = '/source';

function parsePath(hash) {
  return hash.replace(/^#/, '') || DEFAULT_PATH;
}

function match(path) {
  for (const route of ROUTES) {
    const m = path.match(route.pattern);
    if (m) return { route, params: m.slice(1) };
  }
  return null;
}

let _currentId = null;

async function navigate(path) {
  const result = match(path);
  if (!result) {
    window.location.hash = DEFAULT_PATH;
    return;
  }

  const { route, params } = result;

  shell.setActiveNav(route.id);

  if (_currentId === route.id && params.length === 0) return;
  _currentId = route.id;

  const workspace = document.querySelector('.shell__workspace');
  if (!workspace) return;

  // Unmount previous screen gracefully, preserving persistent shell elements
  const prev = workspace.querySelector('.screen');
  if (prev) {
    try { prev.dispatchEvent(new Event('unmount')); } catch { /* ignore */ }
    prev.remove();
  }

  const el = document.createElement('div');
  el.className = 'screen';
  workspace.appendChild(el);

  // Error boundary: screen crashes are caught and shown as recovery card
  try {
    await route.screen.mount(el, params);
  } catch (err) {
    console.error(`[router] Screen "${route.id}" crashed:`, err);
    _renderBoundary(el, () => navigate(path));
  }
}

function _renderBoundary(el, onRetry) {
  el.innerHTML = `
    <div class="screen__header">
      <div class="screen__title">Something went wrong</div>
      <div class="screen__subtitle">This screen encountered an unexpected problem.</div>
    </div>
    <div class="screen__body">
      <div class="eb-card">
        <div class="row gap-3" style="align-items:flex-start">
          <span class="eb-card__icon" aria-hidden="true">⚠</span>
          <div class="col gap-2">
            <div class="text-body" style="font-weight:600">The screen couldn't load</div>
            <div class="text-caption text-faint">This is usually temporary. Try reloading the screen, or go back to Source to start over.</div>
          </div>
        </div>
        <div class="row gap-3 mt-4">
          <button class="btn btn-primary" id="eb-retry">Reload screen</button>
          <a class="btn btn-ghost" href="#/source">← Back to Source</a>
        </div>
      </div>
    </div>
  `;
  el.querySelector('#eb-retry')?.addEventListener('click', onRetry);
}

function onHashChange() {
  navigate(parsePath(window.location.hash));
}

function init() {
  window.addEventListener('hashchange', onHashChange);
  navigate(parsePath(window.location.hash));
}

function go(path) {
  window.location.hash = path;
}

export const router = { init, go };
