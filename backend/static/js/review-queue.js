/* =====================================================================
   ReviewQueue — UP30 Creator Morning Review
   LocalStorage-backed queue of completed render jobs.
   States: new → kept / favorited / dismissed / failed
   ===================================================================== */
window.ReviewQueue = (() => {
  const LS_KEY  = 'review_queue_v1';
  const MAX_ITEMS = 200;
  const STATE = { NEW: 'new', KEPT: 'kept', FAVORITED: 'favorited', DISMISSED: 'dismissed', FAILED: 'failed' };

  let _items = [];

  // ── Storage ────────────────────────────────────────────────────────
  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (_) { return []; }
  }

  function _save() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(_items)); } catch (_) {}
  }

  // ── Public: add a completed job ────────────────────────────────────
  function addJob(jobId, name, outputDir, opts) {
    if (!jobId) return;
    if (_items.find(it => it.jobId === jobId)) return; // no duplicates
    const payload = (opts && opts.payload) || null;
    _items.unshift({
      jobId,
      name:      name || jobId,
      outputDir: outputDir || '',
      state:     (opts && opts.failed) ? STATE.FAILED : STATE.NEW,
      recovered: !!(opts && opts.recovered),
      addedAt:   Date.now(),
      payload,
    });
    if (_items.length > MAX_ITEMS) _items = _items.slice(0, MAX_ITEMS);
    _save();
    _refreshBadge();
  }

  // ── State transitions ──────────────────────────────────────────────
  function keep(jobId) {
    const item = _setState(jobId, STATE.KEPT);
    if (!item) return;
    _log('review_kept', jobId, item.name);
    _steeringFeedback(item, 'keep');
    _showToast('Kept', 'success');
    _refreshView();
  }

  function favorite(jobId) {
    const item = _setState(jobId, STATE.FAVORITED);
    if (!item) return;
    _log('review_favorited', jobId, item.name);
    _steeringFeedback(item, 'favorite');
    _showToast('Added to Favorites', 'success');
    _refreshView();
  }

  function dismiss(jobId) {
    const item = _setState(jobId, STATE.DISMISSED);
    if (!item) return;
    _log('review_dismissed', jobId, item.name);
    _steeringFeedback(item, 'dismiss');
    _showToast('Dismissed', 'info');
    _refreshView();
  }

  function retry(jobId) {
    const item = _items.find(it => it.jobId === jobId);
    if (!item) return;
    _log('review_retry', jobId, item.name);
    _showToast('Switch to the Render tab to retry', 'info');
  }

  function openFolder(jobId) {
    const item = _items.find(it => it.jobId === jobId);
    if (!item || !item.outputDir) return;
    if (typeof openStoredOutputPath === 'function') openStoredOutputPath(item.outputDir);
  }

  function _setState(jobId, newState) {
    const item = _items.find(it => it.jobId === jobId);
    if (!item) return null;
    item.state = newState;
    _save();
    _refreshBadge();
    return item;
  }

  // ── Keyboard handler — call from card onkeydown ────────────────────
  function handleKey(e, jobId) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) return;
    if (e.key === 'k' || e.key === 'K') { e.preventDefault(); keep(jobId); }
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); favorite(jobId); }
    if (e.key === 'd' || e.key === 'D') { e.preventDefault(); dismiss(jobId); }
    if (e.key === 'r' || e.key === 'R') { e.preventDefault(); retry(jobId); }
  }

  // ── Gentle steering feedback ───────────────────────────────────────
  function _steeringFeedback(item, action) {
    try {
      if (action === 'keep' || action === 'favorite') {
        if (typeof CreatorTaste !== 'undefined') CreatorTaste.recordDownload(1);
        const vt = item.payload && (item.payload.variant_type || item.payload.preset_name);
        if (vt && typeof CreatorFeedback !== 'undefined') CreatorFeedback.recordVariantDownload(vt);
      } else if (action === 'dismiss') {
        if (typeof CreatorTaste !== 'undefined') CreatorTaste.recordDownload(99);
      }
    } catch (_) {}
  }

  // ── Sorting ────────────────────────────────────────────────────────
  function _sort(items) {
    return [...items].sort((a, b) => {
      // recovered (failed recovery) floats up within state group
      if (a.recovered !== b.recovered) return a.recovered ? -1 : 1;
      return b.addedAt - a.addedAt;
    });
  }

  // ── Trust chips from payload ───────────────────────────────────────
  function _chips(item) {
    const p = item.payload;
    if (!p) return item.recovered ? '<span class="rqChip rqChipRecovered">recovered</span>' : '';
    const chips = [];
    if (item.recovered) chips.push('<span class="rqChip rqChipRecovered">recovered</span>');
    if (p.preset_name) chips.push(`<span class="rqChip rqChipPreset">${esc(p.preset_name)}</span>`);
    const dna = p.creator_dna;
    if (dna && dna.confident) chips.push(`<span class="rqChip rqChipDna">${esc(dna.confident)}</span>`);
    const sb = p.structure_bias;
    if (sb && sb !== 'balanced') chips.push(`<span class="rqChip rqChipSteer">${esc(sb)}</span>`);
    if (p.asset_logo_path || p.asset_intro_path) chips.push('<span class="rqChip rqChipAsset">assets</span>');
    return chips.join('');
  }

  function esc(v) {
    return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Card HTML ──────────────────────────────────────────────────────
  function _cardHtml(item) {
    const thumbUrl = `/api/jobs/${esc(item.jobId)}/parts/1/thumbnail?t=1`;
    const timeStr  = _relTime(item.addedAt);
    const nameEsc  = esc(item.name);
    const jid      = esc(item.jobId);
    const chipsHtml = _chips(item);

    return `<div class="rqCard rqCard-${item.state}" data-rq-jobid="${jid}"
                 tabindex="0"
                 onkeydown="ReviewQueue.handleKey(event,'${jid}')"
                 aria-label="${nameEsc}">
  <div class="rqCardThumbWrap">
    <img class="rqCardThumb" src="${thumbUrl}" alt=""
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
    <div class="rqCardThumbPlaceholder" style="display:none">&#9654;</div>
  </div>
  <div class="rqCardBody">
    <div class="rqCardTop">
      <div class="rqCardName" title="${nameEsc}">${nameEsc}</div>
      <div class="rqCardTime">${timeStr}</div>
    </div>
    ${chipsHtml ? `<div class="rqChips">${chipsHtml}</div>` : ''}
    <div class="rqCardActions">
      <button class="rqBtn rqBtnKeep"    onclick="ReviewQueue.keep('${jid}')"        title="Keep  K">K</button>
      <button class="rqBtn rqBtnFav"     onclick="ReviewQueue.favorite('${jid}')"    title="Favorite  F">&#9733;</button>
      <button class="rqBtn rqBtnDismiss" onclick="ReviewQueue.dismiss('${jid}')"     title="Dismiss  D">D</button>
      <button class="rqBtn rqBtnRetry"   onclick="ReviewQueue.retry('${jid}')"       title="Retry  R">&#8635;</button>
      <button class="rqBtn rqBtnOpen"    onclick="ReviewQueue.openFolder('${jid}')"  title="Open Folder">&#128193;</button>
    </div>
  </div>
</div>`;
  }

  // ── Relative time ──────────────────────────────────────────────────
  function _relTime(ts) {
    const diff = Date.now() - ts;
    if (diff < 60000)    return 'just now';
    if (diff < 3600000)  return `${Math.floor(diff/60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
    return `${Math.floor(diff/86400000)}d ago`;
  }

  // ── Section HTML ───────────────────────────────────────────────────
  function _sectionHtml(id, label, items, opts) {
    const collapsed  = opts && opts.collapsed;
    const emptyMsg   = (opts && opts.emptyMsg) || '';
    const collapseId = `rqSection_${id}_body`;
    const cardsHtml  = items.length
      ? _sort(items).map(_cardHtml).join('')
      : (emptyMsg ? `<div class="rqEmpty">${emptyMsg}</div>` : '');

    if (!cardsHtml && items.length === 0 && !emptyMsg) return '';

    return `<section class="rqSection rqSection-${id}${collapsed ? ' rqCollapsed' : ''}" aria-label="${label}">
  <div class="rqSectionHeader" onclick="this.closest('.rqSection').classList.toggle('rqCollapsed')">
    <span class="rqSectionTitle">${label}</span>
    <span class="rqSectionCount">${items.length}</span>
    <span class="rqCollapseIcon">&#9660;</span>
  </div>
  <div class="rqSectionBody" id="${collapseId}">
    ${cardsHtml}
  </div>
</section>`;
  }

  // ── Render the full review view ────────────────────────────────────
  function renderView() {
    const container = document.getElementById('rq_view_body');
    if (!container) return;

    const byState = { new: [], kept: [], favorited: [], dismissed: [], failed: [] };
    _items.forEach(it => {
      if (byState[it.state]) byState[it.state].push(it);
    });

    const newSection  = _sectionHtml('new',       'Ready to Review', byState.new,       { emptyMsg: 'All caught up — no new clips.' });
    const favSection  = _sectionHtml('favorited', 'Favorites',       byState.favorited, {});
    const keptSection = _sectionHtml('kept',      'Kept',            byState.kept,      { collapsed: true });
    const failSection = _sectionHtml('failed',    'Needs Retry',     byState.failed,    {});

    container.innerHTML = newSection + favSection + keptSection + failSection
      || '<div class="rqEmpty rqEmptyFull">No clips in the review queue yet.<br>Clips appear here after each completed render.</div>';
  }

  // ── Badge ──────────────────────────────────────────────────────────
  function _refreshBadge() {
    const badge = document.getElementById('rqNavBadge');
    if (!badge) return;
    const count = _items.filter(it => it.state === STATE.NEW).length;
    badge.textContent = count > 0 ? String(count) : '';
    badge.style.display = count > 0 ? '' : 'none';
  }

  function _refreshView() {
    renderView();
    _refreshBadge();
  }

  // ── Log / toast ────────────────────────────────────────────────────
  function _log(event, jobId, name) {
    try {
      if (typeof addEvent === 'function') addEvent(`${event}: ${name} (${jobId})`, 'render');
    } catch (_) {}
  }

  function _showToast(msg, type) {
    try {
      if (typeof showToast === 'function') showToast(msg, type || 'info');
    } catch (_) {}
  }

  // ── Public query ───────────────────────────────────────────────────
  function getNewCount() {
    return _items.filter(it => it.state === STATE.NEW).length;
  }

  // ── Init ───────────────────────────────────────────────────────────
  function init() {
    _items = _load();
    _refreshBadge();
  }

  return { init, addJob, keep, favorite, dismiss, retry, openFolder, renderView, handleKey, getNewCount, STATE };
})();
