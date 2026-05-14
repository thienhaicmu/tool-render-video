/* partStatusList(parts) — renders a styled part progress table.
   Returns HTML string. No side effects.
*/

import { statusChip } from './status-chip.js';

export function partStatusList(parts) {
  if (!Array.isArray(parts) || !parts.length) {
    return `<div class="text-caption text-faint" style="padding:var(--sp-4) 0">Waiting for parts to start…</div>`;
  }
  return `<div class="part-status-table">${parts.map(p => _partRow(p)).join('')}</div>`;
}

function _partRow(part) {
  const pct      = Math.min(100, part.progressPercent ?? 0);
  const isActive = part.chipStatus === 'running';
  const rowCls   = `part-row--${part.chipStatus ?? 'queued'}`;
  return `
    <div class="part-progress-row ${rowCls}">
      <div class="part-progress-row__no text-caption">${part.partNo}</div>
      <div class="col gap-1 flex-1" style="min-width:0">
        <div class="row gap-2" style="align-items:center">
          <span class="part-item__title">${_esc(part.partName || `Part ${part.partNo}`)}</span>
          ${statusChip(part.chipStatus)}
          ${isActive && pct > 0
            ? `<span class="text-caption text-faint" style="margin-left:auto;flex-shrink:0;font-variant-numeric:tabular-nums">${pct}%</span>`
            : ''}
        </div>
        ${isActive || pct > 0 ? `
          <div class="progress-bar ${isActive ? 'progress-bar--running' : ''}" style="height:2px">
            <div class="progress-bar__fill" style="width:${pct}%"></div>
          </div>
        ` : ''}
        ${part.message ? `<div class="text-caption text-faint part-message">${_esc(part.message)}</div>` : ''}
      </div>
    </div>
  `;
}

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
