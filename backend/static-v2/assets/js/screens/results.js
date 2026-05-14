/* Results screen — load job → parse ResultPackage → ranked clips + media stream */

import { resultsStore } from '../store/results.js';
import { statusChip } from '../components/status-chip.js';
import { aiBadge } from '../components/ai-badge.js';
import { emptyState, ICONS } from '../components/empty-state.js';
import { router } from '../router.js';

/* ── Sub-renders ──────────────────────────────────────────────────── */

function renderScoreFill(score) {
  const pct = Math.round(Math.min(100, Math.max(0, Number(score ?? 0))));
  const color = pct >= 70 ? 'var(--color-success)' : pct >= 40 ? 'var(--color-warning)' : 'var(--color-failed)';
  return `
    <div class="row gap-2" style="align-items:center">
      <div class="progress-bar" style="flex:1;height:3px">
        <div class="progress-bar__fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="text-caption" style="color:${color};min-width:28px;text-align:right;font-variant-numeric:tabular-nums">${pct}</span>
    </div>
  `;
}

function renderClipCard(clip, selected) {
  return `
    <div class="output-clip-card ${selected ? 'output-clip-card--selected' : ''}"
      data-part-no="${clip.partNo}" style="cursor:pointer">
      <div class="row gap-3" style="align-items:flex-start">
        <div class="clip-rank-badge ${clip.isBest ? 'clip-rank-badge--best' : ''}">
          ${clip.isBest ? '★' : `#${clip.rank}`}
        </div>
        <div class="col gap-1 flex-1" style="min-width:0">
          <div class="row gap-2" style="align-items:center">
            <span class="text-body" style="font-weight:600">Part ${clip.partNo}</span>
            ${clip.isBest ? `<span class="best-label">BEST</span>` : ''}
          </div>
          ${clip.score > 0 ? renderScoreFill(clip.score) : ''}
          ${clip.rankingReason
            ? `<div class="text-caption text-faint" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(clip.rankingReason)}</div>`
            : ''}
        </div>
        ${statusChip('completed')}
      </div>
    </div>
  `;
}

function renderHeroVideo(clip, jobId) {
  if (!clip) {
    return `<div class="results-hero results-hero--empty"><div class="text-caption text-faint">Select a clip to preview</div></div>`;
  }
  const url = `/api/jobs/${encodeURIComponent(jobId)}/parts/${clip.partNo}/stream`;
  return `
    <div class="results-hero">
      <video id="results-video" class="results-video"
        src="${url}" controls preload="metadata"
        style="width:100%;max-height:400px;object-fit:contain;border-radius:var(--radius-panel);background:#000">
      </video>
      <div id="results-video-err" style="display:none;padding:var(--sp-3) var(--sp-4);text-align:center">
        <div class="text-caption" style="color:var(--color-failed)">Preview unavailable — output file may be missing.</div>
        <a href="${url}" target="_blank" class="text-caption" style="color:var(--color-accent)">Try direct link ↗</a>
      </div>
      <div class="row gap-2 mt-2" style="padding:0 var(--sp-1)">
        <span class="text-caption text-faint">Part ${clip.partNo}</span>
        ${clip.isBest ? `<span class="best-label">BEST CLIP</span>` : ''}
        <span class="flex-1"></span>
        <a href="${url}" download="part_${clip.partNo}.mp4" class="btn btn-secondary btn-sm">Download</a>
      </div>
    </div>
  `;
}

function renderStatusRow(result) {
  const parts = [];
  if (result.voiceSummary !== 'not used') {
    const c = result.voiceSummary === 'applied' ? 'var(--color-success)' : 'var(--color-failed)';
    parts.push(`<span class="text-caption" style="color:${c}">Voice: ${_esc(result.voiceSummary)}</span>`);
  }
  if (result.subtitleTranslateSummary !== 'not used') {
    const c = result.subtitleTranslateSummary === 'applied' ? 'var(--color-success)'
      : result.subtitleTranslateSummary === 'partial' ? 'var(--color-warning)' : 'var(--color-failed)';
    parts.push(`<span class="text-caption" style="color:${c}">Translation: ${_esc(result.subtitleTranslateSummary)}</span>`);
  }
  return parts.length ? `<div class="row gap-4 results-status-row">${parts.join('')}</div>` : '';
}

function renderFailedPanel(result) {
  if (!result.failedPartNumbers.length) return '';
  return `
    <div class="card" style="border-color:var(--color-failed)">
      <div class="text-body" style="font-weight:600;color:var(--color-failed);margin-bottom:var(--sp-2)">
        ${result.failedCount} part${result.failedCount !== 1 ? 's' : ''} failed
      </div>
      ${result.failedPartDetails.slice(0, 5).map(d => `
        <div class="row gap-2 mt-2">
          <span class="text-caption text-faint">Part ${d.part_no ?? '?'}</span>
          <span class="text-caption">${_esc(d.message ?? d.error ?? 'Failed')}</span>
        </div>
      `).join('')}
      ${result.rankingWarning
        ? `<div class="text-caption" style="color:var(--color-warning);margin-top:var(--sp-2)">${_esc(result.rankingWarning)}</div>`
        : ''}
    </div>
  `;
}

function renderAISection(result) {
  const ai = result.ai;
  if (!ai || (!ai.available && !ai.directorEnabled)) return '';
  return `
    <div class="card card--raised">
      <div class="row gap-3" style="align-items:center;margin-bottom:var(--sp-3)">
        <span style="color:var(--color-ai);font-size:16px">◈</span>
        <span class="text-section">AI Insights</span>
        ${aiBadge(ai.available ? 'advisory' : 'disabled')}
      </div>
      <div class="text-body" style="color:var(--color-text-muted)">
        AI insights available after Phase 63 integration.
      </div>
      ${ai.summaryLines.length > 0 ? `
        <div class="col gap-1 mt-3">
          ${ai.summaryLines.map(l => `<div class="text-caption text-faint">• ${_esc(l)}</div>`).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

/* ── Right panel (shell panel) ────────────────────────────────────── */

function updateRightPanel(state) {
  const panelEl = document.querySelector('#panel-content');
  if (!panelEl) return;
  const clip = resultsStore.getSelectedClip();
  if (!clip || !state.result) {
    panelEl.innerHTML = '<div class="text-caption text-faint">Select a clip to see details.</div>';
    return;
  }
  const components = clip.rankingComponents ?? {};
  panelEl.innerHTML = `
    <div class="col gap-3">
      <div class="text-section">Part ${clip.partNo}</div>
      ${clip.isBest ? `<span class="best-label" style="width:fit-content">BEST CLIP</span>` : ''}
      ${clip.score > 0 ? renderScoreFill(clip.score) : ''}
      ${clip.rankingReason ? `<div class="text-caption" style="color:var(--color-text-muted)">${_esc(clip.rankingReason)}</div>` : ''}
      ${clip.reasons?.length ? `
        <div class="col gap-1 mt-2">
          ${clip.reasons.map(r => `<div class="text-caption text-faint">• ${_esc(r)}</div>`).join('')}
        </div>
      ` : ''}
      ${Object.keys(components).length ? `
        <div class="col gap-2 mt-3">
          <div class="text-caption" style="font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--color-text-faint)">Score breakdown</div>
          ${Object.entries(components).map(([k, v]) => `
            <div class="row gap-2" style="align-items:center">
              <span class="text-caption text-faint" style="min-width:110px">${k.replace(/_/g,' ')}</span>
              ${renderScoreFill(Number(v) * 100)}
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

/* ── Full body render ─────────────────────────────────────────────── */

function renderBody(state) {
  const { result, selectedClipIndex, job } = state;
  const selectedClip = resultsStore.getSelectedClip();
  const jobId = state.jobId;

  return `
    <div id="results-hero-wrap">
      ${renderHeroVideo(selectedClip, jobId)}
    </div>

    <div class="row gap-4 results-status-row" style="align-items:center;flex-wrap:wrap">
      ${statusChip(result.isPartialSuccess ? 'partial' : 'completed')}
      <span class="text-body">${result.successfulCount} clip${result.successfulCount !== 1 ? 's' : ''}</span>
      ${result.isPartialSuccess ? `<span class="text-caption" style="color:var(--color-warning)">${result.failedCount} failed</span>` : ''}
      ${renderStatusRow(result)}
    </div>

    <div>
      <div class="text-section" style="margin-bottom:var(--sp-3)">Ranked outputs</div>
      <div id="results-clip-list" class="col gap-2">
        ${result.ranking.map((c, i) => renderClipCard(c, i === selectedClipIndex)).join('')}
      </div>
    </div>

    ${renderFailedPanel(result)}
    ${renderAISection(result)}
  `;
}

/* ── Mount ────────────────────────────────────────────────────────── */

export async function mount(el, params) {
  const jobId = params[0];

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Results</div>
          <div class="screen__subtitle">${jobId ? `Job ${jobId.slice(0, 12)}…` : 'Completed render'}</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-ghost" id="res-monitor-btn">← Monitor</button>
        <button class="btn btn-secondary" id="res-new-btn">New render</button>
      </div>
    </div>
    <div class="screen__body col gap-5" id="results-body">
      <div class="skeleton-block" style="height:220px;border-radius:var(--radius-panel)"></div>
      <div class="skeleton-line" style="height:18px;width:45%"></div>
      <div class="skeleton-line" style="height:18px;width:70%"></div>
    </div>
  `;

  el.querySelector('#res-monitor-btn')?.addEventListener('click', () =>
    router.go(jobId ? `/monitor/${jobId}` : '/source')
  );
  el.querySelector('#res-new-btn')?.addEventListener('click', () => router.go('/source'));

  if (!jobId) {
    const body = el.querySelector('#results-body');
    if (body) {
      body.innerHTML = '';
      body.appendChild(emptyState({
        icon: ICONS.empty,
        title: 'No job selected',
        body: 'Navigate here from Monitor after a render completes.',
      }));
    }
    return;
  }

  const unsub = resultsStore.subscribe(state => {
    const body = el.querySelector('#results-body');
    if (!body) return;

    if (state.loading) {
      body.innerHTML = `
        <div class="skeleton-block" style="height:220px;border-radius:var(--radius-panel)"></div>
        <div class="skeleton-line" style="height:18px;width:45%"></div>
        <div class="skeleton-line" style="height:18px;width:70%"></div>
      `;
      return;
    }

    if (state.error) {
      body.innerHTML = `
        <div class="card" style="border-color:var(--color-failed)">
          <div class="text-body" style="color:var(--color-failed)">Failed to load results</div>
          <div class="text-caption text-faint mt-2">${_esc(state.error)}</div>
        </div>
      `;
      return;
    }

    if (!state.result || !state.result.rawAvailable) {
      body.innerHTML = `
        <div class="card">
          <div class="text-body">Results not yet available</div>
          <div class="text-caption text-faint mt-2">${_esc(state.result?.parseError ?? 'The job may still be running or has no result data.')}</div>
          <button class="btn btn-secondary mt-4" id="res-back-to-monitor">← Back to Monitor</button>
        </div>
      `;
      el.querySelector('#res-back-to-monitor')?.addEventListener('click', () => router.go(`/monitor/${jobId}`));
      return;
    }

    body.innerHTML = renderBody(state);

    // Wire video error
    const vid = body.querySelector('#results-video');
    const vidErr = body.querySelector('#results-video-err');
    if (vid && vidErr) {
      vid.addEventListener('error', () => { vid.style.display = 'none'; vidErr.style.display = ''; });
    }

    // Wire clip selection
    body.querySelector('#results-clip-list')?.addEventListener('click', e => {
      const card = e.target.closest('[data-part-no]');
      if (!card) return;
      const partNo = Number(card.dataset.partNo);
      const idx = state.result.ranking.findIndex(c => c.partNo === partNo);
      if (idx >= 0) resultsStore.selectClip(idx);
    });

    updateRightPanel(state);
  });

  await resultsStore.load(jobId);

  el.addEventListener('unmount', () => { unsub(); });
}

export const resultsScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
