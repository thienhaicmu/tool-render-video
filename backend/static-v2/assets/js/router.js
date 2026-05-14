import { sourceScreen }    from './screens/source.js';
import { studioScreen }    from './screens/studio.js';
import { monitorScreen }   from './screens/monitor.js';
import { resultsScreen }   from './screens/results.js';
import { libraryScreen }   from './screens/library.js';
import { downloadsScreen } from './screens/downloads.js';
import { shell }           from './components/shell.js';

const ROUTES = [
  { pattern: /^\/source$/,           screen: sourceScreen,    id: 'source'    },
  { pattern: /^\/studio$/,           screen: studioScreen,    id: 'studio'    },
  { pattern: /^\/monitor\/([^/]+)$/, screen: monitorScreen,   id: 'monitor'   },
  { pattern: /^\/results\/([^/]+)$/, screen: resultsScreen,   id: 'results'   },
  { pattern: /^\/library$/,          screen: libraryScreen,   id: 'library'   },
  { pattern: /^\/downloads$/,        screen: downloadsScreen, id: 'downloads' },
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

  workspace.innerHTML = '';
  const el = document.createElement('div');
  el.className = 'screen';
  workspace.appendChild(el);

  await route.screen.mount(el, params);
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
