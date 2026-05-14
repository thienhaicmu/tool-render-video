/* Source screen — YouTube or local file → POST /api/render/prepare-source → Studio */

import { renderApi }                from '../api/render.js';
import { draftStore }               from '../store/draft.js';
import { desktopAdapter }           from '../desktop-adapter.js';
import { router }                   from '../router.js';
import { parsePrepareSourceResponse } from '../entities/source-session.js';
import { readinessStore }           from '../store/readiness.js';
import { withTimeout }              from '../transport.js';

const PREPARE_TIMEOUT_MS = 45_000;

// Module-level UI state (resets on each mount)
let _s = {};

function initState() {
  const { draft } = draftStore.getState();
  _s = {
    mode:       'idle',           // idle | loading | success | error
    sourceMode: draft.sourceMode ?? 'youtube',
    youtubeUrl: draft.youtubeUrl ?? '',
    localPath:  draft.sourceVideoPath ?? '',
    outputDir:  draft.outputDir ?? '',
    error:      null,
    session:    null,
  };
}

function fmt(sec) {
  if (sec == null) return '';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

/* ── Readiness warnings ───────────────────────────────────────────── */

function renderReadinessWarnings() {
  const { ytdlpAvailable } = readinessStore.getState();
  if (_s.sourceMode !== 'youtube') return '';
  if (ytdlpAvailable === false) {
    return `
      <div class="readiness-warning row gap-2">
        <span aria-hidden="true">⚠</span>
        <span class="text-caption">yt-dlp is unavailable, so YouTube downloads are disabled. Use a local file instead.</span>
      </div>
    `;
  }
  return '';
}

/* ── Sub-renders ──────────────────────────────────────────────────── */

function renderSourceTabs() {
  const { ytdlpAvailable } = readinessStore.getState();
  const ytDisabled = ytdlpAvailable === false;
  return `
    <div class="source-tabs row gap-1">
      <button class="source-tab btn ${_s.sourceMode === 'youtube' ? 'source-tab--active btn-primary' : 'btn-ghost'}"
        data-mode="youtube" ${ytDisabled ? 'disabled title="yt-dlp is unavailable"' : ''}>
        YouTube
      </button>
      <button class="source-tab btn ${_s.sourceMode === 'local' ? 'source-tab--active btn-primary' : 'btn-ghost'}" data-mode="local">
        Local File
      </button>
    </div>
  `;
}

function renderYouTubeInput() {
  return `
    <div class="form-field">
      <label class="form-label">YouTube URL</label>
      <input class="form-input" id="src-yt-url" type="url"
        placeholder="https://www.youtube.com/watch?v=…"
        value="${_esc(_s.youtubeUrl)}" autocomplete="off" />
      <div class="text-caption text-faint mt-2">Standard YouTube and youtu.be links supported.</div>
    </div>
  `;
}

function renderLocalInput() {
  const hasPath = !!_s.localPath;
  const pickerAvailable = desktopAdapter.filePickerAvailable;
  return `
    <div class="form-field">
      <label class="form-label">Video file</label>
      ${hasPath ? `
        <div class="path-chip row gap-2">
          <span class="path-chip__icon" aria-hidden="true">&#127910;</span>
          <span class="path-chip__text text-caption" title="${_esc(_s.localPath)}">${_esc(_truncatePath(_s.localPath, 52))}</span>
          <button class="path-chip__clear" id="src-local-clear" aria-label="Clear selected file">&times;</button>
        </div>
      ` : ''}
      <div class="row gap-2">
        <input class="form-input flex-1" id="src-local-path" type="text"
          placeholder="${pickerAvailable ? '/path/to/video.mp4' : 'Paste file path here…'}"
          value="${_esc(_s.localPath)}" autocomplete="off" />
        ${pickerAvailable
          ? `<button class="btn btn-secondary" id="src-browse-btn">Browse…</button>`
          : ''}
      </div>
      <div class="text-caption text-faint mt-2">
        ${pickerAvailable
          ? 'MP4, MOV, MKV and other formats — must be a path readable by the backend.'
          : 'Browse is available in desktop mode. Paste a local file path here.'}
      </div>
    </div>
  `;
}

function renderOutputDir() {
  const hasDir = !!_s.outputDir;
  const pickerAvailable = desktopAdapter.folderPickerAvailable;
  return `
    <div class="form-field">
      <label class="form-label">Output folder</label>
      ${hasDir ? `
        <div class="path-chip row gap-2">
          <span class="path-chip__icon" aria-hidden="true">&#128193;</span>
          <span class="path-chip__text text-caption" title="${_esc(_s.outputDir)}">${_esc(_truncatePath(_s.outputDir, 52))}</span>
          <button class="path-chip__clear" id="src-output-clear" aria-label="Clear selected folder">&times;</button>
        </div>
      ` : ''}
      <div class="row gap-2">
        <input class="form-input flex-1" id="src-output-dir" type="text"
          placeholder="${pickerAvailable ? 'Choose a folder…' : 'Paste output folder path here…'}"
          value="${_esc(_s.outputDir)}" />
        ${pickerAvailable
          ? `<button class="btn btn-secondary" id="src-pick-output-btn">Browse…</button>`
          : ''}
      </div>
      ${!pickerAvailable
        ? `<div class="text-caption text-faint mt-2">Browse is available in desktop mode. Paste an output folder path here.</div>`
        : ''}
    </div>
  `;
}

function renderReadinessSummary(hasSource, hasOutput) {
  const { loaded: backendOk } = readinessStore.getState();
  const item = (ok, label) =>
    `<div class="row gap-2" style="align-items:center">
      <span style="font-size:11px;line-height:1;color:${ok ? 'var(--color-success,#22c55e)' : 'var(--color-text-faint,#64748b)'}">${ok ? '✓' : '○'}</span>
      <span class="text-caption" style="color:${ok ? 'var(--color-text-muted,#94a3b8)' : 'var(--color-text-faint,#64748b)'}">${label}</span>
    </div>`;
  return `
    <div class="col gap-1" style="border-top:1px solid var(--color-border,rgba(255,255,255,.08));padding-top:var(--sp-3)">
      ${item(hasSource, _s.sourceMode === 'youtube' ? 'YouTube URL entered' : 'Video file selected')}
      ${item(hasOutput, 'Output folder set')}
      ${item(!!backendOk, 'Backend reachable')}
    </div>
  `;
}

function renderForm() {
  const loading = _s.mode === 'loading';
  const hasSource = _s.sourceMode === 'youtube' ? !!_s.youtubeUrl.trim() : !!_s.localPath.trim();
  const hasOutput = !!_s.outputDir.trim();
  const allReady  = hasSource && hasOutput;
  return `
    <div class="col gap-4 source-form">
      ${renderSourceTabs()}
      ${renderReadinessWarnings()}
      ${_s.sourceMode === 'youtube' ? renderYouTubeInput() : renderLocalInput()}
      ${renderOutputDir()}
      ${renderReadinessSummary(hasSource, hasOutput)}
      <div id="src-error-area">
        ${_s.error ? _errorCard(_s.error) : ''}
      </div>
      <button class="btn btn-primary" id="src-prepare-btn"
        ${loading ? 'disabled' : ''} style="width:100%">
        ${loading
          ? '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span>&nbsp;Preparing…'
          : 'Prepare source →'}
      </button>
      <div class="text-caption text-faint" style="text-align:center">
        ${loading
          ? 'This may take up to a minute for YouTube videos.'
          : allReady
            ? 'Ready — click to validate and open Studio.'
            : 'Complete the fields above, then prepare your source.'}
      </div>
    </div>
  `;
}

function renderReadyPanel() {
  const s = _s.session;
  return `
    <div class="card source-ready-card" style="border-color:var(--color-accent)">
      <div class="row gap-2" style="align-items:center;margin-bottom:var(--sp-3)">
        <span style="color:var(--color-accent);font-size:18px">✓</span>
        <span class="text-section">Source ready</span>
      </div>
      <div class="col gap-2">
        ${s.title ? `<div class="row gap-3"><span class="text-caption text-faint" style="min-width:64px">Title</span><span class="text-body" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(s.title)}</span></div>` : ''}
        ${s.duration != null ? `<div class="row gap-3"><span class="text-caption text-faint" style="min-width:64px">Duration</span><span class="text-body">${fmt(s.duration)}</span></div>` : ''}
        <div class="row gap-3"><span class="text-caption text-faint" style="min-width:64px">Session</span><span class="text-caption" style="font-family:monospace;color:var(--color-text-muted)">${s.sessionId.slice(0, 16)}…</span></div>
      </div>
      <button class="btn btn-primary" id="src-go-studio-btn" style="margin-top:var(--sp-5);width:100%">
        Continue to Studio →
      </button>
    </div>
  `;
}

function renderInfoPanel() {
  return `
    <div class="col gap-4">
      <div class="text-section">What happens next</div>
      <div class="card card--raised col gap-4">
        <div class="row gap-3">
          <span style="color:var(--color-accent);font-weight:700;font-size:15px">①</span>
          <div>
            <div class="text-body" style="font-weight:600">Source validation</div>
            <div class="text-caption text-faint mt-1">URL or path is probed for duration, title, and viability.</div>
          </div>
        </div>
        <div class="row gap-3">
          <span style="color:var(--color-accent);font-weight:700;font-size:15px">②</span>
          <div>
            <div class="text-body" style="font-weight:600">Preview preparation</div>
            <div class="text-caption text-faint mt-1">A browser-safe preview is generated for Studio playback.</div>
          </div>
        </div>
        <div class="row gap-3">
          <span style="color:var(--color-accent);font-weight:700;font-size:15px">③</span>
          <div>
            <div class="text-body" style="font-weight:600">Studio opens</div>
            <div class="text-caption text-faint mt-1">Configure clips, subtitles, camera, and AI, then start the render.</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderScreen() {
  return `
    <div class="screen__header">
      <div class="screen__title">Source</div>
      <div class="screen__subtitle">Import a video to begin</div>
    </div>
    <div class="screen__body">
      <div class="source-layout row gap-8">
        <div class="col gap-4 source-layout__main" id="src-form-col">
          ${renderForm()}
        </div>
        <div class="source-layout__panel" id="src-panel-col">
          ${_s.mode === 'success' && _s.session ? renderReadyPanel() : renderInfoPanel()}
        </div>
      </div>
    </div>
  `;
}

/* ── Event wiring ─────────────────────────────────────────────────── */

function wireAll(el) {
  // Mode tabs
  el.querySelectorAll('.source-tab').forEach(btn =>
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      _s.sourceMode = btn.dataset.mode;
      _s.error = null;
      rerenderForm(el);
    })
  );

  // YouTube URL
  el.querySelector('#src-yt-url')?.addEventListener('input', e => { _s.youtubeUrl = e.target.value; });

  // Local path
  el.querySelector('#src-local-path')?.addEventListener('input', e => { _s.localPath = e.target.value; });

  // Desktop pickers
  el.querySelector('#src-browse-btn')?.addEventListener('click', async () => {
    const file = await desktopAdapter.pickVideoFile();
    if (file) {
      _s.localPath = file;
      rerenderForm(el);
    }
  });
  el.querySelector('#src-pick-output-btn')?.addEventListener('click', async () => {
    const dir = await desktopAdapter.pickOutputDir();
    if (dir) {
      _s.outputDir = dir;
      rerenderForm(el);
    }
  });

  // Clear buttons
  el.querySelector('#src-local-clear')?.addEventListener('click', () => {
    _s.localPath = '';
    rerenderForm(el);
  });
  el.querySelector('#src-output-clear')?.addEventListener('click', () => {
    _s.outputDir = '';
    rerenderForm(el);
  });

  // Output dir input
  el.querySelector('#src-output-dir')?.addEventListener('input', e => { _s.outputDir = e.target.value; });

  // Prepare CTA
  el.querySelector('#src-prepare-btn')?.addEventListener('click', () => handlePrepare(el));

  // Go to Studio (after success)
  el.querySelector('#src-go-studio-btn')?.addEventListener('click', () => router.go('/studio'));
}

function rerenderForm(el) {
  const col = el.querySelector('#src-form-col');
  if (col) col.innerHTML = renderForm();
  const panel = el.querySelector('#src-panel-col');
  if (panel) panel.innerHTML = _s.mode === 'success' && _s.session ? renderReadyPanel() : renderInfoPanel();
  wireAll(el);
}

async function handlePrepare(el) {
  _s.outputDir   = (el.querySelector('#src-output-dir')?.value  ?? _s.outputDir).trim();
  _s.youtubeUrl  = (el.querySelector('#src-yt-url')?.value      ?? _s.youtubeUrl).trim();
  _s.localPath   = (el.querySelector('#src-local-path')?.value  ?? _s.localPath).trim();

  if (_s.sourceMode === 'youtube') {
    if (!_s.youtubeUrl) { _s.error = 'YouTube URL is required.'; rerenderForm(el); return; }
    const isYtUrl = _s.youtubeUrl.startsWith('http') &&
      (_s.youtubeUrl.includes('youtube.com') || _s.youtubeUrl.includes('youtu.be'));
    if (!isYtUrl) { _s.error = 'Enter a valid YouTube URL (youtube.com or youtu.be).'; rerenderForm(el); return; }
  } else {
    if (!_s.localPath) { _s.error = 'Select a video file to continue.'; rerenderForm(el); return; }
  }
  if (!_s.outputDir) { _s.error = 'Output directory is required.'; rerenderForm(el); return; }

  _s.mode  = 'loading';
  _s.error = null;
  rerenderForm(el);

  try {
    const payload = { source_mode: _s.sourceMode };
    if (_s.sourceMode === 'youtube') payload.youtube_url      = _s.youtubeUrl;
    else                              payload.source_video_path = _s.localPath;

    const raw     = await withTimeout(
      renderApi.prepareSource(payload),
      PREPARE_TIMEOUT_MS,
      'Source preparation'
    );
    const session = parsePrepareSourceResponse(raw);
    if (!session) throw new Error('Invalid response from prepare-source.');

    draftStore.setSession(session);
    draftStore.patch({
      outputDir:       _s.outputDir,
      sourceMode:      _s.sourceMode,
      youtubeUrl:      _s.sourceMode === 'youtube' ? _s.youtubeUrl : '',
      sourceVideoPath: _s.sourceMode === 'local'   ? _s.localPath  : '',
    });

    _s.mode    = 'success';
    _s.session = session;
    rerenderForm(el);
  } catch (err) {
    _s.mode  = 'error';
    _s.error = err.message ?? 'Preparation failed. Try again.';
    rerenderForm(el);
  }
}

/* ── Mount ────────────────────────────────────────────────────────── */

export async function mount(el) {
  initState();
  el.innerHTML = renderScreen();
  wireAll(el);
}

export const sourceScreen = { mount };

/* ── Helpers ──────────────────────────────────────────────────────── */
function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

function _truncatePath(p, max) {
  if (!p || p.length <= max) return p;
  const sep = p.includes('/') ? '/' : '\\';
  const parts = p.split(sep);
  const name = parts[parts.length - 1];
  if (name.length >= max - 5) return '…' + name.slice(-(max - 1));
  const keep = max - name.length - 4;
  return p.slice(0, keep) + '…' + sep + name;
}

function _errorCard(msg) {
  return `
    <div class="card" style="border-color:var(--color-failed);padding:var(--sp-3) var(--sp-4)">
      <div class="row gap-2">
        <span style="color:var(--color-failed);flex-shrink:0">✗</span>
        <div class="text-body" style="color:var(--color-text-muted)">${_esc(msg)}</div>
      </div>
    </div>
  `;
}
