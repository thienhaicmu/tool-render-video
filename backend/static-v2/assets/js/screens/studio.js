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
  { value: 'center',  label: 'Center',  desc: 'Locked center crop' },
  { value: 'motion',  label: 'Motion',  desc: 'Motion-aware reframe' },
  { value: 'subject', label: 'Subject', desc: 'Subject-tracking crop' },
];

const EXEC_MODES = [
  { value: 'off',        label: 'Off'        },
  { value: 'safe',       label: 'Safe'       },
  { value: 'balanced',   label: 'Balanced'   },
  { value: 'aggressive', label: 'Aggressive' },
];

let _submitting = false;
let _submitError = null;

/* ── Preview ──────────────────────────────────────────────────────── */

function renderPreviewArea(sessionId) {
  if (!sessionId) {
    return `
      <div class="studio-preview studio-preview--empty col" style="align-items:center;justify-content:center;gap:var(--sp-3)">
        <div style="opacity:0.25;color:var(--color-text-muted);width:48px;height:48px">${ICONS.video}</div>
        <div class="text-body text-muted">No source prepared</div>
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
      <div id="studio-video-err" class="studio-video-err" style="display:none">
        <div class="col gap-3" style="align-items:center">
          <div class="text-body" style="color:var(--color-text-muted)">Preview couldn't load</div>
          <div class="text-caption text-faint">The source may still be processing. You can still configure and start the render.</div>
          <button class="btn btn-ghost" id="studio-video-retry">Retry preview</button>
        </div>
      </div>
    </div>
  `;
}

/* ── Draft section renderers ──────────────────────────────────────── */

function renderSectionA(d) {
  return `
    <div class="draft-section">
      <div class="draft-section__title">A · Clip Setup</div>
      <div class="col gap-3">
        <div class="row gap-3">
          <div class="form-field flex-1">
            <label class="form-label">Min sec</label>
            <input class="form-input" id="d-min" type="number" min="5" max="300" value="${d.minPartSec}" />
          </div>
          <div class="form-field flex-1">
            <label class="form-label">Max sec</label>
            <input class="form-input" id="d-max" type="number" min="10" max="300" value="${d.maxPartSec}" />
          </div>
          <div class="form-field flex-1">
            <label class="form-label">Max clips</label>
            <input class="form-input" id="d-qty" type="number" min="1" max="20" value="${d.maxExportParts}" />
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">Aspect ratio</label>
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
        <span>B · Subtitles</span>
        <label class="toggle-wrap" style="margin-left:auto;cursor:pointer;display:flex;align-items:center;gap:var(--sp-2)">
          <input type="checkbox" id="d-sub-on" ${on ? 'checked' : ''} style="width:14px;height:14px" />
          <span class="text-caption" style="color:${on ? 'var(--color-accent)' : 'var(--color-text-faint)'}">${on ? 'On' : 'Off'}</span>
        </label>
      </div>
      <div class="col gap-3 ${on ? '' : 'section-disabled'}">
        <div class="form-field">
          <label class="form-label">Style preset</label>
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
      <div class="draft-section__title">C · Camera</div>
      <div class="col gap-2">
        ${CAMERA_MODES.map(m => `
          <label class="camera-option ${d.reframeMode === m.value ? 'camera-option--active' : ''}">
            <input type="radio" name="d-reframe" value="${m.value}" ${d.reframeMode === m.value ? 'checked' : ''} />
            <div>
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
        <span>D · AI Analysis</span>
        <label class="toggle-wrap" style="margin-left:auto;cursor:pointer;display:flex;align-items:center;gap:var(--sp-2)">
          <input type="checkbox" id="d-ai-on" ${on ? 'checked' : ''} style="width:14px;height:14px" />
          <span class="text-caption" style="color:${on ? 'var(--color-ai)' : 'var(--color-text-faint)'}">${on ? 'On' : 'Off'}</span>
        </label>
      </div>
      <div class="col gap-3 ${on ? '' : 'section-disabled'}">
        <div class="form-field">
          <label class="form-label">Execution mode</label>
          <div class="exec-mode-row row gap-1">
            ${EXEC_MODES.map(m => `
              <button class="exec-pill ${d.aiExecutionMode === m.value ? 'exec-pill--active' : ''}"
                data-exec="${m.value}" ${on ? '' : 'disabled'}>${m.label}</button>
            `).join('')}
          </div>
        </div>
        <div class="text-caption text-faint">AI analyzes your source and explains ranking recommendations. Enable execution influence in advanced settings to allow bounded render changes.</div>
      </div>
    </div>
  `;
}

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

function renderCTA(d) {
  const { renderBlocked, ffmpegAvailable } = readinessStore.getState();
  const { errors } = validateRenderDraft(d);
  const canSubmit  = errors.length === 0 && !_submitting && !renderBlocked;

  const ffmpegWarning = ffmpegAvailable === false
    ? `<div class="readiness-warning row gap-2"><span aria-hidden="true">⚠</span><span class="text-caption">FFmpeg is unavailable, so rendering is disabled. Check System → Diagnostics for details.</span></div>`
    : '';

  return `
    <div id="studio-cta" class="studio-cta">
      ${ffmpegWarning}
      ${errors.length > 0
        ? `<div class="col gap-1">${errors.map(e => `<div class="text-caption" style="color:var(--color-failed)">⚠ ${_esc(e)}</div>`).join('')}</div>`
        : ''}
      ${_submitError ? `<div class="text-caption" style="color:var(--color-failed)">✗ ${_esc(_submitError)}</div>` : ''}
      <div class="row gap-3" style="align-items:center">
        <button class="btn btn-ghost" id="studio-back-btn">← Source</button>
        <span class="flex-1"></span>
        <button class="btn btn-primary" id="studio-render-btn"
          ${!canSubmit ? 'disabled' : ''} style="min-width:140px">
          ${_submitting
            ? '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>&nbsp;Starting…'
            : 'Start render →'}
        </button>
      </div>
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

  // Route recovery: no session on refresh → show explanation and link to Source
  if (!sessionId) {
    el.innerHTML = `
      <div class="screen__header">
        <div class="screen__title">Studio</div>
        <div class="screen__subtitle">No source loaded</div>
      </div>
      <div class="screen__body">
        <div class="card col gap-3" style="max-width:420px">
          <div class="text-body" style="font-weight:600">No source is loaded</div>
          <div class="text-caption text-faint">Go back to Source to prepare a video before opening Studio.</div>
          <button class="btn btn-primary" id="studio-no-session-btn" style="width:fit-content">← Go to Source</button>
        </div>
      </div>
    `;
    el.querySelector('#studio-no-session-btn')?.addEventListener('click', () => router.go('/source'));
    return;
  }

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">Studio</div>
          <div class="screen__subtitle">${
            draft.sessionTitle ? _esc(draft.sessionTitle)
              : sessionId ? `Session ${sessionId.slice(0, 8)}…`
              : 'No source — go back to Source'
          }</div>
        </div>
        ${draft.sessionDuration != null
          ? `<span class="text-caption text-faint">${Math.floor(draft.sessionDuration/60)}:${String(Math.floor(draft.sessionDuration%60)).padStart(2,'0')} source</span>`
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

  // Video error + retry handler
  const video    = el.querySelector('#studio-video');
  const videoErr = el.querySelector('#studio-video-err');
  if (video && videoErr) {
    video.addEventListener('error', () => {
      video.style.display = 'none';
      videoErr.style.display = '';
    });
    el.querySelector('#studio-video-retry')?.addEventListener('click', () => {
      videoErr.style.display = 'none';
      video.style.display = '';
      video.load();
    });
  }

  el.querySelector('#studio-no-source-btn')?.addEventListener('click', () => router.go('/source'));

  wireDraft(el);
  wireCTA(el);
}

export const studioScreen = { mount };

function _esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }
