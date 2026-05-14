/* Results screen — load job → parse ResultPackage → ranked clips + stable hero video.
   Video element is NEVER destroyed on clip selection: only src + meta strip update.
   Media URLs are always /api/jobs/{jobId}/parts/{partNo}/stream — never raw file paths.
   Layout order: hero → status banner → AI panel (if data) → clip list → failed clips.
*/

import { resultsStore } from '../store/results.js';
import { aiBadge } from '../components/ai-badge.js';
import { emptyState, ICONS } from '../components/empty-state.js';
import { scoreBadge, scoreColor } from '../components/score-badge.js';
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
  const url = state.jobId
    ? `/api/jobs/${encodeURIComponent(state.jobId)}/parts/${clip.partNo}/stream`
    : null;
  const components = clip.rankingComponents ?? {};
  panelEl.innerHTML = `
    <div class="col gap-3">
      <div class="text-section">Clip ${clip.partNo}</div>
      ${clip.isBest ? `<span class="best-label" style="width:fit-content">BEST CLIP</span>` : ''}
      ${clip.score > 0 ? scoreBadge(clip.score) : ''}
      ${url ? `<a href="${url}" download="clip_${clip.partNo}.mp4" class="btn btn-secondary btn-sm" style="align-self:flex-start">↓ Download clip</a>` : ''}
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

/* ── Status banner ────────────────────────────────────────────────────── */

function renderStatusBar(result) {
  if (result.isPartialSuccess) {
    return `
      <div class="partial-banner row gap-3" style="align-items:center">
        <span aria-hidden="true" style="color:var(--color-partial);font-size:15px">⚠</span>
        <div class="col gap-1">
          <span class="text-body" style="font-weight:600;color:var(--color-partial)">${result.successfulCount} clip${result.successfulCount !== 1 ? 's' : ''} ready</span>
          <span class="text-caption text-faint">${result.failedCount} clip${result.failedCount !== 1 ? 's' : ''} couldn't be processed</span>
        </div>
        ${result.rankingWarning ? `<span class="flex-1"></span><span class="text-caption" style="color:var(--color-warning)">${_esc(result.rankingWarning)}</span>` : '<span class="flex-1"></span>'}
      </div>
    `;
  }

  const extras = [];
  if (result.voiceSummary !== 'not used') {
    const c = result.voiceSummary === 'applied' ? 'var(--color-success)' : 'var(--color-failed)';
    extras.push(`<span class="text-caption" style="color:${c}">Voice ${_esc(result.voiceSummary)}</span>`);
  }
  if (result.subtitleTranslateSummary !== 'not used') {
    const c = result.subtitleTranslateSummary === 'applied' ? 'var(--color-success)'
      : result.subtitleTranslateSummary === 'partial' ? 'var(--color-warning)' : 'var(--color-failed)';
    extras.push(`<span class="text-caption" style="color:${c}">Subtitles ${_esc(result.subtitleTranslateSummary)}</span>`);
  }

  return `
    <div class="results-complete-banner">
      <span class="results-ready-icon" aria-hidden="true">✓</span>
      <div class="col gap-1">
        <span class="text-body" style="font-weight:600">${result.successfulCount} clip${result.successfulCount !== 1 ? 's' : ''} ready</span>
        ${extras.length ? `<div class="row gap-2">${extras.join('<span class="text-faint" style="opacity:0.4">·</span>')}</div>` : ''}
      </div>
      <span class="flex-1"></span>
      <span class="text-caption text-faint">Ranked by AI</span>
    </div>
  `;
}

/* ── Failed clips panel ───────────────────────────────────────────────── */

function renderFailedPanel(result, jobId) {
  if (!result.failedPartNumbers.length) return '';
  return `
    <div class="failed-panel">
      <div class="row gap-2" style="align-items:center;margin-bottom:var(--sp-2)">
        <div class="text-body" style="font-weight:600;color:var(--color-failed)">
          ${result.failedCount} clip${result.failedCount !== 1 ? 's' : ''} couldn't be processed
        </div>
        ${jobId ? `<span class="flex-1"></span><a class="btn btn-ghost btn-sm" href="#/monitor/${jobId}">View logs →</a>` : ''}
      </div>
      ${result.failedPartDetails.slice(0, 6).map(d => `
        <div class="failed-row">
          <span class="text-caption text-faint" style="min-width:48px;flex-shrink:0">Clip ${d.part_no ?? '?'}</span>
          <span class="text-caption" style="color:var(--color-text-muted)">${_esc(d.message ?? d.error ?? 'Failed')}</span>
        </div>
      `).join('')}
      ${result.rankingWarning
        ? `<div class="text-caption mt-2" style="color:var(--color-warning)">${_esc(result.rankingWarning)}</div>`
        : ''}
    </div>
  `;
}

/* ── AI panel — only renders when intelligence data is present ────────── */

function renderAIPanel(result) {
  const ai    = result.ai;
  const isActive = !!(ai?.available || ai?.directorEnabled);
  const intel = ai?.intelligence;

  if (!isActive || !intel?.hasData) return '';

  const { appliedItems, creatorType, platform, platformFit, confidenceLabel,
          strategyNotes, qualityScores, creatorFit, learningItems, suggestions,
          modeLabel, assistanceLabel } = intel;

  return `
    <div class="ai-intel-panel ai-intel-panel--active">
      <div class="ai-intel-header">
        <span class="ai-intel-icon" aria-hidden="true">◈</span>
        <span class="text-section">AI Intelligence</span>
        <span class="flex-1"></span>
        ${aiBadge('advisory')}
      </div>

      ${appliedItems.length > 0 ? `
        <div class="ai-intel-section">
          <div class="ai-intel-section__title">What AI improved</div>
          <div class="col gap-2">
            ${appliedItems.map(item => `
              <div class="ai-applied-item">
                <span class="ai-applied-item__check" aria-hidden="true">✓</span>
                <span class="text-caption">${_esc(item.label)}${item.detail ? ` — <span class="text-faint">${_esc(item.detail)}</span>` : ''}</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${creatorType || platform || confidenceLabel ? `
        <div class="ai-intel-section">
          <div class="ai-intel-section__title">Creator &amp; Platform</div>
          <div class="ai-strat-rows">
            ${creatorType ? `<div class="ai-strat-row"><span class="ai-strat-row__key">Type</span><span class="ai-strat-row__val">${_esc(creatorType)}</span></div>` : ''}
            ${platform    ? `<div class="ai-strat-row"><span class="ai-strat-row__key">Platform</span><span class="ai-strat-row__val">${_esc(platform)}</span></div>` : ''}
            ${creatorFit  ? `<div class="ai-strat-row"><span class="ai-strat-row__key">Creator fit</span><span class="ai-strat-row__val ai-strat-row__val--${creatorFit.toLowerCase()}">${_esc(creatorFit)}</span></div>` : ''}
            ${platformFit != null ? `<div class="ai-strat-row"><span class="ai-strat-row__key">Platform fit</span><span class="ai-strat-row__val">${platformFit}%</span></div>` : ''}
            ${confidenceLabel ? `<div class="ai-strat-row"><span class="ai-strat-row__key">Confidence</span><span class="ai-conf-pill ai-conf-pill--${confidenceLabel.toLowerCase()}">${_esc(confidenceLabel)}</span></div>` : ''}
          </div>
          ${strategyNotes.length > 0 ? `
            <div class="col gap-1 mt-3">
              ${strategyNotes.map(n => `<div class="text-caption text-faint">• ${_esc(n)}</div>`).join('')}
            </div>
          ` : ''}
        </div>
      ` : ''}

      ${qualityScores ? `
        <div class="ai-intel-section">
          <div class="ai-intel-section__title">Quality</div>
          <div class="ai-quality-grid">
            <div class="ai-quality-tile">
              <span class="ai-quality-score" style="color:${scoreColor(qualityScores.overall)}">${qualityScores.overall}</span>
              <span class="text-caption text-faint">Overall</span>
            </div>
            ${qualityScores.subtitle != null ? `<div class="ai-quality-tile"><span class="ai-quality-score" style="color:${scoreColor(qualityScores.subtitle)}">${qualityScores.subtitle}</span><span class="text-caption text-faint">Subtitle</span></div>` : ''}
            ${qualityScores.camera   != null ? `<div class="ai-quality-tile"><span class="ai-quality-score" style="color:${scoreColor(qualityScores.camera)}">${qualityScores.camera}</span><span class="text-caption text-faint">Camera</span></div>` : ''}
            ${qualityScores.hook     != null ? `<div class="ai-quality-tile"><span class="ai-quality-score" style="color:${scoreColor(qualityScores.hook)}">${qualityScores.hook}</span><span class="text-caption text-faint">Hook</span></div>` : ''}
          </div>
        </div>
      ` : ''}

      ${learningItems.length > 0 ? `
        <div class="ai-intel-section">
          <div class="ai-intel-section__title">AI learned</div>
          <div class="col gap-2">
            ${learningItems.map(item => `
              <div class="ai-learning-item">
                <span class="ai-learning-item__check" aria-hidden="true">✓</span>
                <span class="text-caption text-faint">${_esc(item)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${suggestions.length > 0 ? `
        <div class="ai-intel-section">
          <div class="ai-intel-section__title">Suggestions</div>
          <div class="ai-suggest-list">
            ${suggestions.map(s => `
              <div class="ai-suggest-card">
                <span class="text-caption">${_esc(s)}</span>
                <span class="ai-suggest-label">Manual review</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${modeLabel || assistanceLabel ? `
        <div class="ai-exec-footer">
          ${modeLabel      ? `<span class="text-caption text-faint">Mode: ${_esc(modeLabel)}</span>` : ''}
          ${modeLabel && assistanceLabel ? `<span class="text-caption text-faint">·</span>` : ''}
          ${assistanceLabel ? `<span class="text-caption text-faint">${_esc(assistanceLabel)}</span>` : ''}
        </div>
      ` : ''}

      ${ai.warnings?.length > 0 ? `
        <div class="col gap-1 mt-2">
          ${ai.warnings.map(w => `<div class="ai-chip ai-chip--warning" style="display:inline-flex">⚠ ${_esc(w)}</div>`).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

/* ── Full body render (called once per result load) ───────────────────── */

function renderBody(state) {
  const { result, selectedClipIndex, jobId } = state;
  const clip   = resultsStore.getSelectedClip();
  const aiHtml = renderAIPanel(result);

  return `
    <div class="results-body-col">
      <div id="results-hero-wrap" class="hero-section">
        ${bestClipHero(clip, jobId)}
      </div>

      <div id="results-status-bar">
        ${renderStatusBar(result)}
      </div>

      ${aiHtml ? `<div id="results-ai-panel">${aiHtml}</div>` : ''}

      <div>
        <div class="row gap-2" style="align-items:baseline;margin-bottom:var(--sp-3)">
          <span class="text-section">Your clips</span>
          <span class="text-caption text-faint" style="font-weight:400">${result.ranking.length}</span>
        </div>
        <div id="results-clip-list" class="col gap-2">
          ${result.ranking.map((c, i) =>
            outputCard(c, { selected: i === selectedClipIndex })
          ).join('')}
        </div>
      </div>

      <div id="results-failed-panel">${renderFailedPanel(result, jobId)}</div>
    </div>
  `;
}

/* ── Surgical selection update (no video element recreation) ──────────── */

function _updateSelection(bodyEl, state) {
  const clip  = resultsStore.getSelectedClip();
  const jobId = state.jobId;

  const heroWrap = bodyEl.querySelector('#results-hero-wrap');
  if (heroWrap && clip) {
    updateHeroClip(heroWrap, clip, jobId);
  }

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
          <div class="screen__subtitle" id="results-subtitle">${jobId ? 'Loading…' : 'Completed render'}</div>
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
        icon: ICONS.video,
        title: 'No results to show',
        body: 'Start a render from Studio to see your clips here.',
        ctaLabel: '← Back to Studio',
        onCta: () => router.go('/studio'),
      }));
    }
    return;
  }

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
      body.innerHTML = '';
      const errNode = document.createElement('div');
      errNode.className = 'results-error-card col gap-3';
      errNode.innerHTML = `
        <div class="text-body" style="font-weight:600;color:var(--color-failed)">Couldn't load results</div>
        <div class="text-caption text-faint">${_esc(state.error)}</div>
        <div class="row gap-2">
          <button class="btn btn-secondary btn-sm" id="res-err-retry">Try again</button>
          <button class="btn btn-ghost btn-sm" id="res-err-library">Open Library</button>
        </div>
      `;
      errNode.querySelector('#res-err-retry')?.addEventListener('click', () => resultsStore.load(jobId));
      errNode.querySelector('#res-err-library')?.addEventListener('click', () => router.go('/library'));
      body.appendChild(errNode);
      return;
    }

    if (!state.result?.rawAvailable) {
      _prevResult = null;
      body.innerHTML = '';
      const notAvailNode = document.createElement('div');
      notAvailNode.className = 'card col gap-3';
      notAvailNode.innerHTML = `
        <div class="text-body" style="font-weight:600">Results not ready yet</div>
        <div class="text-caption text-faint">${_esc(state.result?.parseError ?? 'The render may still be running.')}</div>
        <div class="row gap-2">
          <button class="btn btn-secondary btn-sm" id="res-back-to-monitor">← Open Monitor</button>
          <button class="btn btn-ghost btn-sm" id="res-back-to-library">Library</button>
        </div>
      `;
      notAvailNode.querySelector('#res-back-to-monitor')?.addEventListener('click', () => router.go(`/monitor/${jobId}`));
      notAvailNode.querySelector('#res-back-to-library')?.addEventListener('click', () => router.go('/library'));
      body.appendChild(notAvailNode);
      return;
    }

    if (state.result !== _prevResult) {
      _prevResult = state.result;
      body.innerHTML = renderBody(state);
      _wireBody(body, state);

      // Update subtitle to reflect actual clip count
      const subtitle = el.querySelector('#results-subtitle');
      if (subtitle) {
        const count = state.result.ranking.length;
        subtitle.textContent = state.result.isPartialSuccess
          ? `${count} clip${count !== 1 ? 's' : ''} · partial`
          : `${count} clip${count !== 1 ? 's' : ''} ready`;
      }
    } else {
      _updateSelection(body, state);
    }

    updateRightPanel(state);
  });

  await resultsStore.load(jobId);

  el.addEventListener('unmount', () => { unsub(); });
}

function _wireBody(bodyEl, state) {
  const heroWrap = bodyEl.querySelector('#results-hero-wrap');
  if (heroWrap) wireHeroVideo(heroWrap);

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
