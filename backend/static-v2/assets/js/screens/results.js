/* Results screen — load job → parse ResultPackage → ranked clips + stable hero video.
   Video element is NEVER destroyed on clip selection: only src + meta strip update.
   Media URLs are always /api/jobs/{jobId}/parts/{partNo}/stream — never raw file paths.
*/

import { resultsStore } from '../store/results.js';
import { statusChip } from '../components/status-chip.js';
import { aiBadge } from '../components/ai-badge.js';
import { emptyState, ICONS } from '../components/empty-state.js';
import { scoreBadge, scorePill, scoreColor } from '../components/score-badge.js';
import { outputCard } from '../components/output-card.js';
import { bestClipHero, heroMetaHtml, wireHeroVideo, updateHeroClip } from '../components/best-clip-hero.js';
import { router } from '../router.js';

/* ── Right panel (shell panel) ────────────────────────────────────────── */

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
      ${clip.score > 0 ? scoreBadge(clip.score) : ''}
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
              <span class="text-caption text-faint" style="min-width:110px;flex-shrink:0">${k.replace(/_/g, ' ')}</span>
              ${scoreBadge(Number(v) * 100)}
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

/* ── Status bar ───────────────────────────────────────────────────────── */

function renderStatusBar(result) {
  const parts = [];

  if (result.isPartialSuccess) {
    parts.push(`
      <div class="partial-banner row gap-3" style="align-items:center">
        <span class="text-caption" style="color:var(--color-partial);font-weight:600">⚠ Partial success</span>
        <span class="text-caption text-faint">${result.successfulCount} clip${result.successfulCount !== 1 ? 's' : ''} ready · ${result.failedCount} failed</span>
      </div>
    `);
  } else {
    const chips = [statusChip('completed')];
    chips.push(`<span class="text-body">${result.successfulCount} clip${result.successfulCount !== 1 ? 's' : ''}</span>`);
    if (result.voiceSummary !== 'not used') {
      const c = result.voiceSummary === 'applied' ? 'var(--color-success)' : 'var(--color-failed)';
      chips.push(`<span class="text-caption" style="color:${c}">Voice: ${_esc(result.voiceSummary)}</span>`);
    }
    if (result.subtitleTranslateSummary !== 'not used') {
      const c = result.subtitleTranslateSummary === 'applied' ? 'var(--color-success)'
        : result.subtitleTranslateSummary === 'partial' ? 'var(--color-warning)' : 'var(--color-failed)';
      chips.push(`<span class="text-caption" style="color:${c}">Translation: ${_esc(result.subtitleTranslateSummary)}</span>`);
    }
    parts.push(`<div class="row gap-3" style="align-items:center;flex-wrap:wrap">${chips.join('')}</div>`);
  }

  return parts.join('');
}

/* ── Failed parts panel ───────────────────────────────────────────────── */

function renderFailedPanel(result) {
  if (!result.failedPartNumbers.length) return '';
  return `
    <div class="failed-panel">
      <div class="text-body" style="font-weight:600;color:var(--color-failed);margin-bottom:var(--sp-2)">
        ${result.failedCount} part${result.failedCount !== 1 ? 's' : ''} failed
      </div>
      ${result.failedPartDetails.slice(0, 6).map(d => `
        <div class="failed-row">
          <span class="text-caption text-faint" style="min-width:48px;flex-shrink:0">Part ${d.part_no ?? '?'}</span>
          <span class="text-caption" style="color:var(--color-text-muted)">${_esc(d.message ?? d.error ?? 'Failed')}</span>
        </div>
      `).join('')}
      ${result.rankingWarning
        ? `<div class="text-caption mt-2" style="color:var(--color-warning)">${_esc(result.rankingWarning)}</div>`
        : ''}
    </div>
  `;
}

/* ── AI panel ─────────────────────────────────────────────────────────── */

function renderAIPanel(result) {
  const ai = result.ai;
  const isAdvisory = ai?.available || ai?.directorEnabled;
  const hasMetics  = ai?.previewChips?.length > 0;

  return `
    <div class="ai-panel ${isAdvisory ? 'ai-panel--advisory' : ''}">
      <div class="ai-panel__header">
        <span style="color:var(--color-ai);font-size:15px">◈</span>
        <span class="text-section">AI Insights</span>
        <span class="flex-1"></span>
        ${aiBadge(isAdvisory ? 'advisory' : 'disabled')}
      </div>

      ${isAdvisory && hasMetics ? `
        <div class="ai-panel__chips">
          ${ai.previewChips.map(chip => `
            <span class="ai-chip ${chip.type === 'applied' ? 'ai-chip--applied' : chip.type === 'quality' ? 'ai-chip--advisory' : ''}">
              ${_esc(chip.label)}
            </span>
          `).join('')}
        </div>
      ` : ''}

      ${isAdvisory && ai.summaryLines.length > 0 ? `
        <div class="col gap-1 mt-3">
          ${ai.summaryLines.slice(0, 3).map(l => `
            <div class="text-caption text-faint">• ${_esc(l)}</div>
          `).join('')}
        </div>
      ` : ''}

      ${!isAdvisory ? `
        <div class="text-body mt-2" style="color:var(--color-text-faint)">
          AI Copilot summaries will appear here when connected.
        </div>
      ` : ''}

      ${ai?.warnings?.length > 0 ? `
        <div class="col gap-1 mt-2">
          ${ai.warnings.map(w => `
            <div class="ai-chip ai-chip--warning" style="display:inline-flex">⚠ ${_esc(w)}</div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

/* ── Full body render (called once per result load) ───────────────────── */

function renderBody(state) {
  const { result, selectedClipIndex, jobId } = state;
  const clip = resultsStore.getSelectedClip();

  return `
    <div class="results-body-col">
      <div id="results-hero-wrap" class="hero-section">
        ${bestClipHero(clip, jobId)}
      </div>

      <div id="results-status-bar">
        ${renderStatusBar(result)}
      </div>

      <div>
        <div class="text-section" style="margin-bottom:var(--sp-3)">
          Ranked outputs
          <span class="text-caption text-faint" style="margin-left:var(--sp-2);font-weight:400">${result.ranking.length}</span>
        </div>
        <div id="results-clip-list" class="col gap-2">
          ${result.ranking.map((c, i) =>
            outputCard(c, { selected: i === selectedClipIndex })
          ).join('')}
        </div>
      </div>

      <div id="results-failed-panel">${renderFailedPanel(result)}</div>
      <div id="results-ai-panel">${renderAIPanel(result)}</div>
    </div>
  `;
}

/* ── Surgical selection update (no video element recreation) ──────────── */

function _updateSelection(bodyEl, state) {
  const clip  = resultsStore.getSelectedClip();
  const jobId = state.jobId;

  // Update video src + meta strip without touching the <video> element structure
  const heroWrap = bodyEl.querySelector('#results-hero-wrap');
  if (heroWrap && clip) {
    updateHeroClip(heroWrap, clip, jobId);
  }

  // Toggle selected class on clip cards (no innerHTML change)
  bodyEl.querySelectorAll('.output-clip-card').forEach(card => {
    const isSelected = Number(card.dataset.partNo) === clip?.partNo;
    card.classList.toggle('output-clip-card--selected', isSelected);
  });
}

/* ── Mount ────────────────────────────────────────────────────────────── */

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

  // Track previous result reference to distinguish "new result" vs "selection change"
  let _prevResult = null;

  const unsub = resultsStore.subscribe(state => {
    const body = el.querySelector('#results-body');
    if (!body) return;

    if (state.loading) {
      _prevResult = null;
      body.innerHTML = `
        <div class="skeleton-block" style="height:220px;border-radius:var(--radius-panel)"></div>
        <div class="skeleton-line" style="height:18px;width:45%"></div>
        <div class="skeleton-line" style="height:18px;width:70%"></div>
      `;
      return;
    }

    if (state.error) {
      _prevResult = null;
      body.innerHTML = `
        <div class="card" style="border-color:var(--color-failed)">
          <div class="text-body" style="color:var(--color-failed)">Failed to load results</div>
          <div class="text-caption text-faint mt-2">${_esc(state.error)}</div>
        </div>
      `;
      return;
    }

    if (!state.result?.rawAvailable) {
      _prevResult = null;
      body.innerHTML = `
        <div class="card">
          <div class="text-body">Results not yet available</div>
          <div class="text-caption text-faint mt-2">${_esc(state.result?.parseError ?? 'The job may still be running or has no result data.')}</div>
          <button class="btn btn-secondary mt-4" id="res-back-to-monitor">← Back to Monitor</button>
        </div>
      `;
      body.querySelector('#res-back-to-monitor')?.addEventListener('click', () =>
        router.go(`/monitor/${jobId}`)
      );
      return;
    }

    // Full re-render when result changes (new load)
    if (state.result !== _prevResult) {
      _prevResult = state.result;
      body.innerHTML = renderBody(state);
      _wireBody(body, state);
    } else {
      // Selection changed only — surgical update preserving video element
      _updateSelection(body, state);
    }

    updateRightPanel(state);
  });

  await resultsStore.load(jobId);

  el.addEventListener('unmount', () => { unsub(); });
}

function _wireBody(bodyEl, state) {
  // Wire video error handler on the hero
  const heroWrap = bodyEl.querySelector('#results-hero-wrap');
  if (heroWrap) wireHeroVideo(heroWrap);

  // Wire clip selection
  bodyEl.querySelector('#results-clip-list')?.addEventListener('click', e => {
    const card = e.target.closest('[data-part-no]');
    if (!card) return;
    const partNo = Number(card.dataset.partNo);
    const idx = state.result.ranking.findIndex(c => c.partNo === partNo);
    if (idx >= 0) resultsStore.selectClip(idx);
  });
}

export const resultsScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
