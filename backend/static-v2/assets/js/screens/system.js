/* System / Diagnostics screen — runtime readiness, AI diagnostics, environment.
   Route: #/system (no params)
   APIs: GET /api/warmup/status, GET /api/render/ai-diagnostics, GET /health
*/

import { systemApi }   from '../api/system.js';
import { systemStore } from '../store/system.js';

/* ── Warmup item metadata ────────────────────────────────────────────── */

const WARMUP_META = {
  ffmpeg:           { label: 'FFmpeg',            group: 'core' },
  gpu:              { label: 'GPU / CUDA',         group: 'core' },
  yt_dlp:           { label: 'yt-dlp',             group: 'core' },
  opencv_cascades:  { label: 'OpenCV cascades',    group: 'core' },
  whisper_tiny:     { label: 'Whisper tiny',        group: 'ai'   },
  whisper_base:     { label: 'Whisper base',        group: 'ai'   },
  whisper_small:    { label: 'Whisper small',       group: 'ai'   },
  ollama_service:   { label: 'Ollama service',      group: 'ai'   },
  ollama_model:     { label: 'Ollama model',        group: 'ai'   },
};

/* ── Dependency display metadata ─────────────────────────────────────── */

const DEP_META = {
  sentence_transformers: { label: 'Sentence Transformers', required: false },
  faiss:                 { label: 'FAISS',                  required: false },
  librosa:               { label: 'Librosa',                required: false },
  mediapipe:             { label: 'MediaPipe',              required: false },
  faster_whisper:        { label: 'faster-whisper',         required: false },
  whisperx:              { label: 'WhisperX',               required: false },
  deepfilternet:         { label: 'DeepFilterNet',          required: false },
};

/* ── Helpers ─────────────────────────────────────────────────────────── */

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _warmupToStatusLabel(status) {
  switch (status) {
    case 'ready':   return { cls: 'sys-badge--ok',      text: 'Ready'    };
    case 'running': return { cls: 'sys-badge--running',  text: 'Running'  };
    case 'pending': return { cls: 'sys-badge--pending',  text: 'Pending'  };
    case 'skipped': return { cls: 'sys-badge--skipped',  text: 'Skipped'  };
    case 'error':   return { cls: 'sys-badge--error',    text: 'Error'    };
    default:        return { cls: 'sys-badge--pending',  text: status ?? 'Unknown' };
  }
}

function _boolRow(label, value, invert = false) {
  const ok  = invert ? !value : !!value;
  const sym = ok ? '&#10003;' : '&#10007;';
  const cls = ok ? 'sys-bool-yes' : 'sys-bool-no';
  return `
    <div class="sys-dep-row row gap-2">
      <span class="sys-dep-label text-caption">${_esc(label)}</span>
      <span class="flex-1"></span>
      <span class="${cls} text-caption">${sym}</span>
    </div>`;
}

function _depRow(label, available) {
  const sym = available ? '&#10003;' : '&#8212;';
  const cls = available ? 'sys-bool-yes' : 'sys-bool-no';
  return `
    <div class="sys-dep-row row gap-2">
      <span class="sys-dep-label text-caption">${_esc(label)}</span>
      <span class="flex-1"></span>
      <span class="${cls} text-caption">${sym}</span>
    </div>`;
}

/* ── Module-level screen state ───────────────────────────────────────── */

let _s = {
  warmup:       null,
  aiDiag:       null,
  health:       null,
  loading:      false,
  error:        null,
  lastChecked:  null,
};
let _el = null;

/* ── Refresh (parallel fetch with graceful partial failure) ──────────── */

async function _refresh() {
  if (_s.loading) return;
  _s.loading = true;
  _s.error   = null;
  _renderRefreshBtn();

  try {
    const [warmupRes, aiRes, healthRes] = await Promise.allSettled([
      systemApi.getWarmupStatus(),
      systemApi.getAIDiagnostics(),
      systemApi.getHealth(),
    ]);

    if (warmupRes.status === 'fulfilled') _s.warmup  = warmupRes.value;
    if (aiRes.status     === 'fulfilled') _s.aiDiag  = aiRes.value;
    if (healthRes.status === 'fulfilled') _s.health  = healthRes.value;

    const failed = [warmupRes, aiRes, healthRes].filter(r => r.status === 'rejected');
    if (failed.length === 3) {
      _s.error = 'All diagnostics endpoints unavailable. Is the backend running?';
    }

    _s.lastChecked = new Date();
  } finally {
    _s.loading = false;
    _renderAll();
  }
}

/* ── Render: refresh button state ────────────────────────────────────── */

function _renderRefreshBtn() {
  const btn = _el?.querySelector('#sys-refresh-btn');
  if (!btn) return;
  btn.disabled    = _s.loading;
  btn.textContent = _s.loading ? 'Refreshing…' : 'Refresh';
}

/* ── Render: runtime readiness grid ─────────────────────────────────── */

function _renderReadiness() {
  const section = _el?.querySelector('#sys-readiness-section');
  if (!section) return;

  const storeState = systemStore.getState();
  const backendUp  = _s.health != null;
  const backendBadge = backendUp
    ? { cls: 'sys-badge--ok',    text: 'Online' }
    : { cls: 'sys-badge--error', text: 'Offline' };

  const backendCard = `
    <div class="sys-status-card">
      <div class="sys-status-card__label text-caption">Backend</div>
      <span class="sys-badge ${_esc(backendBadge.cls)}">${backendBadge.text}</span>
      ${storeState.appVersion
        ? `<div class="text-caption text-faint sys-status-card__detail">v${_esc(storeState.appVersion)}</div>`
        : ''}
    </div>`;

  let warmupCards = '';
  if (_s.warmup?.items && Array.isArray(_s.warmup.items)) {
    warmupCards = _s.warmup.items.map(item => {
      const meta  = WARMUP_META[item.key] ?? { label: item.key, group: 'core' };
      const badge = _warmupToStatusLabel(item.status);
      const detail = item.message
        ? `<div class="text-caption text-faint sys-status-card__detail" title="${_esc(item.message)}">${_esc(item.message.slice(0, 40))}${item.message.length > 40 ? '…' : ''}</div>`
        : (item.size_mb != null
          ? `<div class="text-caption text-faint sys-status-card__detail">${_esc(String(item.size_mb))} MB</div>`
          : '');
      return `
        <div class="sys-status-card">
          <div class="sys-status-card__label text-caption">${_esc(meta.label)}</div>
          <span class="sys-badge ${_esc(badge.cls)}">${badge.text}</span>
          ${detail}
        </div>`;
    }).join('');
  } else if (_s.warmup == null) {
    warmupCards = `<div class="text-caption text-faint" style="grid-column:1/-1">Warmup status unavailable</div>`;
  }

  const summary = _s.warmup
    ? `<span class="text-caption text-faint sys-readiness-summary">${_s.warmup.ready_count ?? 0} / ${_s.warmup.total_count ?? 0} ready${_s.warmup.in_progress ? ' · in progress' : ''}</span>`
    : '';

  section.innerHTML = `
    <div class="col gap-3">
      <div class="row gap-2" style="align-items:center">
        <div class="text-section">Runtime Readiness</div>
        ${summary}
      </div>
      <div class="sys-status-grid">
        ${backendCard}
        ${warmupCards}
      </div>
    </div>`;
}

/* ── Render: AI Intelligence panel ───────────────────────────────────── */

function _renderAI() {
  const section = _el?.querySelector('#sys-ai-section');
  if (!section) return;

  if (!_s.aiDiag) {
    section.innerHTML = `
      <div class="col gap-2">
        <div class="text-section">AI Intelligence</div>
        <div class="text-caption text-faint">AI diagnostics unavailable</div>
      </div>`;
    return;
  }

  const d = _s.aiDiag;
  const deps = d.dependencies ?? {};
  const vStore = d.vector_store ?? {};
  const mem    = d.memory ?? {};

  const coreRows = [
    _boolRow('Startup safe',              d.startup_safe),
    _boolRow('Embeddings available',      d.embedding_available),
    _boolRow('Vector store (FAISS)',       vStore.faiss_available),
    _boolRow('Vector store fallback mode', vStore.fallback_mode, true),
    _boolRow('Memory (SQLite)',            mem.sqlite_available),
  ].join('');

  const memDetail = mem.count != null
    ? `<div class="text-caption text-faint">Memory entries: ${_esc(String(mem.count))}</div>`
    : '';

  const depRows = Object.entries(DEP_META).map(([key, meta]) => {
    const available = deps[key] === true;
    return _depRow(meta.label, available);
  }).join('');

  section.innerHTML = `
    <div class="col gap-4">
      <div class="text-section">AI Intelligence</div>
      <div class="col gap-1">
        <div class="text-caption text-faint" style="margin-bottom:4px">Core capabilities</div>
        ${coreRows}
        ${memDetail}
      </div>
      <div class="col gap-1">
        <div class="text-caption text-faint" style="margin-bottom:4px">Optional libraries</div>
        ${depRows}
      </div>
    </div>`;
}

/* ── Render: environment panel ───────────────────────────────────────── */

function _renderEnvironment() {
  const section = _el?.querySelector('#sys-env-section');
  if (!section) return;

  const st = systemStore.getState();
  const healthData = _s.health ?? st.health;

  const rows = [];

  const backendUrl = window.location.origin;
  rows.push(`
    <div class="sys-dep-row row gap-2">
      <span class="sys-dep-label text-caption">Backend URL</span>
      <span class="flex-1"></span>
      <span class="text-caption" style="font-family:monospace">${_esc(backendUrl)}</span>
    </div>`);

  const execMode = st.executionMode ?? healthData?.execution_mode ?? '—';
  rows.push(`
    <div class="sys-dep-row row gap-2">
      <span class="sys-dep-label text-caption">Execution mode</span>
      <span class="flex-1"></span>
      <span class="text-caption">${_esc(execMode)}</span>
    </div>`);

  if (st.appVersion) {
    rows.push(`
      <div class="sys-dep-row row gap-2">
        <span class="sys-dep-label text-caption">App version</span>
        <span class="flex-1"></span>
        <span class="text-caption" style="font-family:monospace">${_esc(st.appVersion)}</span>
      </div>`);
  }

  if (healthData?.gpu_available != null) {
    rows.push(_boolRow('GPU available', healthData.gpu_available));
  }

  if (healthData?.ffmpeg_available != null) {
    rows.push(_boolRow('FFmpeg available', healthData.ffmpeg_available));
  }

  section.innerHTML = `
    <div class="col gap-3">
      <div class="text-section">Environment</div>
      <div class="col gap-1">${rows.join('')}</div>
    </div>`;
}

/* ── Render: troubleshooting tips ────────────────────────────────────── */

function _renderTroubleshooting() {
  const section = _el?.querySelector('#sys-trouble-section');
  if (!section) return;

  const tips = [];

  if (_s.warmup?.errors && _s.warmup.errors.length > 0) {
    for (const err of _s.warmup.errors) {
      tips.push({ icon: '&#9888;', text: _esc(String(err)) });
    }
  }

  if (_s.warmup?.items) {
    for (const item of _s.warmup.items) {
      if (item.status === 'error' && item.message) {
        const meta = WARMUP_META[item.key] ?? { label: item.key };
        tips.push({ icon: '&#10007;', text: `${_esc(meta.label)}: ${_esc(item.message)}` });
      }
    }
  }

  if (_s.aiDiag?.warnings && _s.aiDiag.warnings.length > 0) {
    for (const w of _s.aiDiag.warnings) {
      tips.push({ icon: '&#9888;', text: _esc(String(w)) });
    }
  }

  if (_s.aiDiag?.memory?.warnings && _s.aiDiag.memory.warnings.length > 0) {
    for (const w of _s.aiDiag.memory.warnings) {
      tips.push({ icon: '&#9888;', text: _esc(String(w)) });
    }
  }

  if (_s.error) {
    tips.push({ icon: '&#10007;', text: _esc(_s.error) });
  }

  if (tips.length === 0) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  section.innerHTML = `
    <div class="col gap-3">
      <div class="text-section">Troubleshooting</div>
      <div class="col gap-2">
        ${tips.map(t => `
          <div class="sys-tip row gap-2">
            <span class="sys-tip-icon">${t.icon}</span>
            <span class="text-caption">${t.text}</span>
          </div>`).join('')}
      </div>
    </div>`;
}

/* ── Render: timestamp ───────────────────────────────────────────────── */

function _renderTimestamp() {
  const el = _el?.querySelector('#sys-timestamp');
  if (!el) return;
  el.textContent = _s.lastChecked
    ? `Last checked: ${_s.lastChecked.toLocaleTimeString()}`
    : '';
}

/* ── Render all ──────────────────────────────────────────────────────── */

function _renderAll() {
  _renderRefreshBtn();
  _renderReadiness();
  _renderAI();
  _renderEnvironment();
  _renderTroubleshooting();
  _renderTimestamp();
}

/* ── Mount ───────────────────────────────────────────────────────────── */

export async function mount(el, _params) {
  _s  = { warmup: null, aiDiag: null, health: null, loading: false, error: null, lastChecked: null };
  _el = el;

  el.innerHTML = `
    <div class="screen__header">
      <div class="row gap-3" style="align-items:center">
        <div>
          <div class="screen__title">System</div>
          <div class="screen__subtitle">Runtime readiness &amp; diagnostics</div>
        </div>
        <span class="flex-1"></span>
        <span id="sys-timestamp" class="sys-timestamp text-caption text-faint"></span>
        <button class="btn btn-secondary btn-sm" id="sys-refresh-btn">Refresh</button>
      </div>
    </div>
    <div class="screen__body col gap-4" id="sys-body">
      <div class="card" id="sys-readiness-section">
        <div class="text-caption text-faint">Loading readiness…</div>
      </div>
      <div class="card" id="sys-ai-section">
        <div class="text-caption text-faint">Loading AI diagnostics…</div>
      </div>
      <div class="card" id="sys-env-section">
        <div class="text-caption text-faint">Loading environment…</div>
      </div>
      <div class="card" id="sys-trouble-section" hidden></div>
    </div>
  `;

  el.querySelector('#sys-refresh-btn')?.addEventListener('click', _refresh);

  await _refresh();
}

export const systemScreen   = { mount };
export const settingsScreen = systemScreen;
