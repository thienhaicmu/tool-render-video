/* NavRail — UI-R5B creator-first navigation.
   Primary:  Create, Projects
   Bottom:   Settings (separated by flex spacer)
   Hidden:   Monitor, Downloads (accessible via render bar / direct URL)

   setActive(id) accepts both new canonical IDs ('create','projects','settings')
   and legacy IDs ('source','studio','results','library','system') so that
   backward-compatible routes still highlight the correct nav item.
*/

import { router } from '../router.js';

const PRIMARY_ITEMS = [
  {
    id: 'create',
    label: 'Create',
    route: '/create',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
    </svg>`,
  },
  {
    id: 'projects',
    label: 'Projects',
    route: '/projects',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="3" y="3" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
      <rect x="11" y="3" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
      <rect x="3" y="11" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
      <rect x="11" y="11" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,
  },
];

const SETTINGS_ITEM = {
  id: 'settings',
  label: 'Settings',
  route: '/settings',
  icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/>
    <path d="M10 3v1.5M10 15.5V17M3 10h1.5M15.5 10H17M4.93 4.93l1.06 1.06M13.01 13.01l1.06 1.06M15.07 4.93l-1.06 1.06M6.99 13.01l-1.06 1.06"
      stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  </svg>`,
};

/* Legacy-to-canonical ID map — ensures backward-compat routes highlight correctly */
const NAV_ID_MAP = {
  source:    'create',
  studio:    'create',
  results:   'projects',
  library:   'projects',
  system:    'settings',
  // canonical passthrough
  create:    'create',
  projects:  'projects',
  settings:  'settings',
  // no highlight for monitor / downloads
  monitor:   null,
  downloads: null,
};

let _container = null;
let _activeId  = 'create';

function _renderItem(item, { utility = false } = {}) {
  const isActive = item.id === _activeId;
  const cls = [
    'nav-rail-item',
    isActive ? 'nav-rail-item--active'  : '',
    utility  ? 'nav-rail-item--utility' : '',
  ].filter(Boolean).join(' ');

  const el = document.createElement('button');
  el.className = cls;
  el.dataset.navId = item.id;
  el.setAttribute('title', item.label);
  if (isActive) el.setAttribute('aria-current', 'page');
  el.innerHTML = `<span class="nav-rail-icon" aria-hidden="true">${item.icon}</span><span>${item.label}</span>`;
  el.addEventListener('click', () => router.go(item.route));
  return el;
}

function _spacer() {
  const d = document.createElement('div');
  d.className = 'nav-rail-spacer';
  return d;
}

function _render() {
  if (!_container) return;
  _container.innerHTML = '';

  for (const item of PRIMARY_ITEMS) {
    _container.appendChild(_renderItem(item));
  }

  _container.appendChild(_spacer());
  _container.appendChild(_renderItem(SETTINGS_ITEM, { utility: true }));
}

function mount(container) {
  _container = container;
  container.setAttribute('role', 'navigation');
  container.setAttribute('aria-label', 'Main navigation');
  _render();
}

function setActive(id) {
  /* Resolve legacy or null IDs to canonical nav IDs */
  const canonical = id != null ? (NAV_ID_MAP[id] ?? null) : null;
  _activeId = canonical ?? _activeId;

  if (!_container) return;
  _container.querySelectorAll('.nav-rail-item').forEach(el => {
    const isActive = el.dataset.navId === canonical;
    el.classList.toggle('nav-rail-item--active', isActive);
    if (isActive) el.setAttribute('aria-current', 'page');
    else          el.removeAttribute('aria-current');
  });
}

export const navRail = { mount, setActive };
