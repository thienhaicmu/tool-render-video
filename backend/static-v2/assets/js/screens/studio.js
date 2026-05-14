/* Studio screen — preview prepared source → configure RenderDraft → POST /api/render/process */

import { draftStore }          from '../store/draft.js';
import { renderApi }           from '../api/render.js';
import { router }              from '../router.js';
import { validateRenderDraft } from '../entities/render-request.js';
import { emptyState, ICONS }   from '../components/empty-state.js';
import { readinessStore }      from '../store/readiness.js';
import { withTimeout }         from '../transport.js';

const RENDER_TIMEOUT_MS = 30_000;

const ASPECT_RATIOS = [
  { value: '9:16', label: '9:16' },
  { value: '1:1',  label: '1:1'  },
  { value: '3:4',  label: '3:4'  },
  { value: '16:9', label: '16:9' },
];

const SUBTITLE_PRESETS = [
  { value: 'viral_bold',    label: 'Viral Bold'    },
  { value: 'clean_pro',     label: 'Clean Pro'     },
  { value: 'boxed_caption', label: 'Boxed Caption' },
];

const CAMERA_MODES = [
  { value: 'center',  label: 'Center',  desc: 'Locked center crop'   },
  { value: 'motion',  label: 'Motion',  desc: 'Motion-aware reframe'  },
  { value: 'subject', label: 'Subject', desc: 'Subject-tracking crop' },
];

const EXEC_MODES = [
  { value: 'off',        label: 'Off'        },
  { value: 'safe',       label: 'Safe'       },
  { value: 'balanced',   label: 'Balanced'   },
  { value: 'aggressive', label: 'Aggressive' },
];

let _submitting  = false;
let _submitError = null;

/* ── Preview ──────────────────────────────────────────────────────── */

function renderPreviewArea(sessionId) {
  if (!sessionId) {
    return `
      <div class="studio-preview studio-preview--empty col"
           style="align-items:center;justify-content:center;gap:var(--sp-4);text-align:center;padding:var(--sp-8)">
        <div style="opacity:0.2;color:var(--color-text-muted);width:52px;height:52px">${ICONS.video}</div>
        <div class="text-section" style="color:var(--color-text-muted)">No source loaded</div>
        <div class="text-body text-faint" style="max-width:220px;line-height:1.6">
          Prepare a video in Source, then return here to set up your render.
        </div>
        <button class="btn btn-secondary" id="studio-no-source-btn">← Back to Source</button>
      </div>
    `;
  }
  const url = renderApi.getPreviewVideoUrl(sessionId);
  return `
    <div class="studio-preview">
      <video id="studio-video" class="studio-video"
        src="${url}" controls muted preload="metadata"
        style="width:100%;height:100%;object-fit:contain;border-radius:var(--radius-panel);background:#000">
      </video>
      <div id="studio-video-loading" class="studio-video-err">
        <div class="col gap-3" style="align-items:center">
          <div class="spinner" style="width:22px;height:22px;border-width:2px"></div>
          <div class="text-body" style="color:var(--color-text-muted)">Loading preview</div>
          <div class="text-caption text-faint" style="max-width:200px;text-align:center;line-height:1.5">
            Set up your render while this loads.
          </div>
        </div>
      </div>
      <div id="studio-video-err" class="studio-video-err" style="display:none">
        <div class="col gap-3" style="align-items:center">
          <div class="text-body" style="color:var(--color-text-muted)">Preview unavailable</div>
          <div class="text-caption text-faint" style="max-width:200px;text-align:center;line-height:1.5">
            Your render will still work — preview is optional.
          </div>
          <button class="btn btn-ghost btn-sm" id="studio-video-retry">Try again</button>
        </div>
      </div>
    </div>
  `;
}

/* ── Draft section renderers ──────────────────────────────────────── */

function renderSectionA(d) {
  return `
    <div class="draft-section">
      <div class="draft-section__title">Clip Strategy</div>
      <div class="col gap-4">
        <div class="row gap-2">
          <div class="form-field flex-1">
            <label class="form-label">Min</label>
            <div class="studio-num-wrap">
              <input class="form-input studio-number-input" id="d-min"
                type="number" min="5" max="300" value="${d.minPartSec}" />
              <span class="studio-num-unit">s</span>
            </div>
          </div>
          <div class="form-field flex-1">
            <label class="form-label">Max</label>
            <div class="studio-num-wrap">
              <input class="form-input studio-number-input" id="d-max"
                type="number" min="10" max="300" value="${d.maxPartSec}" />
              <span class="studio-num-unit">s</span>
            </div>
          </div>
          <div class="form-field flex-1">
            <label class="form-label">Count</label>
            <input class="form-input studio-number-input" id="d-qty"
              type="number" min="1" max="20" value="${d.maxExportParts}" />
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">Format</label>
          <div class="row gap-2" style="flex-wrap:wrap">
            ${ASPECT_RATIOS.map(r => `
              <button class="ratio-pill ${d.aspectRatio === r.value ? 'ratio-pill--active' : ''}"
                data-ratio="${r.value}">${r.label}</button>
            `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderSectionB(d) {
  const on = d.subtitleEnabled;
  return `
    <div class="draft-section">
      <div class="draft-section__title row gap-3" style="align-items:center">
        <span>Subtitles</span>
        <label class="studio-toggle" style="margin-left:auto"
               title="${on ? 'Disable' : 'Enable'} subtitles">
          <input type="checkbox" id="d-sub-on" ${on ? 'checked' : ''} />
          <span class="studio-toggle__track"></span>
          <span class="studio-toggle__thumb"></span>
        </label>
      </div>
      <div class="col gap-3 ${on ? '' : 'section-disabled'}">
        <div class="form-field">
          <label class="form-label">Caption style</label>
          <div class="row gap-2">
            ${SUBTITLE_PRESETS.map(p => `
              <button class="preset-pill ${d.subtitleStyle === p.value ? 'preset-pill--active' : ''} ${on ? '' : 'btn-ghost'}"
                data-preset="${p.value}" ${on ? '' : 'disabled'}>${p.label}</button>
            `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderSectionC(d) {
  return `
    <div class="draft-section">
      <div class="draft-section__title">Camera</div>
      <div class="col gap-2">
        ${CAMERA_MODES.map(m => `
          <label class="camera-option ${d.reframeMode === m.value ? 'camera-option--active' : ''}">
            <input type="radio" name="d-reframe" value="${m.value}"
              ${d.reframeMode === m.value ? 'checked' : ''} class="studio-radio" />
            <div class="flex-1">
              <div class="text-body" style="font-weight:600">${m.label}</div>
              <div class="text-caption text-faint">${m.desc}</div>
            </div>
          </label>
        `).join('')}
      </div>
    </div>
  `;
}

function renderSectionD(d) {
  const on = d.aiEnabled;
  return `
    <div class="draft-section">
      <div class="draft-section__title row gap-3" style="align-items:center">
        <span>AI Guidance</span>
        <label class="studio-toggle" style="margin-left:auto"
               title="${on ? 'Disable' : 'Enable'} AI guidance">
          <input type="checkbox" id="d-ai-on" ${on ? 'checked' : ''} />
          <span class="studio-toggle__track"></span>
          <span class="studio-toggle__thumb"></span>
        </label>
      </div>
      <div class="col gap-3 ${on ? '' : 'section-disabled'}">
        <div class="form-field">
          <label class="form-label">Influence</label>
          <div class="exec-mode-row row gap-1">
            ${EXEC_MODES.map(m => `
              <button class="exec-pill ${d.aiExecutionMode === m.value ? 'exec-pill--active' : ''}"
                data-exec="${m.value}" ${on ? '' : 'disabled'}>${m.label}</button>
            `).join('')}
          </div>
        </div>
        <div class="text-caption text-faint" style="line-height:1.5">
          AI ranks your clips and explains why each was selected.
        </div>
      </div>
    </div>
  `;
}

/* ── Right panel (shell panel) ────────────────────────────────────── */

function updateStudioPanel(d) {
  const panelEl = document.querySelector('#panel-content');
  if (!panelEl) return;

  const title  = d.sessionTitle ?? null;
  const dur    = d.sessionDuration != null
    ? `${Math.floor(d.sessionDuration / 60)}:${String(Math.floor(d.sessionDuration % 60)).padStart(2, '0')}`
    : null;
  const src    = d.sourceMode === 'youtube' ? 'YouTube' : d.sourceMode === 'local' ? 'Local file' : null;
  const outDir = d.outputDir && d.outputDir.trim() ? d.outputDir.trim() : null;
  const qty    = d.maxExportParts ?? 5;
  const ar     = d.aspectRatio ?? '9:16';
  const min    = d.minPartSec  ?? 15;
  const max    = d.maxPartSec  ?? 60;
  const cam    = d.reframeMode ?? 'center';
  const sub    = d.subtitleEnabled ? (d.subtitleStyle ?? 'viral_bold').replace(/_/g, ' ') : 'off';
  const ai     = d.aiEnabled ? (d.aiExecutionMode ?? 'balanced') : 'off';

  panelEl.innerHTML = `
    <div class="col gap-4">
      ${title ? `<div class="text-body" style="font-weight:600;word-break:break-word;line-height:1.4">${_esc(title)}</div>` : ''}

      <div class="col gap-1">
        <div class="text-caption" style="font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--color-text-faint);margin-bottom:var(--sp-1)">Source</div>
        ${dur ? `<div class="text-caption text-faint">${_esc(dur)} duration</div>` : ''}
        ${src ? `<div class="text-caption text-faint">${_esc(src)}</div>`          : ''}
      </div>

      ${outDir ? `
        <div class="col gap-1">
          <div class="text-caption" style="font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--color-text-faint);margin-bottom:var(--sp-1)">Output</div>
          <div class="text-caption text-faint" style="word-break:break-all;line-height:1.4">${_esc(_trunc(outDir, 40))}</div>
        </div>
      ` : ''}

      <div class="col gap-2">
        <div class="text-caption" style="font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--color-text-faint);margin-bottom:var(--sp-1)">Render plan</div>
        <div class="row gap-1" style="flex-wrap:wrap">
          ${[ar, `≤${qty} clip${qty !== 1 ? 's' : ''}`, `${min}–${max}s`, cam].map(c =>
            `<span class="summary-chip">${_esc(c)}</span>`
          ).join('')}
        </div>
        <div class="text-caption text-faint">Subtitles · ${_esc(sub)}</div>
        <div class="text-caption text-faint">AI · ${_esc(ai)}</div>
      </div>
    </div>
  `;
}

/* ── Draft panel ──────────────────────────────────────────────────── */

function renderDraftPanel(d) {
  return `
    <div id="studio-draft" class="studio-draft">
      ${renderSectionA(d)}
      ${renderSectionB(d)}
      ${renderSectionC(d)}
      ${renderSectionD(d)}
    </div>
  `;
}

/* ── Render summary + CTA ─────────────────────────────────────────── */

function renderRenderSummary(d) {
  const qty  = d.maxExportParts ?? 5;
  const ar   = d.aspectRatio ?? '9:16';
  const min  = d.minPartSec  ?? 15;
  const max  = d.maxPartSec  ?? 60;
  const sub  = d.subtitleEnabled
    ? (d.subtitleStyle ?? 'viral_bold').replace(/_/g, ' ')
    : 'no subtitles';
  const ai   = d.aiEnabled ? (d.aiExecutionMode ?? 'balanced') : 'AI off';
  const dur  = d.sessionDuration != null
    ? `${Math.floor(d.sessionDuration / 60)}:${String(Math.floor(d.sessionDuration % 60)).padStart(2, '0')} source`
    : null;
  const chips = [ar, `≤${qty} clip${qty !== 1 ? 's' : ''}`, `${min}–${max}s`, sub, ai, ...(dur ? [dur] : [])];
  return `<div class="row gap-1" style="flex-wrap:wrap;margin-bottom:var(--sp-2)">${
    chips.map(c => `<span class="summary-chip">${_esc(c)}</span>`).join('')
  }</div>`;
}

function renderCTA(d) {
  const { renderBlocked, ffmpegAvailable } = readinessStore.getState();
  const { errors } = validateRenderDraft(d);
  const canSubmit  = errors.length === 0 && !_submitting && !renderBlocked;

  const ffmpegWarning = ffmpegAvailable === false
    ? `<div class="readiness-warning row gap-2" style="margin-bottom:var(--sp-2)"><span aria-hidden="true">⚠</span><span class="text-caption">FFmpeg is unavailable — rendering is disabled. Check System → Diagnostics.</span></div>`
    : '';

  return `
    <div id="studio-cta" class="studio-cta">
      ${ffmpegWarning}
      ${errors.length > 0
        ? `<div class="col gap-1">${errors.map(e => `<div class="text-caption" style="color:var(--color-failed)">⚠ ${_esc(e)}</div>`).join('')}</div>`
        : renderRenderSummary(d)}
      ${_submitError ? `<div class="text-caption" style="color:var(--color-failed)">✗ ${_esc(_submitError)}</div>` : ''}
      <button class="btn btn-primary studio-render-btn" id="studio-render-btn"
        ${!canSubmit ? 'disabled' : ''}>
        ${_submitting
          ? '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span>&nbsp;Starting…'
          : _submitError ? 'Retry Render →' : 'Start Render →'}
      </button>
      <button class="btn btn-ghost studio-back-link" id="studio-back-btn">← Back to Source</button>
    </div>
  `;
}

/* ── Wiring ───────────────────────────────────────────────────────── */

function rerender(el) {
  const { draft } = draftStore.getState();
  const draftEl = el.querySelector('#studio-draft');
  if (draftEl) draftEl.outerHTML = renderDraftPanel(draft);
  const ctaEl = el.querySelector('#studio-cta');
  if (ctaEl) ctaEl.outerHTML = renderCTA(draft);
  wireDraft(el);
  wireCTA(el);
  updateStudioPanel(draft);
}

function wireDraft(el) {
  el.querySelectorAll('.ratio-pill').forEach(b =>
    b.addEventListener('click', () => { draftStore.patch({ aspectRatio: b.dataset.ratio }); rerender(el); })
  );
  el.querySelector('#d-sub-on')?.addEventListener('change', e => {
    draftStore.patch({ subtitleEnabled: e.target.checked }); rerender(el);
  });
  el.querySelectorAll('.preset-pill').forEach(b =>
    b.addEventListener('click', () => { draftStore.patch({ subtitleStyle: b.dataset.preset }); rerender(el); })
  );
  el.querySelectorAll('input[name="d-reframe"]').forEach(r =>
    r.addEventListener('change', () => { if (r.checked) { draftStore.patch({ reframeMode: r.value }); rerender(el); } })
  );
  el.querySelector('#d-ai-on')?.addEventListener('change', e => {
    draftStore.patch({ aiEnabled: e.target.checked }); rerender(el);
  });
  el.querySelectorAll('.exec-pill').forEach(b =>
    b.addEventListener('click', () => { draftStore.patch({ aiExecutionMode: b.dataset.exec }); rerender(el); })
  );
  ['d-min', 'd-max', 'd-qty'].forEach(id => {
    el.querySelector(`#${id}`)?.addEventListener('change', e => {
      const v = parseInt(e.target.value, 10);
      if (!isNaN(v)) {
        if (id === 'd-min') draftStore.patch({ minPartSec: v });
        if (id === 'd-max') draftStore.patch({ maxPartSec: v });
        if (id === 'd-qty') draftStore.patch({ maxExportParts: v });
        rerender(el);
      }
    });
  });
}

function wireCTA(el) {
  el.querySelector('#studio-back-btn')?.addEventListener('click', () => router.go('/source'));
  el.querySelector('#studio-render-btn')?.addEventListener('click', () => handleRender(el));
}

async function handleRender(el) {
  const { draft } = draftStore.getState();
  const { valid, errors } = validateRenderDraft(draft);
  if (!valid) { _submitError = errors[0]; rerender(el); return; }

  _submitting  = true;
  _submitError = null;
  rerender(el);

  try {
    const payload = draftStore.buildPayload();
    const result  = await withTimeout(
      renderApi.process(payload),
      RENDER_TIMEOUT_MS,
      'Render submit'
    );
    const jobId = result?.job_id ?? result?.id;
    if (!jobId) throw new Error('No job ID returned. The render may have started — check Library for status.');
    router.go(`/monitor/${jobId}`);
  } catch (err) {
    _submitting  = false;
    _submitError = err.message;
    rerender(el);
  }
}

/* ── Mount ────────────────────────────────────────────────────────── */

export async function mount(el) {
  _submitting  = false;
  _submitError = null;

  const { draft } = draftStore.getState();
  const sessionId = draft.editSessionId;

  if (!sessionId) {
    el.innerHTML = `
      <div class="screen__header">
        <div class="screen__title">Studio</div>
        <div class="screen__subtitle">No source loaded</div>
      </div>
      <div class="screen__body">
        <div class="card col gap-4" style="max-width:400px">
          <div class="text-section" style="font-weight:600">No source loaded</div>
          <div class="text-body text-faint" style="line-height:1.6">
            Prepare a video in Source first, then come back to configure your render.
          </div>
          <button class="btn btn-primary" id="studio-no-session-btn" style="width:fit-content">
            ← Go to Source
          </button>
        </div>
      </div>
    `;
    el.querySelector('#studio-no-session-btn')?.addEventListener('click', () => router.go('/source'));
    return;
  }

  el.innerHTML = `
    <div class="screen__header studio-workspace-header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title studio-workspace-title">Studio</div>
          ${draft.sessionTitle
            ? `<div class="screen__subtitle">${_esc(draft.sessionTitle)}</div>`
            : `<div class="screen__subtitle" style="font-size:10px;font-family:monospace">Session ${sessionId.slice(0, 8)}…</div>`}
        </div>
        <span class="flex-1"></span>
        ${draft.sessionDuration != null
          ? `<span class="text-caption text-faint" style="font-variant-numeric:tabular-nums">${Math.floor(draft.sessionDuration / 60)}:${String(Math.floor(draft.sessionDuration % 60)).padStart(2, '0')}</span>`
          : ''}
      </div>
    </div>
    <div class="studio-body">
      <div class="studio-left">${renderPreviewArea(sessionId)}</div>
      <div class="studio-right">
        <div class="studio-right__scroll">${renderDraftPanel(draft)}</div>
        ${renderCTA(draft)}
      </div>
    </div>
  `;

  // Preview: loading overlay → ready or error (10 s timeout)
  const video     = el.querySelector('#studio-video');
  const videoLoad = el.querySelector('#studio-video-loading');
  const videoErr  = el.querySelector('#studio-video-err');
  if (video && videoLoad) {
    let _previewTimer = null;

    const _hideLoading = () => {
      if (_previewTimer) { clearTimeout(_previewTimer); _previewTimer = null; }
      videoLoad.style.display = 'none';
    };
    const _showPreviewErr = () => {
      _hideLoading();
      if (videoErr) videoErr.style.display = '';
    };

    video.addEventListener('canplay', _hideLoading);
    video.addEventListener('loadedmetadata', _hideLoading);
    video.addEventListener('error', _showPreviewErr);
    _previewTimer = setTimeout(_showPreviewErr, 10_000);

    if (video.readyState >= 3) _hideLoading();

    el.addEventListener('unmount', () => {
      if (_previewTimer) clearTimeout(_previewTimer);
      video.removeEventListener('canplay', _hideLoading);
      video.removeEventListener('loadedmetadata', _hideLoading);
      video.removeEventListener('error', _showPreviewErr);
    });

    el.querySelector('#studio-video-retry')?.addEventListener('click', () => {
      if (videoErr) videoErr.style.display = 'none';
      videoLoad.style.display = '';
      _previewTimer = setTimeout(_showPreviewErr, 10_000);
      video.load();
    });
  }

  el.querySelector('#studio-no-source-btn')?.addEventListener('click', () => router.go('/source'));

  wireDraft(el);
  wireCTA(el);
  updateStudioPanel(draft);

  el.addEventListener('unmount', () => {
    const panelEl = document.querySelector('#panel-content');
    if (panelEl) panelEl.textContent = 'Select a job to see details.';
  });
}

export const studioScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
function _trunc(s, n) { const str = String(s ?? ''); return str.length > n ? str.slice(0, n) + '…' : str; }
