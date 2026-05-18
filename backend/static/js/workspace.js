/* =========================================================
   workspace.js — UP32: Creator Workspace
   Default landing view. Consolidates morning workflow into
   one screen: status strip · series continuation · quick
   create · favorites.

   Philosophy:
     - All data from localStorage — instant, no API calls on open.
     - Reads review_queue_v1 and creator_series_v1 directly.
     - No module coupling for reads (resilient if modules absent).
     - Advisory only — no form-fill, no forced selections.
   ========================================================= */
'use strict';

window.CreatorWorkspace = (() => {

  // ── localStorage readers — no module dependency ────────────────────
  function _loadQueue() {
    try { return JSON.parse(localStorage.getItem('review_queue_v1') || '[]'); } catch (_) { return []; }
  }

  function _loadFingerprint() {
    try {
      const d = JSON.parse(localStorage.getItem('creator_series_v1') || '{}');
      return (d && d.fingerprint) ? d.fingerprint : null;
    } catch (_) { return null; }
  }

  // ── Helpers ────────────────────────────────────────────────────────
  function _esc(v) {
    return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function _relTime(ts) {
    const diff = Date.now() - ts;
    if (diff < 60000)    return 'just now';
    if (diff < 3600000)  return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  // ── Section A — Today status strip ────────────────────────────────
  function _renderTodayStrip(items, fp) {
    const now        = Date.now();
    const DAY_MS     = 86400000;
    const todayCount = items.filter(it => (now - it.addedAt) < DAY_MS).length;
    const newCount   = items.filter(it => it.state === 'new').length;

    const chips = [];
    if (todayCount > 0) chips.push(`<span class="wsChip wsChipToday">${todayCount} rendered today</span>`);
    if (newCount   > 0) chips.push(`<span class="wsChip wsChipReview" onclick="if(typeof setView==='function')setView('review')" style="cursor:pointer" title="Go to Review">${newCount} to review</span>`);

    if (fp && fp.series_detected && fp.confidence >= 0.35) {
      const lbl = fp.title_prefix ? `Series: ${fp.title_prefix}` : 'Series style';
      chips.push(`<span class="wsChip wsChipSeries">${_esc(lbl)}</span>`);
    }

    const inner = chips.length
      ? chips.join('')
      : '<span class="wsChipEmpty">No renders yet today — ready when you are.</span>';

    return `<div class="wsStatusStrip" aria-label="Today status">${inner}</div>`;
  }

  // ── Section B — Continue Series ───────────────────────────────────
  function _renderContinueSeries(fp) {
    if (!fp || !fp.series_detected || fp.confidence < 0.35) return '';

    const name    = fp.title_prefix ? `"${_esc(fp.title_prefix)}"` : 'Your series';
    const pct     = Math.round(fp.confidence * 100);
    const metas   = [];
    if (fp.preset_id)  metas.push(`<span class="wsSeriesMeta">${_esc(fp.preset_id)}</span>`);
    if (fp.platform)   metas.push(`<span class="wsSeriesMeta">${_esc(fp.platform)}</span>`);
    const metaHtml = metas.length ? `<div class="wsSeriesMetas">${metas.join('')}</div>` : '';

    return `<div class="wsCard wsSectionSeries">
  <div class="wsCardHeader">
    <div class="wsCardTitle">Continue Series</div>
    <div class="wsCardSub">Series style active &middot; ${pct}% confidence</div>
  </div>
  <div class="wsSeriesName">${name}</div>
  ${metaHtml}
  <button class="wsBtn wsBtnPrimary" onclick="CreatorWorkspace._onContinueSeries()">Continue</button>
</div>`;
  }

  // ── Section C — Quick Create ───────────────────────────────────────
  function _renderQuickCreate() {
    let presetLine = '';
    try {
      if (typeof CreatorPresets !== 'undefined') {
        const active = CreatorPresets.getActive();
        if (active && active.label) {
          presetLine = `<div class="wsQuickMeta">Preset: ${_esc(active.label)}</div>`;
        }
      }
    } catch (_) {}

    return `<div class="wsCard wsSectionCreate">
  <div class="wsCardHeader">
    <div class="wsCardTitle">Quick Create</div>
    <div class="wsCardSub">Start a new clip</div>
  </div>
  ${presetLine}
  <button class="wsBtn wsBtnPrimary" onclick="CreatorWorkspace._onQuickCreate()">Start Creating</button>
</div>`;
  }

  // ── Section D — Favorites ──────────────────────────────────────────
  function _renderFavorites(items) {
    const favs = items.filter(it => it.state === 'favorited').slice(0, 12);

    if (favs.length === 0) {
      return `<div class="wsCard wsSectionFavs">
  <div class="wsCardHeader">
    <div class="wsCardTitle">Favorites</div>
  </div>
  <div class="wsEmpty">Mark clips as Favorite in Review to see them here.</div>
</div>`;
    }

    const cards = favs.map(it => {
      const thumb = `/api/jobs/${_esc(it.jobId)}/parts/1/thumbnail?t=1`;
      return `<div class="wsFavCard" title="${_esc(it.name)}"
    onclick="if(typeof setView==='function'){setView('review');CreatorWorkspace._onReviewClick();}" style="cursor:pointer">
  <img class="wsFavThumb" src="${thumb}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
  <div class="wsFavThumbPlaceholder" style="display:none">&#9654;</div>
  <div class="wsFavName">${_esc(it.name)}</div>
  <div class="wsFavTime">${_relTime(it.addedAt)}</div>
</div>`;
    }).join('');

    return `<div class="wsCard wsSectionFavs">
  <div class="wsCardHeader">
    <div class="wsCardTitle">Favorites</div>
    <div class="wsCardSub">${favs.length} clip${favs.length !== 1 ? 's' : ''}</div>
  </div>
  <div class="wsFavGrid">${cards}</div>
</div>`;
  }

  // ── Render ─────────────────────────────────────────────────────────
  function renderView() {
    const container = document.getElementById('ws_view_body');
    if (!container) return;

    const items = _loadQueue();
    const fp    = _loadFingerprint();

    container.innerHTML = `
      ${_renderTodayStrip(items, fp)}
      <div class="wsMain">
        ${_renderContinueSeries(fp)}
        ${_renderQuickCreate()}
        ${_renderFavorites(items)}
      </div>`;
  }

  // ── CTA handlers ───────────────────────────────────────────────────
  function _onContinueSeries() {
    _log('workspace_continue_series');
    _log('workspace_action', 'continue_series');
    if (typeof setView === 'function') setView('render');
  }

  function _onQuickCreate() {
    _log('workspace_action', 'quick_create');
    if (typeof setView === 'function') setView('render');
  }

  function _onReviewClick() {
    _log('workspace_review_click');
    _log('workspace_action', 'review_click');
  }

  // ── Logging ────────────────────────────────────────────────────────
  function _log(event, detail) {
    try {
      const msg = detail ? `${event}: ${detail}` : event;
      if (typeof addEvent === 'function') addEvent(msg, 'render');
    } catch (_) {}
  }

  // ── Lifecycle ──────────────────────────────────────────────────────
  function init() {
    _log('workspace_opened');
    renderView();
  }

  return { init, renderView, _onContinueSeries, _onQuickCreate, _onReviewClick };

})();
