/* NavRail — left 72px column.
   4 enabled: source, studio, monitor, results
   4 disabled: analytics, library, settings, help
*/

import { router } from '../router.js';

const NAV_ITEMS = [
  {
    id: 'source',
    label: 'Source',
    route: '/source',
    enabled: true,
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="3" y="3" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M7 17h6M10 13v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
  },
  {
    id: 'studio',
    label: 'Studio',
    route: '/studio',
    enabled: true,
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/>
      <path d="M8 7.5l5 2.5-5 2.5V7.5z" fill="currentColor"/>
    </svg>`,
  },
  {
    id: 'monitor',
    label: 'Monitor',
    route: '/monitor',
    enabled: true,
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M3 13l4-4 3 3 4-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,
  },
  {
    id: 'results',
    label: 'Results',
    route: '/results',
    enabled: true,
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M5 10h10M5 6h10M5 14h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
  },
];

const DISABLED_ITEMS = [
  { id: 'analytics', label: 'Analytics', icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 14l4-5 3 3 4-6 3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>` },
  { id: 'library',   label: 'Library',   icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="4" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="4" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="15" y="6" width="2" height="10" rx="1" stroke="currentColor" stroke-width="1.5"/></svg>` },
  { id: 'settings',  label: 'Settings',  icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/><path d="M10 3v1.5M10 15.5V17M3 10h1.5M15.5 10H17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>` },
  { id: 'help',      label: 'Help',      icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M10 14v-1M10 11c0-1.5 2-2 2-3.5a2 2 0 00-4 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>` },
];

let _container = null;
let _activeId = 'source';

function renderItem(item, disabled = false) {
  const isActive = !disabled && item.id === _activeId;
  const cls = [
    'nav-rail-item',
    isActive   ? 'nav-rail-item--active'   : '',
    disabled   ? 'nav-rail-item--disabled' : '',
  ].filter(Boolean).join(' ');

  const el = document.createElement('button');
  el.className = cls;
  el.dataset.navId = item.id;
  el.setAttribute('title', item.label);
  el.innerHTML = `<span class="nav-rail-icon">${item.icon}</span><span>${item.label}</span>`;

  if (!disabled) {
    el.addEventListener('click', () => router.go(item.route));
  }
  return el;
}

function render() {
  if (!_container) return;
  _container.innerHTML = '';

  for (const item of NAV_ITEMS) {
    _container.appendChild(renderItem(item, false));
  }

  const divider = document.createElement('div');
  divider.className = 'nav-rail-divider';
  _container.appendChild(divider);

  for (const item of DISABLED_ITEMS) {
    _container.appendChild(renderItem(item, true));
  }
}

function mount(container) {
  _container = container;
  render();
}

function setActive(id) {
  _activeId = id;
  if (!_container) return;
  _container.querySelectorAll('.nav-rail-item').forEach(el => {
    el.classList.toggle('nav-rail-item--active', el.dataset.navId === id);
  });
}

export const navRail = { mount, setActive };
