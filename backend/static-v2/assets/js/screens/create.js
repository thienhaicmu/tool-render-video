/* Create workspace (UI-R5C.1) — creator-native, preview-first.
   State machine: import → preparing → configure
   Layout: .cw (column) → .cw-hero (flex-1) | .cw-controls | .cw-cta
   Shell right panel hidden by layout.css [data-route="create"] rule.
*/

import { draftStore }                 from '../store/draft.js';
import { renderApi }                  from '../api/render.js';
import { desktopAdapter }             from '../desktop-adapter.js';
import { readinessStore }             from '../store/readiness.js';
import { router }                     from '../router.js';
import { parsePrepareSourceResponse } from '../entities/source-session.js';
import { validateRenderDraft }        from '../entities/render-request.js';
import { withTimeout }                from '../transport.js';

const PREPARE_TIMEOUT_MS = 45_000;

const PRESETS = [
  { id: 'hooks',    label: 'Fast Hooks',    desc: '10–30s · up to 8 clips',  patch: { minPartSec: 10, maxPartSec: 30,  maxExportParts: 8, aiEnabled: true,  aiInfluenceEnabled: true  } },
  { id: 'balanced', label: 'Balanced',      desc: '20–60s · up to 5 clips',  patch: { minPartSec: 20, maxPartSec: 60,  maxExportParts: 5, aiEnabled: true,  aiInfluenceEnabled: false } },
  { id: 'story',    label: 'Story',         desc: '45–120s · up to 3 clips', patch: { minPartSec: 45, maxPartSec: 120, maxExportParts: 3, aiEnabled: false, aiInfluenceEnabled: false } },
  { id: 'full',     label: 'Full Segments', desc: '2–5 min · up to 3 clips', patch: { minPartSec: 90, maxPartSec: 300, maxExportParts: 3, aiEnabled: false, aiInfluenceEnabled: false } },
];

const FORMATS = [
  { id: '9:16',  label: '9:16' },
  { id: '1:1',   label: '1:1' },
  { id: '16:9',  label: '16:9' },
];

let _phase        = 'import';
let _srcMode      = 'youtube';
let _url          = '';
let _filePath     = '';
let _outputDir    = '';
let _error        = null;
let _session      = null;
let _activePreset = 'balanced';
let _advOpen      = false;
let _generating   = false;
let _el           = null;

/* ── Helpers ─────────────────────────────────────────────────────────── */

function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fmt(sec) {
  if (sec == null) return '';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function _trunc(s, n) {
  const str = String(s ?? '');
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function _clipEstimate() {
  const { draft } = draftStore.getState();
  if (!draft.sessionDuration || draft.sessionDuration <= 0) return null;
  const avg = (draft.minPartSec + draft.maxPartSec) / 2;
  return Math.max(1, Math.min(Math.floor(draft.sessionDuration / avg), draft.maxExportParts));
}

/* ── Hero: import ────────────────────────────────────────────────────── */

function _heroImport() {
  const { ytdlpAvailable } = readinessStore.getState();
  const ytDisabled = ytdlpAvailable === false;
  const isYt = _srcMode === 'youtube';

  return `
    <div class="cw-import">
      <div class="cw-import-inner col gap-6">
        <div>
          <div class="cw-import-title">Drop your video</div>
          <div class="cw-import-sub">YouTube link or local file — we handle the rest</div>
        </div>

        <div class="col gap-4">
          <div class="cw-tabs row gap-1">
            <button class="cw-tab${isYt ? ' cw-tab--active' : ''}" data-tab="youtube"
              ${ytDisabled ? 'disabled title="yt-dlp unavailable"' : ''}>YouTube</button>
            <button class="cw-tab${!isYt ? ' cw-tab--active' : ''}" data-tab="local">Local File</button>
          </div>

          ${isYt ? `
            <div class="col gap-2">
              <input class="cw-url-input" id="cw-url" type="url"
                placeholder="https://www.youtube.com/watch?v=…"
                value="${_esc(_url)}" autocomplete="off" spellcheck="false" />
              ${ytDisabled ? `<div class="cw-warning row gap-2"><span>⚠</span><span>yt-dlp unavailable — switch to Local File</span></div>` : ''}
            </div>
          ` : `
            <div class="col gap-2">
              <div class="row gap-2">
                <input class="cw-url-input flex-1" id="cw-file" type="text"
                  placeholder="Paste video file path…"
                  value="${_esc(_filePath)}" autocomplete="off" />
                ${desktopAdapter.filePickerAvailable
                  ? `<button class="btn btn-secondary" id="cw-browse-file">Browse…</button>`
                  : ''}
              </div>
              <div class="cw-import-sub">MP4, MOV, MKV — must be readable by the backend</div>
            </div>
          `}
        </div>

        <div class="col gap-2">
          <div class="cw-field-label">Output folder</div>
          <div class="row gap-2">
            <input class="cw-url-input flex-1" id="cw-output" type="text"
              placeholder="Where should clips be saved?"
              value="${_esc(_outputDir)}" />
            ${desktopAdapter.folderPickerAvailable
              ? `<button class="btn btn-secondary" id="cw-browse-dir">Browse…</button>`
              : ''}
          </div>
          ${!_outputDir ? `<div class="cw-import-sub">Required — folder must be writable by the backend</div>` : ''}
        </div>

        ${_error ? `<div class="cw-error">${_esc(_error)}</div>` : ''}
      </div>
    </div>
  `;
}

/* ── Hero: preparing ─────────────────────────────────────────────────── */

function _heroPreparing() {
  return `
    <div class="cw-preparing">
      <div class="spinner" style="width:40px;height:40px;border-width:3px"></div>
      <div class="cw-preparing-label">Preparing your video…</div>
      <div class="cw-preparing-sub">This may take a moment for YouTube videos</div>
    </div>
  `;
}

/* ── Hero: configure (video preview) ─────────────────────────────────── */

function _heroConfigure() {
  const previewUrl = _session?.sessionId
    ? renderApi.getPreviewVideoUrl(_session.sessionId)
    : null;

  return `
    <div class="cw-preview">
      ${previewUrl ? `
        <video class="cw-preview__video" src="${_esc(previewUrl)}"
          controls muted playsinline preload="metadata"></video>
      ` : `
        <div class="cw-preview--idle">
          <span class="cw-preview--idle-icon" aria-hidden="true">▶</span>
          <span class="cw-preview--idle-text">No preview available</span>
        </div>
      `}
      <div class="cw-session-bar row gap-3">
        <span class="cw-session-title${_session?.title ? '' : ' cw-session-title--empty'}">
          ${_session?.title ? _esc(_trunc(_session.title, 70)) : 'Session ready'}
        </span>
        ${_session?.duration != null ? `<span class="cw-session-duration">${_fmt(_session.duration)}</span>` : ''}
        <button class="cw-reset-btn" id="cw-reset">← New source</button>
      </div>
    </div>
  `;
}

/* ── Controls: intent cards ──────────────────────────────────────────── */

function _intentCards() {
  return `
    <div class="cw-intent-row">
      ${PRESETS.map(p => `
        <button class="cw-intent-card${_activePreset === p.id ? ' cw-intent-card--active' : ''}" data-preset="${p.id}">
          <span class="cw-intent-card__name">${p.label}</span>
          <span class="cw-intent-card__desc">${p.desc}</span>
        </button>
      `).join('')}
    </div>
  `;
}

/* ── Controls: options row (format + subtitle + advanced toggle) ──────── */

function _optionsRow() {
  const { draft } = draftStore.getState();
  return `
    <div class="cw-options-row row gap-0">
      <div class="cw-format-pills row gap-1">
        ${FORMATS.map(f => `
          <button class="cw-format-pill${draft.aspectRatio === f.id ? ' cw-format-pill--active' : ''}"
            data-format="${f.id}">${f.label}</button>
        `).join('')}
      </div>
      <div class="cw-options-sep"></div>
      <div class="cw-option-item row gap-2">
        <label class="studio-toggle" aria-label="Subtitles">
          <input type="checkbox" id="cw-subtitle" ${draft.subtitleEnabled ? 'checked' : ''} />
          <span class="studio-toggle__track"></span>
          <span class="studio-toggle__thumb"></span>
        </label>
        <span class="cw-option-label">Subtitles</span>
      </div>
      <div class="cw-options-sep"></div>
      <button class="cw-adv-btn" id="cw-adv-toggle">Advanced ${_advOpen ? '▲' : '▼'}</button>
    </div>
  `;
}

/* ── Controls: advanced panel ────────────────────────────────────────── */

function _advancedPanel() {
  if (!_advOpen) return '';
  const { draft } = draftStore.getState();
  return `
    <div class="cw-advanced">
      <div class="cw-advanced-inner row gap-6">
        <div class="col gap-2">
          <div class="cw-adv-label">Max clips</div>
          <div class="row gap-2" style="align-items:center">
            <input class="form-input" id="cw-max-parts" type="number"
              min="1" max="20" value="${draft.maxExportParts}"
              style="width:64px;text-align:center" />
            <span class="cw-adv-unit">clips</span>
          </div>
        </div>
        <div class="col gap-2">
          <div class="cw-adv-label">Duration range</div>
          <div class="row gap-2" style="align-items:center">
            <input class="form-input" id="cw-min-sec" type="number"
              min="5" max="600" value="${draft.minPartSec}"
              style="width:64px;text-align:center" />
            <span class="cw-adv-unit">–</span>
            <input class="form-input" id="cw-max-sec" type="number"
              min="5" max="600" value="${draft.maxPartSec}"
              style="width:64px;text-align:center" />
            <span class="cw-adv-unit">sec</span>
          </div>
        </div>
        <div class="col gap-2">
          <div class="cw-adv-label">AI Director</div>
          <label class="studio-toggle" aria-label="AI Director">
            <input type="checkbox" id="cw-ai" ${draft.aiEnabled ? 'checked' : ''} />
            <span class="studio-toggle__track"></span>
            <span class="studio-toggle__thumb"></span>
          </label>
        </div>
      </div>
    </div>
  `;
}

/* ── CTA inner content ───────────────────────────────────────────────── */

function _ctaInner() {
  if (_phase === 'import' || _phase === 'preparing') {
    const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
    const hasOutput = !!_outputDir.trim();
    const canPrepare = hasSource && hasOutput && _phase === 'import';
    return `
      ${!canPrepare && _phase === 'import' ? `
        <div class="cw-cta-hint">${!hasSource ? 'Add a video source' : 'Set an output folder'} to continue</div>
      ` : ''}
      <button class="cw-generate-btn" id="cw-prepare" ${canPrepare ? '' : 'disabled'}>
        ${_phase === 'preparing'
          ? `<span class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></span>Preparing…`
          : 'Prepare Source →'}
      </button>
    `;
  }

  const { draft } = draftStore.getState();
  const est = _clipEstimate();
  return `
    <div class="cw-cta-chips row gap-2">
      ${est != null ? `<span class="cw-chip">~${est} clip${est !== 1 ? 's' : ''}</span>` : ''}
      <span class="cw-chip">${draft.aspectRatio}</span>
      ${draft.subtitleEnabled ? `<span class="cw-chip">Subtitles</span>` : ''}
      ${draft.aiEnabled ? `<span class="cw-chip cw-chip--ai">AI Director</span>` : ''}
    </div>
    ${_error ? `<div class="cw-error">${_esc(_error)}</div>` : ''}
    <button class="cw-generate-btn" id="cw-generate" ${_generating ? 'disabled' : ''}>
      ${_generating
        ? `<span class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></span>Starting render…`
        : 'Generate Clips'}
    </button>
  `;
}

/* ── Full workspace ──────────────────────────────────────────────────── */

function _workspace() {
  const hero = _phase === 'preparing' ? _heroPreparing()
             : _phase === 'configure' ? _heroConfigure()
             : _heroImport();
  return `
    <div class="cw">
      <div class="cw-hero" id="cw-hero">${hero}</div>
      <div class="cw-controls" id="cw-controls">
        ${_intentCards()}${_optionsRow()}${_advancedPanel()}
      </div>
      <div class="cw-cta" id="cw-cta">${_ctaInner()}</div>
    </div>
  `;
}

/* ── Partial re-renders ──────────────────────────────────────────────── */

function _rerenderHero() {
  const el = _el?.querySelector('#cw-hero');
  if (!el) return;
  el.innerHTML = _phase === 'preparing' ? _heroPreparing()
               : _phase === 'configure' ? _heroConfigure()
               : _heroImport();
  _wireHero();
}

function _rerenderControls() {
  const el = _el?.querySelector('#cw-controls');
  if (!el) return;
  el.innerHTML = _intentCards() + _optionsRow() + _advancedPanel();
  _wireControls();
}

function _rerenderCTA() {
  const el = _el?.querySelector('#cw-cta');
  if (!el) return;
  el.innerHTML = _ctaInner();
  _wireCTA();
}

function _updatePrepareBtn() {
  const btn = _el?.querySelector('#cw-prepare');
  if (!btn) return;
  const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
  const hasOutput = !!_outputDir.trim();
  btn.disabled = !(hasSource && hasOutput);
}

/* ── Prepare handler ─────────────────────────────────────────────────── */

async function _handlePrepare() {
  if (_phase !== 'import') return;
  const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
  if (!hasSource || !_outputDir.trim()) return;

  _error = null;
  _phase = 'preparing';
  _rerenderHero();
  _rerenderCTA();

  draftStore.patch({
    sourceMode:      _srcMode,
    outputDir:       _outputDir.trim(),
    youtubeUrl:      _srcMode === 'youtube' ? _url.trim()      : '',
    sourceVideoPath: _srcMode === 'local'   ? _filePath.trim() : '',
  });

  try {
    const payload = {
      source_mode: _srcMode,
      output_dir:  _outputDir.trim(),
      ...(_srcMode === 'youtube'
        ? { youtube_url:        _url.trim() }
        : { source_video_path: _filePath.trim() }),
    };
    const raw  = await withTimeout(renderApi.prepareSource(payload), PREPARE_TIMEOUT_MS, 'prepare-source');
    const sess = parsePrepareSourceResponse(raw);
    if (!sess) throw new Error('Invalid response from prepare-source');

    draftStore.setSession(sess);
    _session = sess;
    _phase   = 'configure';
  } catch (err) {
    _error = String(err?.message ?? 'Preparation failed. Check the source and try again.');
    _phase = 'import';
  }

  _rerenderHero();
  _rerenderCTA();
}

/* ── Generate handler ────────────────────────────────────────────────── */

async function _handleGenerate() {
  if (_generating) return;
  _error      = null;
  _generating = true;
  _rerenderCTA();

  const { draft } = draftStore.getState();
  const errors = validateRenderDraft(draft);
  if (errors.length > 0) {
    _error      = errors[0];
    _generating = false;
    _rerenderCTA();
    return;
  }

  try {
    const payload = draftStore.buildPayload();
    const res     = await renderApi.process(payload);
    const jobId   = String(res?.job_id ?? res?.id ?? '');
    if (!jobId) throw new Error('No job ID returned from server');
    router.go(`/monitor/${jobId}`);
  } catch (err) {
    _error      = String(err?.message ?? 'Failed to start render. Check the backend is running.');
    _generating = false;
    _rerenderCTA();
  }
}

/* ── Reset handler ───────────────────────────────────────────────────── */

function _handleReset() {
  draftStore.clearSession();
  _session    = null;
  _phase      = 'import';
  _error      = null;
  _generating = false;
  _rerenderHero();
  _rerenderCTA();
}

/* ── Wire: hero ──────────────────────────────────────────────────────── */

function _wireHero() {
  const hero = _el?.querySelector('#cw-hero');
  if (!hero) return;

  hero.querySelectorAll('.cw-tab').forEach(btn =>
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      _srcMode = btn.dataset.tab;
      _error   = null;
      _rerenderHero();
      _rerenderCTA();
    })
  );

  hero.querySelector('#cw-url')?.addEventListener('input', e => {
    _url = e.target.value;
    _updatePrepareBtn();
  });

  hero.querySelector('#cw-file')?.addEventListener('input', e => {
    _filePath = e.target.value;
    _updatePrepareBtn();
  });

  hero.querySelector('#cw-browse-file')?.addEventListener('click', async () => {
    const file = await desktopAdapter.pickVideoFile();
    if (file) { _filePath = file; _rerenderHero(); }
  });

  hero.querySelector('#cw-output')?.addEventListener('input', e => {
    _outputDir = e.target.value;
    _updatePrepareBtn();
  });

  hero.querySelector('#cw-browse-dir')?.addEventListener('click', async () => {
    const dir = await desktopAdapter.pickOutputDir();
    if (dir) { _outputDir = dir; _rerenderHero(); }
  });

  hero.querySelector('#cw-reset')?.addEventListener('click', _handleReset);
}

/* ── Wire: controls ──────────────────────────────────────────────────── */

function _wireControls() {
  const ctrl = _el?.querySelector('#cw-controls');
  if (!ctrl) return;

  ctrl.querySelectorAll('.cw-intent-card').forEach(btn =>
    btn.addEventListener('click', () => {
      const preset = PRESETS.find(p => p.id === btn.dataset.preset);
      if (!preset) return;
      _activePreset = preset.id;
      draftStore.patch(preset.patch);
      _rerenderControls();
      _rerenderCTA();
    })
  );

  ctrl.querySelectorAll('.cw-format-pill').forEach(btn =>
    btn.addEventListener('click', () => {
      draftStore.patch({ aspectRatio: btn.dataset.format });
      _rerenderControls();
      _rerenderCTA();
    })
  );

  ctrl.querySelector('#cw-subtitle')?.addEventListener('change', e => {
    draftStore.patch({ subtitleEnabled: e.target.checked });
    _rerenderCTA();
  });

  ctrl.querySelector('#cw-adv-toggle')?.addEventListener('click', () => {
    _advOpen = !_advOpen;
    _rerenderControls();
  });

  ctrl.querySelector('#cw-max-parts')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 1) draftStore.patch({ maxExportParts: v });
  });
  ctrl.querySelector('#cw-min-sec')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 5) draftStore.patch({ minPartSec: v });
  });
  ctrl.querySelector('#cw-max-sec')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 5) draftStore.patch({ maxPartSec: v });
  });
  ctrl.querySelector('#cw-ai')?.addEventListener('change', e => {
    draftStore.patch({ aiEnabled: e.target.checked });
    _rerenderCTA();
  });
}

/* ── Wire: CTA ───────────────────────────────────────────────────────── */

function _wireCTA() {
  const cta = _el?.querySelector('#cw-cta');
  if (!cta) return;
  cta.querySelector('#cw-prepare')?.addEventListener('click', _handlePrepare);
  cta.querySelector('#cw-generate')?.addEventListener('click', _handleGenerate);
}

/* ── Mount ───────────────────────────────────────────────────────────── */

export async function mount(el, _params) {
  const { draft } = draftStore.getState();

  _phase        = draft.editSessionId ? 'configure' : 'import';
  _session      = draft.editSessionId
    ? { sessionId: draft.editSessionId, title: draft.sessionTitle, duration: draft.sessionDuration }
    : null;
  _srcMode      = draft.sourceMode      ?? 'youtube';
  _url          = draft.youtubeUrl      ?? '';
  _filePath     = draft.sourceVideoPath ?? '';
  _outputDir    = draft.outputDir       ?? '';
  _error        = null;
  _activePreset = 'balanced';
  _advOpen      = false;
  _generating   = false;
  _el           = el;

  el.innerHTML = _workspace();
  _wireHero();
  _wireControls();
  _wireCTA();
}

export const createScreen = { mount };
