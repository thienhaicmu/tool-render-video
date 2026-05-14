/* AIBadge — renders an inline AI state badge.
   states: disabled advisory applied skipped blocked unavailable
*/

const LABELS = {
  disabled:    'AI Off',
  advisory:    'AI Advisory',
  applied:     'AI Applied',
  skipped:     'AI Skipped',
  blocked:     'AI Blocked',
  unavailable: 'AI N/A',
};

export function aiBadge(state) {
  const safe = LABELS[state] ? state : 'unavailable';
  const label = LABELS[safe];
  return `<span class="ai-badge ai-badge--${safe}">${label}</span>`;
}

export function aiBadgeElement(state) {
  const span = document.createElement('span');
  span.className = `ai-badge ai-badge--${LABELS[state] ? state : 'unavailable'}`;
  span.textContent = LABELS[state] ?? 'AI N/A';
  return span;
}
