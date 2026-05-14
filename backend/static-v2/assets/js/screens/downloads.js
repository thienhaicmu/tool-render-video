/* Downloads screen — standalone batch download of public videos.
   Separate workflow from render pipeline. Never mixes into render state.
   Contract: POST /api/download/process, POST /api/download/retry/{job_id}
   Quality preset is a UI-only preference — omitted from API payload until
   backend contract documents a matching field (§9.1 only specifies urls + output_dir).
*/

import { downloadApi }   from '../api/download.js';
import { normalizeJob }  from '../entities/job.js';
import { statusChip }    from '../components/status-chip.js';
import { desktopAdapter } from '../desktop-adapter.js';
import { router }         from '../router.js';

/* ── URL parsing ─────────────────────────────────────────────────────── */

function parseUrlInput(raw) {
  const lines   = String(raw ?? '').split('\n');
  const valid   = [];
  const invalid = [];
  const seen    = new Set();
  let   dupes   = 0;

  for (const line of lines) {
    const url = line.trim();
    if (!url) continue;
    if (!/^https?:\/\//i.test(url)) { invalid.push(url); continue; }
    if (seen.has(url))               { dupes++;           continue; }
    seen.add(url);
    valid.push(url);
  }

  return { valid, invalid, dupes };
}

/* ── Quality options (UI-only; not sent to backend) ─────────────────── */

const QUALITY_OPTIONS = [
  { value: 'best',     label: 'Best',     note: 'Highest available resolution' },
  { value: 'balanced', label: 'Balanced', note: 'Good quality, smaller file' },
  { value: 'fast',     label: 'Fast',     note: 'Fastest, smallest file' },
];

/* ── Helpers ─────────────────────────────────────────────────────────── */

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _trunc(s, n) {
  const str = String(s ?? '');
  return str.length > n ? str.slice(0, n) + '…' : str;
}

/* ── Module-level screen state (reset on each mount) ─────────────────── */

let _urlRaw      = '';
let _outputDir   = '';
let _quality     = 'best';
let _submitting  = false;
let _checkingStatus = false;
let _el          = null;

/* ── Result state (persisted after submit so user can check/retry) ─── */

let _lastJob = null; // { jobId, status, count, outputDir, items }

/* ── URL feedback ────────────────────────────────────────────────────── */

function _renderUrlFeedback(parsed) {
  const feedEl = _el?.querySelector('#dl-url-feedback');
  if (!feedEl) return;

  const parts = [];
  if (parsed.valid.length > 0) {
    parts.push(`<span class="text-caption" style="color:var(--color-success)">${parsed.valid.length} valid URL${parsed.valid.length !== 1 ? 's' : ''}</span>`);
  }
  if (parsed.invalid.length > 0) {
    parts.push(`<span class="text-caption" style="color:var(--color-failed)">${parsed.invalid.length} invalid — must start with https://</span>`);
  }
  if (parsed.dupes > 0) {
    parts.push(`<span class="text-caption text-faint">${parsed.dupes} duplicate${parsed.dupes !== 1 ? 's' : ''} removed</span>`);
  }

  feedEl.innerHTML = parts.length
    ? `<div class="row gap-3" style="flex-wrap:wrap">${parts.join('')}</div>`
    : '';
}

/* ── Submit button state ─────────────────────────────────────────────── */

function _updateSubmitBtn(parsed) {
  const btn = _el?.querySelector('#dl-submit');
  if (!btn) return;
  btn.disabled    = parsed.valid.length === 0 || _submitting;
  btn.textContent = _submitting ? 'Starting…' : 'Start Download';
}

/* ── Inline error ────────────────────────────────────────────────────── */

function _setError(elId, msg) {
  const el = _el?.querySelector(`#${elId}`);
  if (!el) return;
  el.innerHTML = msg
    ? `<div class="text-caption mt-1" style="color:var(--color-failed)">${_esc(msg)}</div>`
    : '';
}

/* ── Job result panel ────────────────────────────────────────────────── */

function _renderJobPanel() {
  const panel = _el?.querySelector('#dl-job-panel');
  if (!panel) return;

  if (!_lastJob) {
    panel.hidden = true;
    return;
  }

  const job = _lastJob;
  panel.hidden = false;

  const isFailed = job.status === 'failed';

  const itemsHtml = Array.isArray(job.items) && job.items.length > 0
    ? `<div class="col gap-1 mt-2">
        ${job.items.slice(0, 8).map(item => `
          <div class="dl-item-row row gap-2">
            <span class="text-caption text-faint dl-item-part">Part ${_esc(String(item.part_no ?? '?'))}</span>
            <span class="text-caption dl-item-source">${_esc(item.source ?? 'unknown')}</span>
            <span class="text-caption text-faint dl-item-url" title="${_esc(item.url ?? '')}">${_esc(_trunc(item.url ?? '', 48))}</span>
          </div>`).join('')}
        ${job.items.length > 8 ? `<div class="text-caption text-faint mt-1">…and ${job.items.length - 8} more</div>` : ''}
      </div>`
    : '';

  panel.innerHTML = `
    <div class="col gap-3">
      <div class="row gap-3" style="align-items:center;flex-wrap:wrap">
        <div class="text-section">Download job submitted</div>
        <span class="flex-1"></span>
        <span id="dl-job-status-chip">${statusChip(job.status ?? 'queued')}</span>
      </div>
      <div class="row gap-2" style="flex-wrap:wrap;align-items:center">
        <span class="text-caption text-faint">Job ID:</span>
        <span class="text-caption" style="font-family:monospace;color:var(--color-text-muted)">${_esc(job.jobId)}</span>
      </div>
      ${job.count != null ? `<div class="text-caption text-faint">${job.count} item${job.count !== 1 ? 's' : ''} queued</div>` : ''}
      ${job.outputDir ? `<div class="text-caption text-faint">Output: <code style="font-family:monospace">${_esc(_trunc(job.outputDir, 60))}</code></div>` : ''}
      ${itemsHtml}
      <div class="row gap-2 mt-2" style="flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" id="dl-view-library">View in Library</button>
        <button class="btn btn-ghost btn-sm" id="dl-check-status">${_checkingStatus ? 'Checking…' : 'Check Status'}</button>
        ${isFailed ? `<button class="btn btn-ghost btn-sm" id="dl-retry-btn">Retry failed items</button>` : ''}
      </div>
      <div id="dl-job-error"></div>
    </div>
  `;

  panel.querySelector('#dl-view-library')?.addEventListener('click', () => {
    router.go('/library');
  });

  panel.querySelector('#dl-check-status')?.addEventListener('click', _checkJobStatus);

  panel.querySelector('#dl-retry-btn')?.addEventListener('click', _handleRetry);
}

/* ── Check status ────────────────────────────────────────────────────── */

async function _checkJobStatus() {
  if (!_lastJob?.jobId || _checkingStatus) return;

  _checkingStatus = true;
  const btn = _el?.querySelector('#dl-check-status');
  if (btn) { btn.disabled = true; btn.textContent = 'Checking…'; }

  try {
    const raw = await downloadApi.getDownloadJob(_lastJob.jobId);
    const job = normalizeJob(raw);
    if (job) {
      _lastJob = { ..._lastJob, status: job.status };
    }
  } catch (err) {
    _setError('dl-job-error', String(err?.message ?? 'Status check failed'));
  } finally {
    _checkingStatus = false;
    _renderJobPanel();
  }
}

/* ── Retry handler ───────────────────────────────────────────────────── */

async function _handleRetry() {
  if (!_lastJob?.jobId) return;

  const btn = _el?.querySelector('#dl-retry-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Retrying…'; }

  try {
    const res = await downloadApi.retryDownload(_lastJob.jobId, []);
    _lastJob = {
      ..._lastJob,
      status: res.status ?? 'queued',
    };
    _setError('dl-job-error', null);
    _renderJobPanel();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Retry failed items'; }
    _setError('dl-job-error', String(err?.message ?? 'Retry failed'));
  }
}

/* ── Output folder section ───────────────────────────────────────────── */

function _renderFolderSection(container) {
  if (desktopAdapter.isDesktop) {
    container.innerHTML = `
      <div class="col gap-2">
        <div class="text-section">Output folder</div>
        <div class="row gap-2" style="align-items:center">
          <button class="btn btn-secondary btn-sm" id="dl-pick-dir">Browse…</button>
          <span class="text-caption text-faint" id="dl-dir-display">${_outputDir ? _esc(_trunc(_outputDir, 50)) : 'No folder selected'}</span>
        </div>
        <div class="text-caption text-faint">Downloads will be saved to this folder.</div>
      </div>
    `;
    container.querySelector('#dl-pick-dir')?.addEventListener('click', async () => {
      const dir = await desktopAdapter.pickOutputDir();
      if (dir) {
        _outputDir = dir;
        const disp = container.querySelector('#dl-dir-display');
        if (disp) disp.textContent = _trunc(dir, 50);
      }
    });
  } else {
    container.innerHTML = `
      <div class="col gap-2">
        <div class="text-section">Output folder</div>
        <input class="dl-path-input" id="dl-dir-input" type="text"
          placeholder="e.g. D:\\Downloads\\videos or /home/user/videos"
          value="${_esc(_outputDir)}" />
        <div class="text-caption text-faint">Enter a backend-readable path. Leave blank to use backend default.</div>
      </div>
    `;
    container.querySelector('#dl-dir-input')?.addEventListener('input', e => {
      _outputDir = e.target.value;
    });
  }
}

/* ── Submit handler ──────────────────────────────────────────────────── */

async function _handleSubmit() {
  const parsed = parseUrlInput(_urlRaw);
  if (parsed.valid.length === 0 || _submitting) return;

  _submitting = true;
  _setError('dl-submit-error', null);
  _updateSubmitBtn(parsed);

  try {
    const payload = {
      urls: parsed.valid,
      ...((_outputDir && _outputDir.trim()) ? { output_dir: _outputDir.trim() } : {}),
    };

    const res = await downloadApi.processDownload(payload);

    _lastJob = {
      jobId:     String(res.job_id ?? res.id ?? ''),
      status:    String(res.status ?? 'queued'),
      count:     res.count  != null ? Number(res.count) : parsed.valid.length,
      outputDir: String(res.output_dir ?? _outputDir ?? ''),
      items:     Array.isArray(res.items) ? res.items : [],
    };

    // Clear the form
    _urlRaw = '';
    const textarea = _el?.querySelector('#dl-url-input');
    if (textarea) textarea.value = '';
    _renderUrlFeedback({ valid: [], invalid: [], dupes: 0 });

    _outputDir = '';
    const folderSection = _el?.querySelector('#dl-folder-section');
    if (folderSection) _renderFolderSection(folderSection);

    _renderJobPanel();
    _el?.querySelector('#dl-job-panel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    _setError('dl-submit-error', String(err?.message ?? 'Submission failed. Check that the backend is running.'));
  } finally {
    _submitting = false;
    _updateSubmitBtn(parseUrlInput(_urlRaw));
  }
}

/* ── Mount ───────────────────────────────────────────────────────────── */

export async function mount(el, _params) {
  _urlRaw         = '';
  _outputDir      = '';
  _quality        = 'best';
  _submitting     = false;
  _checkingStatus = false;
  _lastJob        = null;
  _el             = el;

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Downloads</div>
          <div class="screen__subtitle">Batch download public videos for later rendering</div>
        </div>
        <span class="flex-1"></span>
        <span class="dl-mode-note text-caption text-faint">Standalone download workflow</span>
      </div>
    </div>
    <div class="screen__body col gap-4" id="dl-body">

      <!-- URL input -->
      <div class="card col gap-3">
        <div class="text-section">URLs to download</div>
        <div class="text-caption text-faint">One URL per line · duplicates removed automatically · http/https only</div>
        <textarea id="dl-url-input" class="dl-url-textarea" rows="7"
          placeholder="https://www.youtube.com/watch?v=&#10;https://www.instagram.com/reel/&#10;https://www.facebook.com/watch/"></textarea>
        <div id="dl-url-feedback"></div>
      </div>

      <!-- Options -->
      <div class="card col gap-4">
        <div id="dl-folder-section"></div>

        <div class="col gap-2">
          <div class="text-section">Quality preset</div>
          <div class="row gap-2">
            ${QUALITY_OPTIONS.map(opt => `
              <button class="dl-quality-pill${_quality === opt.value ? ' dl-quality-pill--active' : ''}"
                data-quality="${opt.value}" title="${_esc(opt.note)}">${_esc(opt.label)}</button>`).join('')}
          </div>
          <div class="text-caption text-faint" id="dl-quality-note">
            ${_esc(QUALITY_OPTIONS.find(o => o.value === _quality)?.note ?? '')}
          </div>
        </div>
      </div>

      <!-- Submit -->
      <div class="col gap-2">
        <button class="btn btn-primary" id="dl-submit" disabled>Start Download</button>
        <div id="dl-submit-error"></div>
      </div>

      <!-- Result panel (hidden until first successful submit) -->
      <div class="card" id="dl-job-panel" hidden></div>

    </div>
  `;

  // Output folder section
  _renderFolderSection(el.querySelector('#dl-folder-section'));

  // Textarea
  el.querySelector('#dl-url-input')?.addEventListener('input', e => {
    _urlRaw = e.target.value;
    const parsed = parseUrlInput(_urlRaw);
    _renderUrlFeedback(parsed);
    _updateSubmitBtn(parsed);
  });

  // Quality pills
  el.querySelectorAll('.dl-quality-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      _quality = btn.dataset.quality;
      el.querySelectorAll('.dl-quality-pill').forEach(b =>
        b.classList.toggle('dl-quality-pill--active', b.dataset.quality === _quality)
      );
      const noteEl = el.querySelector('#dl-quality-note');
      if (noteEl) noteEl.textContent = QUALITY_OPTIONS.find(o => o.value === _quality)?.note ?? '';
    });
  });

  // Submit
  el.querySelector('#dl-submit')?.addEventListener('click', _handleSubmit);
}

export const downloadsScreen = { mount };
