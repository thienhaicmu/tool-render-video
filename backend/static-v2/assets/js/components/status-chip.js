/* StatusChip — renders an inline status badge.
   states: queued running completed partial failed interrupted unsupported unavailable
*/

const LABELS = {
  queued:      'Queued',
  running:     'Running',
  completed:   'Done',
  partial:     'Partial',
  failed:      'Failed',
  interrupted: 'Interrupted',
  unsupported: 'Unsupported',
  unavailable: 'Unavailable',
};

export function statusChip(status) {
  const safe = LABELS[status] ? status : 'unavailable';
  const label = LABELS[safe];
  return `<span class="status-chip status-chip--${safe}">${label}</span>`;
}

export function statusChipElement(status) {
  const div = document.createElement('span');
  div.className = `status-chip status-chip--${LABELS[status] ? status : 'unavailable'}`;
  div.textContent = LABELS[status] ?? 'Unavailable';
  return div;
}
