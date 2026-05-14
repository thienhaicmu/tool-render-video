/* Create workspace (UI-R5C) — unified import + configure screen.
   State machine: import → preparing → configure
   import:    canvas = source import surface; brief = output + settings + Prepare CTA
   preparing: canvas = loading; brief frozen
   configure: canvas = video preview; brief = full settings + Generate CTA
   Never touches renderSessionStore — monitor route handles that sync.
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

/* ── Intent presets ───────────────────────────────────────────────────── */

const PRESETS = [
  { id: 'hooks',    label: 'Fast Hooks',    desc: '10–30s · up to 8',  patch: { minPartSec:10, maxPartSec:30,  maxExportParts:8, aiEnabled:true,  aiInfluenceEnabled:true  } },
  { id: 'balanced', label: 'Balanced',      desc: '20–60s · up to 5',  patch: { minPartSec:20, maxPartSec:60,  maxExportParts:5, aiEnabled:true,  aiInfluenceEnabled:false } },
  { id: 'story',    label: 'Story',         desc: '45–120s · up to 3', patch: { minPartSec:45, maxPartSec:120, maxExportParts:3, aiEnabled:false, aiInfluenceEnabled:false } },
  { id: 'full',     label: 'Full Segments', desc: '2–5 min · up to 3', patch: { minPartSec:90, maxPartSec:300, maxExportParts:3, aiEnabled:false, aiInfluenceEnabled:false } },
];

const FORMATS = [
  { id: '9:16',  label: '9:16',  note: 'Vertical'  },
  { id: '1:1',   label: '1:1',   note: 'Square'    },
  { id: '16:9',  label: '16:9',  note: 'Landscape' },
];

/* ── Module state ─────────────────────────────────────────────────────── */

let _phase        = 'import';   // 'import' | 'preparing' | 'configure'
let _srcMode      = 'youtube';
let _url          = '';
let _filePath     = '';
let _outputDir    = '';
let _error        = null;
let _session      = null;       // { sessionId, title, duration }
let _activePreset = 'balanced';
let _advOpen      = false;
let _generating   = false;
let _el           = null;

/* ── Helpers ──────────────────────────────────────────────────────────── */

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

/* ── Canvas: import surface ───────────────────────────────────────────── */

function _canvasImport() {
  const { ytdlpAvailable } = readinessStore.getState();
  const ytDisabled = ytdlpAvailable === false;
  const isYt = _srcMode === 'youtube';

  return `
    <div class="create-import-surface col gap-5">
      <div>
        <div class="create-import-title">Import your video</div>
        <div class="create-import-sub">YouTube URL or local file — we'll take it from there</div>
      </div>

      <div class="create-mode-tabs row gap-1">
        <button class="create-mode-tab${isYt ? ' create-mode-tab--active' : ''}"
          data-tab="youtube" ${ytDisabled ? 'disabled title="yt-dlp unavailable"' : ''}>YouTube</button>
        <button class="create-mode-tab${!isYt ? ' create-mode-tab--active' : ''}"
          data-tab="local">Local File</button>
      </div>

      ${isYt ? `
        <div class="col gap-2">
          <input class="create-url-input" id="cw-url" type="url"
            placeholder="https://www.youtube.com/watch?v=…"
            value="${_esc(_url)}" autocomplete="off" spellcheck="false" />
          <div class="text-caption text-faint">Standard YouTube and youtu.be links</div>
          ${ytDisabled ? `<div class="readiness-warning row gap-2"><span aria-hidden="true">⚠</span><span class="text-caption">yt-dlp unavailable — use Local File instead</span></div>` : ''}
        </div>
      ` : `
        <div class="col gap-2">
          <div class="row gap-2">
            <input class="create-url-input flex-1" id="cw-file" type="text"
              placeholder="Paste video file path…"
              value="${_esc(_filePath)}" autocomplete="off" />
            ${desktopAdapter.filePickerAvailable
              ? `<button class="btn btn-secondary" id="cw-browse-file">Browse…</button>`
              : ''}
          </div>
          <div class="text-caption text-faint">
            ${desktopAdapter.filePickerAvailable
              ? 'MP4, MOV, MKV — must be readable by the backend server.'
              : 'Paste a local file path the backend server can read.'}
          </div>
        </div>
      `}

      ${_error ? `<div class="create-error-card">${_esc(_error)}</div>` : ''}
    </div>
  `;
}

/* ── Canvas: preparing ────────────────────────────────────────────────── */

function _canvasPreparing() {
  return `
    <div class="create-loading col gap-4">
      <div class="spinner" style="width:36px;height:36px;border-width:3px"></div>
      <div>
        <div class="text-body" style="font-weight:600;margin-bottom:4px">Preparing source…</div>
        <div class="text-caption text-faint">This may take up to a minute for YouTube videos</div>
      </div>
    </div>
  `;
}

/* ── Canvas: configure (preview) ──────────────────────────────────────── */

function _canvasConfigure() {
  const previewUrl = _session?.sessionId
    ? renderApi.getPreviewVideoUrl(_session.sessionId)
    : null;

  return `
    <div class="create-preview col gap-0">
      ${previewUrl ? `
        <video class="create-preview__video" src="${_esc(previewUrl)}"
          controls muted playsinline preload="metadata"></video>
      ` : `
        <div class="create-preview--idle">
          <div style="font-size:40px;opacity:0.12" aria-hidden="true">▶</div>
          <div class="text-caption text-faint">No preview available</div>
        </div>
      `}
      <div class="create-session-bar row gap-3">
        ${_session?.title
          ? `<span class="text-body" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${_esc(_trunc(_session.title, 60))}</span>`
          : `<span class="flex-1 text-caption text-faint">Session ready</span>`}
        ${_session?.duration != null ? `<span class="text-caption text-faint">${_fmt(_session.duration)}</span>` : ''}
        <button class="btn btn-ghost btn-sm" id="cw-reset">← New source</button>
      </div>
    </div>
  `;
}

/* ── Brief: output folder ─────────────────────────────────────────────── */

function _briefOutputFolder() {
  return `
    <div class="col gap-2">
      <div class="create-brief-section-label">Output folder</div>
      <div class="row gap-2">
        <input class="form-input flex-1" id="cw-output" type="text"
          placeholder="Paste output path…"
          value="${_esc(_outputDir)}" />
        ${desktopAdapter.folderPickerAvailable
          ? `<button class="btn btn-secondary btn-sm" id="cw-browse-dir">Browse…</button>`
          : ''}
      </div>
      ${!_outputDir ? `<div class="text-caption text-faint">Required — where clips will be saved</div>` : ''}
    </div>
  `;
}

/* ── Brief: intent presets ────────────────────────────────────────────── */

function _briefIntent() {
  return `
    <div class="col gap-2">
      <div class="create-brief-section-label">Intent</div>
      <div class="intent-grid">
        ${PRESETS.map(p => `
          <button class="intent-pill${_activePreset === p.id ? ' intent-pill--active' : ''}" data-preset="${p.id}">
            <span class="intent-pill__label">${p.label}</span>
            <span class="intent-pill__desc">${p.desc}</span>
          </button>
        `).join('')}
      </div>
    </div>
  `;
}

/* ── Brief: format pills ──────────────────────────────────────────────── */

function _briefFormat() {
  const { draft } = draftStore.getState();
  return `
    <div class="col gap-2">
      <div class="create-brief-section-label">Format</div>
      <div class="format-pills row gap-1">
        ${FORMATS.map(f => `
          <button class="format-pill${draft.aspectRatio === f.id ? ' format-pill--active' : ''}" data-format="${f.id}">
            <div style="font-weight:600;font-size:12px">${f.label}</div>
            <div class="text-caption text-faint" style="font-size:10px">${f.note}</div>
          </button>
        `).join('')}
      </div>
    </div>
  `;
}

/* ── Brief: subtitle ──────────────────────────────────────────────────── */

function _briefSubtitle() {
  const { draft } = draftStore.getState();
  return `
    <div class="row gap-3" style="align-items:center">
      <div class="col gap-0 flex-1">
        <div class="create-brief-section-label" style="margin-bottom:0">Subtitles</div>
        <div class="text-caption text-faint">Auto-generated captions</div>
      </div>
      <label class="studio-toggle" aria-label="Subtitles">
        <input type="checkbox" id="cw-subtitle" ${draft.subtitleEnabled ? 'checked' : ''} />
        <span class="studio-toggle__track"><span class="studio-toggle__thumb"></span></span>
      </label>
    </div>
  `;
}

/* ── Brief: advanced settings ─────────────────────────────────────────── */

function _briefAdvanced() {
  const { draft } = draftStore.getState();
  return `
    <div class="col gap-0">
      <button class="create-advanced-toggle" id="cw-adv-toggle">
        <span class="text-caption" style="font-weight:600;color:var(--color-text-muted)">Advanced</span>
        <span class="flex-1"></span>
        <span class="create-advanced-arrow">${_advOpen ? '⌄' : '›'}</span>
      </button>
      <div class="create-advanced-body" ${_advOpen ? '' : 'hidden'}>
        <div class="col gap-4" style="padding-top:var(--sp-3)">
          <div class="col gap-2">
            <div class="create-brief-section-label">Max clips</div>
            <div class="row gap-2" style="align-items:center">
              <input class="form-input" id="cw-max-parts" type="number"
                min="1" max="20" value="${draft.maxExportParts}"
                style="width:68px;text-align:center" />
              <span class="text-caption text-faint">clips maximum</span>
            </div>
          </div>
          <div class="col gap-2">
            <div class="create-brief-section-label">Clip duration</div>
            <div class="row gap-2" style="align-items:center">
              <input class="form-input" id="cw-min-sec" type="number"
                min="5" max="600" value="${draft.minPartSec}"
                style="width:68px;text-align:center" />
              <span class="text-caption text-faint">–</span>
              <input class="form-input" id="cw-max-sec" type="number"
                min="5" max="600" value="${draft.maxPartSec}"
                style="width:68px;text-align:center" />
              <span class="text-caption text-faint">sec</span>
            </div>
          </div>
          <div class="row gap-3" style="align-items:center">
            <div class="col gap-0 flex-1">
              <div class="create-brief-section-label" style="margin-bottom:0">AI Director</div>
              <div class="text-caption text-faint">Smart scene scoring</div>
            </div>
            <label class="studio-toggle" aria-label="AI Director">
              <input type="checkbox" id="cw-ai" ${draft.aiEnabled ? 'checked' : ''} />
              <span class="studio-toggle__track"><span class="studio-toggle__thumb"></span></span>
            </label>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ── Brief: CTA zone ──────────────────────────────────────────────────── */

function _briefCTA() {
  if (_phase === 'import' || _phase === 'preparing') {
    const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
    const hasOutput = !!_outputDir.trim();
    const canPrepare = hasSource && hasOutput && _phase === 'import';
    return `
      <div class="create-generate col gap-2">
        ${_phase === 'import' && !hasSource
          ? `<div class="text-caption text-faint" style="text-align:center">Add a video source to continue</div>`
          : _phase === 'import' && !hasOutput
            ? `<div class="text-caption text-faint" style="text-align:center">Set an output folder to continue</div>`
            : ''}
        <button class="btn-generate" id="cw-prepare" ${canPrepare ? '' : 'disabled'}>
          ${_phase === 'preparing'
            ? `<span class="spinner" style="width:15px;height:15px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Preparing…`
            : 'Prepare Source →'}
        </button>
      </div>
    `;
  }

  const { draft } = draftStore.getState();
  const est = _clipEstimate();
  return `
    <div class="create-generate col gap-2">
      <div class="create-summary">
        ${est != null ? `<span class="create-summary-chip">~${est} clip${est !== 1 ? 's' : ''}</span>` : ''}
        <span class="create-summary-chip">${draft.aspectRatio}</span>
        ${draft.subtitleEnabled ? `<span class="create-summary-chip">Subtitles</span>` : ''}
        ${draft.aiEnabled ? `<span class="create-summary-chip">AI on</span>` : ''}
      </div>
      ${_error ? `<div class="create-error-card" style="margin-bottom:var(--sp-2)">${_esc(_error)}</div>` : ''}
      <button class="btn-generate" id="cw-generate" ${_generating ? 'disabled' : ''}>
        ${_generating
          ? `<span class="spinner" style="width:15px;height:15px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Starting…`
          : 'Generate Clips'}
      </button>
    </div>
  `;
}

/* ── Brief panel ──────────────────────────────────────────────────────── */

function _briefPanel() {
  return `
    <div class="create-brief col gap-0">
      <div class="create-brief__scroll col gap-5">
        ${_phase !== 'configure' ? _briefOutputFolder() : ''}
        ${_briefIntent()}
        ${_briefFormat()}
        ${_briefSubtitle()}
        ${_briefAdvanced()}
      </div>
      ${_briefCTA()}
    </div>
  `;
}

/* ── Full workspace ───────────────────────────────────────────────────── */

function _workspace() {
  const canvas = _phase === 'preparing' ? _canvasPreparing()
               : _phase === 'configure' ? _canvasConfigure()
               : _canvasImport();
  return `
    <div class="create-workspace">
      <div class="create-canvas" id="cw-canvas">${canvas}</div>
      <div class="create-brief-wrapper" id="cw-brief">${_briefPanel()}</div>
    </div>
  `;
}

/* ── Partial re-renders ───────────────────────────────────────────────── */

function _rerenderCanvas() {
  const cv = _el?.querySelector('#cw-canvas');
  if (!cv) return;
  cv.innerHTML = _phase === 'preparing' ? _canvasPreparing()
               : _phase === 'configure' ? _canvasConfigure()
               : _canvasImport();
  _wireCanvas();
}

function _rerenderBrief() {
  const wrap = _el?.querySelector('#cw-brief');
  if (!wrap) return;
  wrap.innerHTML = _briefPanel();
  _wireBrief();
}

function _updatePrepareBtn() {
  const btn = _el?.querySelector('#cw-prepare');
  if (!btn) return;
  const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
  const hasOutput = !!_outputDir.trim();
  btn.disabled = !(hasSource && hasOutput);
}

/* ── Prepare handler ──────────────────────────────────────────────────── */

async function _handlePrepare() {
  if (_phase !== 'import') return;
  const hasSource = _srcMode === 'youtube' ? !!_url.trim() : !!_filePath.trim();
  if (!hasSource || !_outputDir.trim()) return;

  _error = null;
  _phase = 'preparing';
  _rerenderCanvas();
  _rerenderBrief();

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

  _rerenderCanvas();
  _rerenderBrief();
}

/* ── Generate handler ─────────────────────────────────────────────────── */

async function _handleGenerate() {
  if (_generating) return;
  _error      = null;
  _generating = true;
  _rerenderBrief();

  const { draft } = draftStore.getState();
  const errors = validateRenderDraft(draft);
  if (errors.length > 0) {
    _error      = errors[0];
    _generating = false;
    _rerenderBrief();
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
    _rerenderBrief();
  }
}

/* ── Reset handler ────────────────────────────────────────────────────── */

function _handleReset() {
  draftStore.clearSession();
  _session    = null;
  _phase      = 'import';
  _error      = null;
  _generating = false;
  _rerenderCanvas();
  _rerenderBrief();
}

/* ── Canvas wiring ────────────────────────────────────────────────────── */

function _wireCanvas() {
  const cv = _el?.querySelector('#cw-canvas');
  if (!cv) return;

  cv.querySelectorAll('.create-mode-tab').forEach(btn =>
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      _srcMode = btn.dataset.tab;
      _error   = null;
      _rerenderCanvas();
    })
  );

  cv.querySelector('#cw-url')?.addEventListener('input', e => {
    _url = e.target.value;
    _updatePrepareBtn();
  });

  cv.querySelector('#cw-file')?.addEventListener('input', e => {
    _filePath = e.target.value;
    _updatePrepareBtn();
  });

  cv.querySelector('#cw-browse-file')?.addEventListener('click', async () => {
    const file = await desktopAdapter.pickVideoFile();
    if (file) { _filePath = file; _rerenderCanvas(); }
  });

  cv.querySelector('#cw-reset')?.addEventListener('click', _handleReset);
}

/* ── Brief wiring ─────────────────────────────────────────────────────── */

function _wireBrief() {
  const br = _el?.querySelector('#cw-brief');
  if (!br) return;

  br.querySelector('#cw-output')?.addEventListener('input', e => {
    _outputDir = e.target.value;
    _updatePrepareBtn();
  });

  br.querySelector('#cw-browse-dir')?.addEventListener('click', async () => {
    const dir = await desktopAdapter.pickOutputDir();
    if (dir) { _outputDir = dir; _rerenderBrief(); }
  });

  br.querySelectorAll('.intent-pill').forEach(btn =>
    btn.addEventListener('click', () => {
      const preset = PRESETS.find(p => p.id === btn.dataset.preset);
      if (!preset) return;
      _activePreset = preset.id;
      draftStore.patch(preset.patch);
      _rerenderBrief();
    })
  );

  br.querySelectorAll('.format-pill').forEach(btn =>
    btn.addEventListener('click', () => {
      draftStore.patch({ aspectRatio: btn.dataset.format });
      _rerenderBrief();
    })
  );

  br.querySelector('#cw-subtitle')?.addEventListener('change', e => {
    draftStore.patch({ subtitleEnabled: e.target.checked });
    _rerenderBrief();
  });

  br.querySelector('#cw-adv-toggle')?.addEventListener('click', () => {
    _advOpen = !_advOpen;
    const body  = br.querySelector('.create-advanced-body');
    const arrow = br.querySelector('.create-advanced-arrow');
    if (body)  body.hidden      = !_advOpen;
    if (arrow) arrow.textContent = _advOpen ? '⌄' : '›';
  });

  br.querySelector('#cw-max-parts')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 1) draftStore.patch({ maxExportParts: v });
  });
  br.querySelector('#cw-min-sec')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 5) draftStore.patch({ minPartSec: v });
  });
  br.querySelector('#cw-max-sec')?.addEventListener('change', e => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 5) draftStore.patch({ maxPartSec: v });
  });
  br.querySelector('#cw-ai')?.addEventListener('change', e => {
    draftStore.patch({ aiEnabled: e.target.checked });
    _rerenderBrief();
  });

  br.querySelector('#cw-prepare')?.addEventListener('click', _handlePrepare);
  br.querySelector('#cw-generate')?.addEventListener('click', _handleGenerate);
}

/* ── Mount ────────────────────────────────────────────────────────────── */

export async function mount(el, _params) {
  const { draft } = draftStore.getState();

  _phase     = draft.editSessionId ? 'configure' : 'import';
  _session   = draft.editSessionId
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
  _wireCanvas();
  _wireBrief();
}

export const createScreen = { mount };
