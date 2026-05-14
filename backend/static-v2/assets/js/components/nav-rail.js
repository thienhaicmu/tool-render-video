/* NavRail — left 72px column.
   Workflow: source, studio, monitor, results, library
   Utilities: downloads, system
   Disabled: publish
*/

import { router } from '../router.js';

const WORKFLOW_ITEMS = [
  {
    id: 'source',
    label: 'Source',
    route: '/source',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="3" y="3" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M7 17h6M10 13v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
  },
  {
    id: 'studio',
    label: 'Studio',
    route: '/studio',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 7.5l5 2.5-5 2.5V7.5z" fill="currentColor"/>
    </svg>`,
  },
  {
    id: 'monitor',
    label: 'Monitor',
    route: '/monitor',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M3 13l4-4 3 3 4-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,
  },
  {
    id: 'results',
    label: 'Results',
    route: '/results',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M5 10h10M5 6h10M5 14h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
  },
  {
    id: 'library',
    label: 'Library',
    route: '/library',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="4" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="4" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="15" y="6" width="2" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/></svg>`,
  },
];

const UTILITY_ITEMS = [
  {
    id: 'downloads',
    label: 'Downloads',
    route: '/downloads',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 3v9M6 8l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 14v1a2 2 0 002 2h8a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  },
  {
    id: 'system',
    label: 'System',
    route: '/system',
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/><path d="M10 3v1.5M10 15.5V17M3 10h1.5M15.5 10H17M4.93 4.93l1.06 1.06M13.01 13.01l1.06 1.06M15.07 4.93l-1.06 1.06M6.99 13.01l-1.06 1.06" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  },
];

const DISABLED_ITEMS = [
  { id: 'publish', label: 'Publish', icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 13V4M6 7l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 14v1a2 2 0 002 2h8a2 2 0 002-2v-1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>` },
];

let _container = null;
let _activeId = 'source';

function renderItem(item, disabled = false, utility = false) {
  const isActive = !disabled && item.id === _activeId;
  const cls = [
    'nav-rail-item',
    isActive   ? 'nav-rail-item--active'   : '',
    disabled   ? 'nav-rail-item--disabled' : '',
    utility    ? 'nav-rail-item--utility'  : '',
  ].filter(Boolean).join(' ');

  const el = document.createElement('button');
  el.className = cls;
  el.dataset.navId = item.id;
  el.setAttribute('title', item.label);
  if (isActive)  el.setAttribute('aria-current', 'page');
  if (disabled) { el.setAttribute('aria-disabled', 'true'); el.setAttribute('tabindex', '-1'); }
  el.innerHTML = `<span class="nav-rail-icon" aria-hidden="true">${item.icon}</span><span>${item.label}</span>`;

  if (!disabled) {
    el.addEventListener('click', () => router.go(item.route));
  }
  return el;
}

function _divider() {
  const d = document.createElement('div');
  d.className = 'nav-rail-divider';
  return d;
}

function render() {
  if (!_container) return;
  _container.innerHTML = '';

  for (const item of WORKFLOW_ITEMS) {
    _container.appendChild(renderItem(item, false, false));
  }

  _container.appendChild(_divider());

  for (const item of UTILITY_ITEMS) {
    _container.appendChild(renderItem(item, false, true));
  }

  _container.appendChild(_divider());

  for (const item of DISABLED_ITEMS) {
    _container.appendChild(renderItem(item, true, false));
  }
}

function mount(container) {
  _container = container;
  container.setAttribute('role', 'navigation');
  container.setAttribute('aria-label', 'Main navigation');
  render();
}

function setActive(id) {
  _activeId = id;
  if (!_container) return;
  _container.querySelectorAll('.nav-rail-item').forEach(el => {
    const isActive = el.dataset.navId === id;
    el.classList.toggle('nav-rail-item--active', isActive);
    if (isActive) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
}

export const navRail = { mount, setActive };
