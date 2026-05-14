/* Studio screen — configure render settings, launch render job. */

import { draftStore } from '../store/draft.js';
import { renderApi } from '../api/render.js';
import { router } from '../router.js';
import { sessionStore } from '../store/session.js';

const PLATFORMS = [
  { value: 'youtube',  label: 'YouTube' },
  { value: 'tiktok',   label: 'TikTok' },
  { value: 'instagram',label: 'Instagram' },
  { value: 'twitter',  label: 'X / Twitter' },
  { value: 'facebook', label: 'Facebook' },
];

const CREATOR_TYPES = [
  { value: 'solo_creator',     label: 'Solo Creator' },
  { value: 'studio_team',      label: 'Studio Team' },
  { value: 'brand_channel',    label: 'Brand Channel' },
  { value: 'news_media',       label: 'News Media' },
  { value: 'educational',      label: 'Educational' },
];

const EXEC_MODES = [
  { value: 'safe',       label: 'Safe'       },
  { value: 'balanced',   label: 'Balanced'   },
  { value: 'aggressive', label: 'Aggressive' },
];

function renderForm(draft) {
  return `
    <div style="max-width:560px">
      <div class="col gap-4">

        <div class="form-field">
          <label class="form-label">Source file</label>
          <input class="form-input" id="studio-source" type="text" placeholder="/path/to/video.mp4" value="${draft.sourceFile ?? ''}" />
        </div>

        <div class="form-field">
          <label class="form-label">Output directory</label>
          <input class="form-input" id="studio-output" type="text" placeholder="/path/to/output/" value="${draft.outputDir ?? ''}" />
        </div>

        <div class="row gap-4">
          <div class="form-field flex-1">
            <label class="form-label">Platform</label>
            <select class="form-input" id="studio-platform">
              ${PLATFORMS.map(p => `<option value="${p.value}" ${draft.platform === p.value ? 'selected' : ''}>${p.label}</option>`).join('')}
            </select>
          </div>

          <div class="form-field flex-1">
            <label class="form-label">Creator type</label>
            <select class="form-input" id="studio-creator-type">
              ${CREATOR_TYPES.map(c => `<option value="${c.value}" ${draft.creatorType === c.value ? 'selected' : ''}>${c.label}</option>`).join('')}
            </select>
          </div>
        </div>

        <div class="form-field">
          <label class="form-label">AI execution mode</label>
          <div class="row gap-2">
            ${EXEC_MODES.map(m => `
              <label class="row gap-2" style="cursor:pointer;font-size:var(--text-body)">
                <input type="radio" name="exec-mode" value="${m.value}" ${draft.executionMode === m.value ? 'checked' : ''} />
                ${m.label}
              </label>
            `).join('')}
          </div>
        </div>

        <div class="row gap-3" style="align-items:center">
          <label class="row gap-2" style="cursor:pointer">
            <input type="checkbox" id="studio-ai-enabled" ${draft.aiEnabled ? 'checked' : ''} />
            <span class="text-body">Enable AI analysis</span>
          </label>
        </div>

        <div class="row gap-3 mt-4">
          <button class="btn btn-primary" id="studio-render-btn">Start render</button>
          <button class="btn btn-ghost" id="studio-back-btn">← Back</button>
          <span class="flex-1"></span>
          <span class="text-caption text-faint" id="studio-error"></span>
        </div>
      </div>
    </div>
  `;
}

async function mount(el) {
  await draftStore.loadRemote();
  const { draft } = draftStore.getState();

  el.innerHTML = `
    <div class="screen__header">
      <div class="screen__title">Studio</div>
      <div class="screen__subtitle">Configure render settings</div>
    </div>
    <div class="screen__body">
      ${renderForm(draft)}
    </div>
  `;

  const sourceInput     = el.querySelector('#studio-source');
  const outputInput     = el.querySelector('#studio-output');
  const platformSelect  = el.querySelector('#studio-platform');
  const creatorSelect   = el.querySelector('#studio-creator-type');
  const aiCheckbox      = el.querySelector('#studio-ai-enabled');
  const renderBtn       = el.querySelector('#studio-render-btn');
  const backBtn         = el.querySelector('#studio-back-btn');
  const errorEl         = el.querySelector('#studio-error');

  sourceInput?.addEventListener('input', () => draftStore.patch({ sourceFile: sourceInput.value }));
  outputInput?.addEventListener('input', () => draftStore.patch({ outputDir: outputInput.value }));
  platformSelect?.addEventListener('change', () => draftStore.patch({ platform: platformSelect.value }));
  creatorSelect?.addEventListener('change', () => draftStore.patch({ creatorType: creatorSelect.value }));
  aiCheckbox?.addEventListener('change', () => draftStore.patch({ aiEnabled: aiCheckbox.checked }));

  el.querySelectorAll('input[name="exec-mode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      if (radio.checked) draftStore.patch({ executionMode: radio.value });
    });
  });

  backBtn?.addEventListener('click', () => router.go('/source'));

  renderBtn?.addEventListener('click', async () => {
    renderBtn.disabled = true;
    renderBtn.textContent = 'Starting…';
    if (errorEl) errorEl.textContent = '';

    try {
      const payload = draftStore.buildPayload();
      const result  = await renderApi.submit(payload);
      const jobId   = result?.job_id ?? result?.id;
      if (!jobId) throw new Error('No job_id in response');
      router.go(`/monitor/${jobId}`);
    } catch (err) {
      if (errorEl) errorEl.textContent = err.message;
      renderBtn.disabled = false;
      renderBtn.textContent = 'Start render';
    }
  });
}

export const studioScreen = { mount };
