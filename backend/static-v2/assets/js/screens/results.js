/* Results screen — completed job result package with per-part breakdown. */

import { resultsStore } from '../store/results.js';
import { statusChip } from '../components/status-chip.js';
import { aiBadge } from '../components/ai-badge.js';
import { emptyState, ICONS } from '../components/empty-state.js';
import { router } from '../router.js';

function renderSummary(result) {
  const s = result.summary;
  return `
    <div class="row gap-3" style="align-items:center;flex-wrap:wrap;margin-bottom:var(--sp-4)">
      <div class="text-section">Job ${result.jobId.slice(0, 12)}…</div>
      ${statusChip(result.status)}
    </div>
    <div class="metric-grid">
      <div class="metric-tile">
        <div class="metric-tile__value">${result.partsTotal}</div>
        <div class="metric-tile__label">Total parts</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile__value" style="color:var(--color-success)">${result.partsOk}</div>
        <div class="metric-tile__label">Completed</div>
      </div>
      <div class="metric-tile">
        <div class="metric-tile__value" style="color:var(--color-failed)">${result.partsFailed}</div>
        <div class="metric-tile__label">Failed</div>
      </div>
      ${s.aiAppliedCount > 0 ? `
      <div class="metric-tile">
        <div class="metric-tile__value" style="color:var(--color-ai)">${s.aiAppliedCount}</div>
        <div class="metric-tile__label">AI applied</div>
      </div>` : ''}
      ${s.avgQualityScore != null ? `
      <div class="metric-tile">
        <div class="metric-tile__value">${(s.avgQualityScore * 100).toFixed(0)}%</div>
        <div class="metric-tile__label">Avg quality</div>
      </div>` : ''}
    </div>
  `;
}

function renderPartList(parts, selectedIndex) {
  if (!parts.length) return '<div class="text-caption text-faint">No parts in result.</div>';
  return `
    <div class="card" style="padding:0;overflow:hidden">
      ${parts.map((p, i) => `
        <div class="part-item result-part-item ${selectedIndex === i ? 'part-item--selected' : ''}" data-index="${i}">
          <div class="part-item__index">${p.index}</div>
          <div class="part-item__title">${p.title}</div>
          <div class="row gap-2">
            ${statusChip(p.status)}
            ${aiBadge(p.aiState)}
          </div>
          ${p.outputFile ? `<div class="text-caption" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px">${p.outputFile.split(/[\\/]/).pop()}</div>` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function renderPartDetail(part) {
  if (!part) return '<div class="text-caption text-faint">Select a part to see details.</div>';
  return `
    <div class="col gap-3">
      <div class="text-section">${part.title}</div>
      ${statusChip(part.status)}
      ${part.outputFile ? `<div class="text-caption" style="word-break:break-all">${part.outputFile}</div>` : ''}
      ${part.durationMs != null ? `<div class="text-caption">Duration: ${(part.durationMs / 1000).toFixed(2)}s</div>` : ''}
    </div>
  `;
}

async function mount(el, params) {
  const jobId = params[0];

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Results</div>
          <div class="screen__subtitle">Completed render output</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-ghost" id="results-back-btn">← Monitor</button>
        <button class="btn btn-secondary" id="results-new-btn">New render</button>
      </div>
    </div>
    <div class="screen__body col gap-4" id="results-body">
      <div id="results-loading" class="text-caption text-faint">Loading results…</div>
    </div>
  `;

  el.querySelector('#results-back-btn')?.addEventListener('click', () => router.go(`/monitor/${jobId}`));
  el.querySelector('#results-new-btn')?.addEventListener('click',  () => router.go('/source'));

  if (!jobId) {
    const body = el.querySelector('#results-body');
    body.innerHTML = '';
    body.appendChild(emptyState({ icon: ICONS.empty, title: 'No job ID', body: 'Navigate from the Monitor screen.' }));
    return;
  }

  const unsub = resultsStore.subscribe(state => {
    const body = el.querySelector('#results-body');
    if (!body) return;

    if (state.loading) {
      body.innerHTML = '<div class="text-caption text-faint">Loading results…</div>';
      return;
    }
    if (state.error) {
      body.innerHTML = `<div class="text-caption" style="color:var(--color-failed)">${state.error}</div>`;
      return;
    }
    if (!state.result) return;

    body.innerHTML = `
      <div>${renderSummary(state.result)}</div>
      <div>
        <div class="text-section" style="margin-bottom:var(--sp-3)">Parts</div>
        <div id="results-part-list">${renderPartList(state.result.parts, state.selectedPartIndex)}</div>
      </div>
    `;

    body.querySelector('#results-part-list')?.addEventListener('click', e => {
      const item = e.target.closest('.result-part-item');
      if (item) {
        const idx = Number(item.dataset.index);
        resultsStore.selectPart(idx);
      }
    });

    const panelContent = document.querySelector('#panel-content');
    if (panelContent) {
      panelContent.innerHTML = renderPartDetail(resultsStore.getSelectedPart());
    }
  });

  await resultsStore.load(jobId);

  el.addEventListener('unmount', () => { unsub(); });
}

export const resultsScreen = { mount };
