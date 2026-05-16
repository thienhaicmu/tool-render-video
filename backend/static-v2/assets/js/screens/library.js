/* Library screen — browse render history, reopen results, return to active jobs.
   Defensive: never throws on null/malformed result_json, missing status, or missing dates.
   Navigation rules:
     completed/completed_with_errors/partial → #/results/:jobId
     queued/running                          → #/monitor/:jobId
     failed                                 → inline Retry (renderApi.retry)
     interrupted                            → inline Resume (renderApi.resume)
*/

import { jobsApi }       from '../api/jobs.js';
import { renderApi }     from '../api/render.js';
import { normalizeJob }  from '../entities/job.js';
import { statusChip }    from '../components/status-chip.js';
import { aiBadge }       from '../components/ai-badge.js';
import { emptyState, ICONS } from '../components/empty-state.js';
import { router }        from '../router.js';

/* ── Status sets ─────────────────────────────────────────────────────── */

const ACTIVE_STATUSES    = new Set(['queued', 'running']);
const COMPLETED_STATUSES = new Set(['completed', 'completed_with_errors']);
const VIEW_STATUSES      = new Set(['completed', 'completed_with_errors', 'partial']);
const RETRY_STATUSES     = new Set(['failed']);
const RESUME_STATUSES    = new Set(['interrupted']);

/* ── Normalizer ──────────────────────────────────────────────────────── */

function normalizeHistoryItem(raw) {
  const job = normalizeJob(raw);
  if (!job) return null;

  let title       = null;
  let bestScore   = null;
  let hasAI       = false;
  let outputCount = null;

  try {
    const p = job.payload ?? {};
    title = p.title ?? p.source_url ?? p.source_path ?? null;
  } catch { /* ignore */ }

  try {
    const r = job.resultRaw;
    if (r && typeof r === 'object') {
      const ranking = Array.isArray(r.output_ranking) ? r.output_ranking : [];
      if (ranking.length > 0) {
        bestScore   = Number(ranking[0]?.score ?? 0) || null;
        outputCount = ranking.length;
      }
      hasAI = !!(r.ai_director ?? r.ai_render_influence ?? r.ai_execution_metrics);
    }
  } catch { /* ignore */ }

  return {
    ...job,
    displayTitle: _normalizeDisplayTitle(title, job.jobId, job.createdAt),
    bestScore,
    hasAI,
    outputCount,
  };
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function _trunc(s, n) {
  const str = String(s ?? '');
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function _fmtDateShort(str) {
  if (!str) return null;
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch { return null; }
}

function _normalizeDisplayTitle(rawTitle, jobId, createdAt) {
  if (!rawTitle) {
    const ds = _fmtDateShort(createdAt);
    return ds ? `Untitled render · ${ds}` : `Render ${jobId.slice(0, 8)}`;
  }
  // YouTube URL → short video ID
  const yt = rawTitle.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([A-Za-z0-9_-]{6,12})/);
  if (yt) return `YouTube · ${yt[1]}`;
  // File path → filename without extension
  if (/[/\\]/.test(rawTitle)) {
    const parts = rawTitle.replace(/\\/g, '/').split('/');
    const fname = parts[parts.length - 1] ?? rawTitle;
    return _trunc(fname.replace(/\.[^.]+$/, '') || fname, 60);
  }
  return _trunc(rawTitle, 60);
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _fmtDate(str) {
  if (!str) return null;
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  } catch { return null; }
}

/* ── Filter logic ────────────────────────────────────────────────────── */

const FILTER_KEYS = ['all', 'running', 'completed', 'partial', 'failed', 'interrupted'];

function _filterItems(items, filter, search) {
  let out = items;

  if (filter !== 'all') {
    out = out.filter(({ status }) => {
      if (filter === 'running')     return ACTIVE_STATUSES.has(status);
      if (filter === 'completed')   return COMPLETED_STATUSES.has(status);
      if (filter === 'partial')     return status === 'partial';
      if (filter === 'failed')      return status === 'failed';
      if (filter === 'interrupted') return status === 'interrupted';
      return true;
    });
  }

  const q = search.trim().toLowerCase();
  if (q) {
    out = out.filter(item =>
      item.displayTitle.toLowerCase().includes(q) ||
      item.jobId.toLowerCase().includes(q)
    );
  }

  return out;
}

/* ── Card rendering ──────────────────────────────────────────────────── */

function _renderCard(item) {
  const dateStr = _fmtDate(item.createdAt);

  let scorePart = '';
  if (item.bestScore != null && item.bestScore > 0) {
    const c = item.bestScore >= 70 ? 'var(--color-success)'
            : item.bestScore >= 40 ? 'var(--color-warning)'
            : 'var(--color-failed)';
    scorePart = `<span class="text-caption" style="color:${c};font-weight:600">Score ${Math.round(item.bestScore)}</span>`;
  }

  const metaParts = [
    dateStr         ? `<span class="text-caption text-faint">${_esc(dateStr)}</span>` : '',
    item.outputCount != null
      ? `<span class="text-caption text-faint">${item.outputCount} clip${item.outputCount !== 1 ? 's' : ''}</span>`
      : '',
    scorePart,
  ].filter(Boolean);

  const actionParts = [
    VIEW_STATUSES.has(item.status)
      ? `<button class="btn btn-sm btn-secondary lib-action" data-action="results" data-job-id="${_esc(item.jobId)}">View Results</button>`
      : '',
    ACTIVE_STATUSES.has(item.status)
      ? `<button class="btn btn-sm btn-secondary lib-action" data-action="monitor" data-job-id="${_esc(item.jobId)}">Monitor</button>`
      : '',
    RETRY_STATUSES.has(item.status)
      ? `<button class="btn btn-sm btn-ghost lib-action" data-action="retry" data-job-id="${_esc(item.jobId)}">Retry</button>`
      : '',
    RESUME_STATUSES.has(item.status)
      ? `<button class="btn btn-sm btn-ghost lib-action" data-action="resume" data-job-id="${_esc(item.jobId)}">Resume</button>`
      : '',
  ].filter(Boolean);

  return `
    <div class="lib-card card" data-job-id="${_esc(item.jobId)}">
      <div class="row gap-3" style="align-items:flex-start">
        <div class="col gap-2 flex-1" style="min-width:0">
          <div class="lib-card__title text-body">${_esc(item.displayTitle)}</div>
          <div class="row gap-2" style="flex-wrap:wrap;align-items:center">
            ${statusChip(item.status)}
            ${item.hasAI ? aiBadge('advisory') : ''}
          </div>
          ${metaParts.length ? `<div class="row gap-3" style="flex-wrap:wrap">${metaParts.join('')}</div>` : ''}
        </div>
        ${actionParts.length ? `<div class="lib-card__actions row gap-2">${actionParts.join('')}</div>` : ''}
      </div>
    </div>
  `.trim();
}

const _PAGE_SIZE = 20;

/* ── Module-level screen state (reset on each mount) ─────────────────── */

let _history     = [];
let _filter      = 'all';
let _search      = '';
let _loading     = false;
let _loadingMore = false;
let _hasMore     = false;
let _offset      = 0;
let _error       = null;
let _listEl      = null;

/* ── Load history from API (initial page) ────────────────────────────── */

async function _load() {
  _history     = [];
  _offset      = 0;
  _hasMore     = false;
  _loadingMore = false;
  _loading     = true;
  _error       = null;
  _renderList();

  try {
    const raw   = await jobsApi.getHistory({ limit: _PAGE_SIZE, offset: 0 });
    const items = Array.isArray(raw)
      ? raw
      : (Array.isArray(raw?.items) ? raw.items : []);

    // Backend returns items ordered by updated_at DESC — trust that ordering.
    _history = items
      .map(r => { try { return normalizeHistoryItem(r); } catch { return null; } })
      .filter(Boolean);

    _hasMore = raw?.has_more ?? false;
    _offset  = _PAGE_SIZE;
    _loading = false;
    _renderList();
  } catch (err) {
    _loading = false;
    _error   = String(err?.message ?? 'Failed to load history');
    _renderList();
  }
}

/* ── Append the next page ─────────────────────────────────────────────── */

async function _loadMore() {
  if (_loadingMore || !_hasMore) return;
  _loadingMore = true;
  _renderList();

  try {
    const raw   = await jobsApi.getHistory({ limit: _PAGE_SIZE, offset: _offset });
    const items = Array.isArray(raw)
      ? raw
      : (Array.isArray(raw?.items) ? raw.items : []);

    const next = items
      .map(r => { try { return normalizeHistoryItem(r); } catch { return null; } })
      .filter(Boolean);

    _history     = [..._history, ...next];
    _hasMore     = raw?.has_more ?? false;
    _offset     += _PAGE_SIZE;
    _loadingMore = false;
    _renderList();
  } catch (err) {
    _loadingMore = false;
    _renderList();
  }
}

/* ── Render job list panel ───────────────────────────────────────────── */

function _renderList() {
  if (!_listEl) return;

  if (_loading) {
    _listEl.innerHTML = `
      <div class="col gap-2">
        ${[0, 1, 2, 3].map(() =>
          `<div class="skeleton-block" style="height:88px;border-radius:var(--radius-panel)"></div>`
        ).join('')}
      </div>`;
    return;
  }

  if (_error) {
    _listEl.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'card col gap-3';
    wrap.style.borderColor = 'var(--color-failed)';
    wrap.innerHTML = `
      <div class="text-body" style="color:var(--color-failed)">Failed to load history</div>
      <div class="text-caption text-faint">${_esc(_error)}</div>
      <button class="btn btn-secondary btn-sm" id="lib-err-retry">Try again</button>
    `;
    wrap.querySelector('#lib-err-retry').addEventListener('click', _load);
    _listEl.appendChild(wrap);
    return;
  }

  const visible = _filterItems(_history, _filter, _search);

  if (visible.length === 0) {
    _listEl.innerHTML = '';
    const msg = _history.length === 0
      ? 'No renders found. Start a render from Create to see your projects here.'
      : 'No jobs match the current filter or search.';
    _listEl.appendChild(emptyState({ icon: ICONS.empty, title: 'Nothing here', body: msg }));
    // Still offer "Load more" below the empty state if there are server-side pages remaining.
    if (_hasMore) {
      const moreWrap = document.createElement('div');
      moreWrap.className = 'col';
      moreWrap.style.cssText = 'align-items:center;padding-top:var(--space-3)';
      moreWrap.innerHTML = `<button class="btn btn-secondary btn-sm" id="lib-load-more" ${_loadingMore ? 'disabled' : ''}>${_loadingMore ? 'Loading…' : 'Load more'}</button>`;
      moreWrap.querySelector('#lib-load-more')?.addEventListener('click', _loadMore);
      _listEl.appendChild(moreWrap);
    }
    return;
  }

  const moreBtn = _hasMore
    ? `<div class="col" style="align-items:center;padding-top:var(--space-3)">
         <button class="btn btn-secondary btn-sm" id="lib-load-more" ${_loadingMore ? 'disabled' : ''}>${_loadingMore ? 'Loading…' : 'Load more'}</button>
       </div>`
    : '';

  _listEl.innerHTML = `<div class="col gap-2">${visible.map(_renderCard).join('')}</div>${moreBtn}`;
  _wireCards();
  _listEl.querySelector('#lib-load-more')?.addEventListener('click', _loadMore);
}

/* ── Wire card interactions ──────────────────────────────────────────── */

function _wireCards() {
  if (!_listEl) return;

  _listEl.querySelectorAll('.lib-action').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      _handleAction(btn.dataset.action, btn.dataset.jobId, btn);
    });
  });

  _listEl.querySelectorAll('.lib-card').forEach(card => {
    card.addEventListener('click', () => {
      const id   = card.dataset.jobId;
      const item = _history.find(h => h.jobId === id);
      if (!item) return;
      if (VIEW_STATUSES.has(item.status))        router.go(`/projects/${id}`);
      else if (ACTIVE_STATUSES.has(item.status)) router.go(`/monitor/${id}`);
    });
  });
}

/* ── Action handler ──────────────────────────────────────────────────── */

async function _handleAction(action, jobId, btn) {
  if (!jobId) return;
  if (action === 'results') { router.go(`/projects/${jobId}`); return; }
  if (action === 'monitor') { router.go(`/monitor/${jobId}`); return; }

  const isRetry = action === 'retry';
  if (!isRetry && action !== 'resume') return;

  btn.disabled    = true;
  btn.textContent = isRetry ? 'Retrying…' : 'Resuming…';

  try {
    const res   = isRetry
      ? await renderApi.retry(jobId)
      : await renderApi.resume(jobId);
    const newId = res?.job_id ?? res?.id ?? jobId;
    router.go(`/monitor/${newId}`);
  } catch (err) {
    btn.disabled    = false;
    btn.textContent = isRetry ? 'Retry' : 'Resume';
    _showCardError(jobId, String(err?.message ?? `${action} failed`));
  }
}

function _showCardError(jobId, msg) {
  const card = _listEl?.querySelector(`.lib-card[data-job-id="${CSS.escape(jobId)}"]`);
  if (!card) return;
  card.querySelector('.lib-action-err')?.remove();
  const el = document.createElement('div');
  el.className   = 'lib-action-err text-caption mt-2';
  el.style.color = 'var(--color-failed)';
  el.textContent = msg;
  card.appendChild(el);
}

/* ── Filter bar ──────────────────────────────────────────────────────── */

function _renderFilterBar(container) {
  container.innerHTML = `
    <div class="lib-filter-bar row gap-2">
      <div class="lib-filter-pills row gap-1">
        ${FILTER_KEYS.map(k => `
          <button class="lib-filter-pill${_filter === k ? ' lib-filter-pill--active' : ''}" data-filter="${k}">
            ${k.charAt(0).toUpperCase() + k.slice(1)}
          </button>`).join('')}
      </div>
      <span class="flex-1"></span>
      <input class="lib-search" type="text" placeholder="Search title or job ID…" value="${_esc(_search)}" />
    </div>
  `;

  container.querySelectorAll('.lib-filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      _filter = btn.dataset.filter;
      container.querySelectorAll('.lib-filter-pill').forEach(b =>
        b.classList.toggle('lib-filter-pill--active', b.dataset.filter === _filter)
      );
      _renderList();
    });
  });

  container.querySelector('.lib-search')?.addEventListener('input', e => {
    _search = e.target.value;
    _renderList();
  });
}

/* ── Mount ───────────────────────────────────────────────────────────── */

export async function mount(el, _params) {
  _history     = [];
  _filter      = 'all';
  _search      = '';
  _loading     = false;
  _loadingMore = false;
  _hasMore     = false;
  _offset      = 0;
  _error       = null;
  _listEl      = null;

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Library</div>
          <div class="screen__subtitle">Past renders and active jobs</div>
        </div>
        <span class="flex-1"></span>
        <button class="btn btn-ghost" id="lib-refresh">↻ Refresh</button>
      </div>
    </div>
    <div class="screen__body col gap-4" id="lib-body">
      <div id="lib-filter-wrap"></div>
      <div id="lib-list"></div>
    </div>
  `;

  _listEl = el.querySelector('#lib-list');

  _renderFilterBar(el.querySelector('#lib-filter-wrap'));
  el.querySelector('#lib-refresh').addEventListener('click', _load);

  await _load();
}

export const libraryScreen = { mount };
