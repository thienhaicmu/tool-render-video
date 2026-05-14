/* outputCard(clip, opts) — ranked output card for the results clip list.
   Imports score-badge for the inline score bar and pill.
   Never throws on null/incomplete clip.
*/

import { scoreBadge, scorePill } from './score-badge.js';

export function outputCard(clip, { selected = false } = {}) {
  if (!clip) return '';
  const rawDur = clip._raw?.duration ?? clip._raw?.end_sec != null
    ? (clip._raw.end_sec - (clip._raw.start_sec ?? 0))
    : 0;
  const dur = rawDur > 0 ? _fmtDur(rawDur) : null;

  return `
    <div class="output-clip-card ${selected ? 'output-clip-card--selected' : ''}"
         data-part-no="${clip.partNo}" style="cursor:pointer">
      <div class="row gap-3" style="align-items:flex-start">
        <div class="clip-rank-badge ${clip.isBest ? 'clip-rank-badge--best' : ''}">
          ${clip.isBest ? '★' : `#${clip.rank || '?'}`}
        </div>
        <div class="col gap-1 flex-1" style="min-width:0">
          <div class="row gap-2" style="align-items:center;flex-wrap:wrap">
            <span class="text-body" style="font-weight:600">Part ${clip.partNo}</span>
            ${clip.isBest ? `<span class="best-label">BEST</span>` : ''}
            ${dur ? `<span class="dur-badge">${dur}</span>` : ''}
            <span class="flex-1"></span>
            ${clip.score > 0 ? scorePill(clip.score, { sm: true }) : ''}
          </div>
          ${clip.score > 0 ? scoreBadge(clip.score) : ''}
          ${clip.rankingReason
            ? `<div class="text-caption text-faint clip-reason">${_esc(clip.rankingReason)}</div>`
            : ''}
        </div>
      </div>
    </div>
  `;
}

function _fmtDur(sec) {
  const m = Math.floor(sec / 60);
  const s = String(Math.floor(sec % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
