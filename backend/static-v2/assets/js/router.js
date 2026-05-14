import { createScreen }   from './screens/create.js';
import { projectsScreen } from './screens/projects.js';
import { monitorScreen }  from './screens/monitor.js';
import { settingsScreen } from './screens/system.js';
import { downloadsScreen } from './screens/downloads.js';
import { shell }          from './components/shell.js';

/* ── Route table ────────────────────────────────────────────────────────
   Each route has:
     pattern — RegExp matched against the hash path
     screen  — screen module with a mount(el, params) function
     id      — internal route identifier (used for dedup)
     navId   — which nav-rail item to highlight (null = no highlight)

   Canonical routes (new IA):
     /create          — Import phase (source) or Brief phase (studio)
     /projects        — Project history (library)
     /projects/:jobId — Clip review (results) for a specific job
     /settings        — System settings and diagnostics

   Legacy routes (preserved for backward compatibility, bookmarks, state recovery):
     /source, /studio → createScreen  (same experience, backward compat)
     /results/:jobId  → projectsScreen (clip review under new IA)
     /library         → projectsScreen (history under new IA)
     /system          → settingsScreen
     /monitor/:jobId  → monitorScreen  (not in nav; accessible via render bar)
     /downloads       → downloadsScreen (not in nav; accessible via direct URL)
────────────────────────────────────────────────────────────────────── */

const ROUTES = [
  // ── Canonical routes (new IA) ─────────────────────────────────────
  { pattern: /^\/create$/,            screen: createScreen,   id: 'create',   navId: 'create'   },
  { pattern: /^\/projects$/,          screen: projectsScreen, id: 'projects', navId: 'projects' },
  { pattern: /^\/projects\/([^/]+)$/, screen: projectsScreen, id: 'projects', navId: 'projects' },
  { pattern: /^\/settings$/,          screen: settingsScreen, id: 'settings', navId: 'settings' },

  // ── Legacy routes (preserved, backward compatible) ─────────────────
  { pattern: /^\/source$/,            screen: createScreen,   id: 'source',   navId: 'create'   },
  { pattern: /^\/studio$/,            screen: createScreen,   id: 'studio',   navId: 'create'   },
  { pattern: /^\/results\/([^/]+)$/,  screen: projectsScreen, id: 'results',  navId: 'projects' },
  { pattern: /^\/library$/,           screen: projectsScreen, id: 'library',  navId: 'projects' },
  { pattern: /^\/system$/,            screen: settingsScreen, id: 'system',   navId: 'settings' },

  // ── Utility routes (not in nav) ────────────────────────────────────
  { pattern: /^\/monitor\/([^/]+)$/,  screen: monitorScreen,  id: 'monitor',  navId: null       },
  { pattern: /^\/downloads$/,         screen: downloadsScreen, id: 'downloads', navId: null     },
];

const DEFAULT_PATH = '/create';

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

  shell.setActiveNav(route.navId);

  const shellEl = document.querySelector('.shell');
  if (shellEl) shellEl.dataset.route = route.id;

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
            <div class="text-caption text-faint">This is usually temporary. Try reloading the screen, or go back to Create to start over.</div>
          </div>
        </div>
        <div class="row gap-3 mt-4">
          <button class="btn btn-primary" id="eb-retry">Reload screen</button>
          <a class="btn btn-ghost" href="#/create">← Start over</a>
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
