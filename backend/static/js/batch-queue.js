/* =========================================================
   batch-queue.js — UP23: Batch Creator Workflow
   Queue many local video files, render overnight.

   - One UP21 preset applied to ALL files via shared form fields
   - Reuses existing /api/render/process endpoint per file
   - Backend MAX_CONCURRENT_JOBS enforced automatically
   - Failure isolation: one failure never kills the batch
   - Output dir per file: sibling folder named after file stem
   ========================================================= */
'use strict';

window.BatchQueue = (() => {

  // ── State ──────────────────────────────────────────────────────────────────
  let _items = [];       // { id, name, filePath, outputDir, status, jobId, progress, error }
  let _pollTimer = null;
  const POLL_INTERVAL_MS = 2000;
  const MAX_BATCH = 50;

  const STATUS = {
    PENDING:   'pending',
    QUEUED:    'queued',
    RUNNING:   'running',
    COMPLETED: 'completed',
    RECOVERED: 'recovered',   // completed but one or more safe fallbacks were used
    FAILED:    'failed',
    CANCELLED: 'cancelled',
  };

  // ── ID gen ─────────────────────────────────────────────────────────────────
  let _seq = 0;
  function _genId() { return 'bq_' + (++_seq) + '_' + Date.now().toString(36); }

  // ── Output dir from file path ──────────────────────────────────────────────
  function _computeOutputDir(filePath, fileName) {
    if (!filePath || filePath === fileName) return '';
    const sep = filePath.includes('\\') ? '\\' : '/';
    const parent = filePath.substring(0, filePath.lastIndexOf(sep));
    const stem = fileName.replace(/\.[^/.]+$/, '');
    return parent + sep + stem;
  }

  // ── Payload builder (reads current form fields) ───────────────────────────
  function _buildPayload(item) {
    const gv = (id, fb) => { const el = document.getElementById(id); return (el && el.value !== undefined) ? el.value : fb; };
    const gc = (id)      => { const el = document.getElementById(id); return el ? !!el.checked : false; };
    const gn = (id, fb)  => { const el = document.getElementById(id); return el ? Number(el.value) || fb : fb; };

    const aspectRatio = gv('evAspectRatio', '3:4');
    const PLAY_RES_Y  = {'9:16': 1920, '3:4': 1440, '4:5': 1440, '1:1': 1080, '16:9': 1080};
    const playResY    = PLAY_RES_Y[aspectRatio] || 1440;
    const posY        = gn('evSubPos', 15);
    const reframe     = gv('evReframeStrategy', 'fast_center');

    return {
      source_mode:         'local',
      source_video_path:   item.filePath,
      output_dir:          item.outputDir,
      output_mode:         'manual',
      channel_code:        '',
      render_output_subdir:'',
      edit_session_id:     null,
      edit_trim_in:        0,
      edit_trim_out:       0,
      edit_volume:         1.0,

      render_profile:      gv('evRenderProfile', 'balanced'),
      aspect_ratio:        aspectRatio,
      add_subtitle:        gc('evAddSubtitle'),
      subtitle_style:      gv('evSubStyle', 'pro_karaoke'),
      sub_font:            gv('evSubFont', 'Bungee'),
      sub_font_size:       gn('evSubSize', 46),
      sub_color:           gv('evSubColor', '#ffffff'),
      sub_highlight:       gv('evSubHighlight', '#ffff00'),
      sub_outline:         gn('evSubOutline', 3),
      sub_margin_v:        Math.round((posY / 100) * playResY),
      sub_x_percent:       Math.max(5, Math.min(95, gn('evSubPosX', 50))),
      subtitle_only_viral_high: false,
      subtitle_viral_min_score: 0,
      subtitle_viral_top_ratio: 1.0,

      target_platform:     gv('evTargetPlatform', 'youtube_shorts'),
      multi_variant:       gc('evMultiVariant'),
      cta_enabled:         gc('evCtaEnabled'),
      cta_type:            gv('evCtaType', 'auto'),

      playback_speed:      gn('evPlaybackSpeed', 1.07),
      min_part_sec:        gn('evMinPart', 70),
      max_part_sec:        gn('evMaxPart', 180),
      max_export_parts:    gn('evMaxExportParts', 0),
      output_fps:          gn('evOutputFps', 60),
      max_parallel_parts:  0,
      part_order:          gv('evPartOrder', 'viral'),
      frame_scale_y:       Math.max(80, Math.min(130, gn('evFrameScaleY', 106))),
      motion_aware_crop:   reframe !== 'fast_center',
      reframe_mode:        reframe === 'fast_center' ? 'center' : reframe,
      cleanup_temp_files:  gc('evCleanupTemp'),
      source_quality_mode: gv('evSourceQualityMode', 'standard_1080'),

      effect_preset:       gv('evEffectPreset', 'story_clean_01'),
      transition_sec:      0.25,
      reup_mode:           false,
      reup_overlay_enable: false,
      reup_overlay_opacity:0.08,
      reup_bgm_enable:     false,
      reup_bgm_path:       null,
      reup_bgm_gain:       0.18,
      loudnorm_enabled:    false,

      voice_enabled:       false,
      voice_text:          null,
      add_title_overlay:   false,
      title_overlay_text:  '',
      text_layers:         [],
      subtitle_translate_enabled: false,
      subtitle_target_language:   'en',
      subtitle_edits:      null,
      editor_clip_plan:    null,

      market_viral: {
        target_market:     'US',
        subtitle_tone:     'clean',
        keyword_highlight: false,
        hook_engine_v2:    { best_hook: '', variants: [], scores: [] },
      },
      viral_market:               'US',
      hook_apply_enabled:         false,
      hook_applied_text:          '',
      hook_score:                 null,
      combined_scoring_enabled:   false,
      adaptive_scoring_enabled:   false,
      auto_best_export_enabled:   false,
      auto_best_export_count:     3,

      creator_dna: (typeof CreatorDNA !== 'undefined') ? CreatorDNA.getDNAContext() : null,

      // UP26: Pro Timeline Steering
      structure_bias:    (document.getElementById('qsStructureBias')?.value) || 'balanced',
      subtitle_emphasis: (document.getElementById('evSubtitleEmphasis')?.value) || 'balanced',
      clip_lock:    (typeof ClipSteering !== 'undefined' && ClipSteering.getClipLock().length)    ? ClipSteering.getClipLock()    : null,
      clip_exclude: (typeof ClipSteering !== 'undefined' && ClipSteering.getClipExclude().length) ? ClipSteering.getClipExclude() : null,
    };
  }

  // ── File ingestion ─────────────────────────────────────────────────────────
  function openFilePicker() {
    const inp = document.getElementById('bqFileInput');
    if (inp) inp.click();
  }

  function onFilesSelected(files) {
    if (!files || !files.length) return;
    const toAdd = Array.from(files).slice(0, MAX_BATCH - _items.length);
    if (!toAdd.length) {
      if (typeof showToast === 'function') showToast(`Batch capped at ${MAX_BATCH} files`, 'warning');
      return;
    }
    for (const f of toAdd) {
      const filePath = f.path || f.name;
      const outputDir = _computeOutputDir(filePath, f.name);
      _items.push({ id: _genId(), name: f.name, filePath, outputDir, status: STATUS.PENDING, jobId: null, progress: 0, error: '' });
    }
    _render();
    _log('batch_files_added', toAdd.length);
  }

  function onDrop(e) {
    e.preventDefault();
    const zone = document.getElementById('bqDropZone');
    if (zone) zone.classList.remove('over');
    onFilesSelected(e.dataTransfer?.files);
  }

  function onDragOver(e) {
    e.preventDefault();
    const zone = document.getElementById('bqDropZone');
    if (zone) zone.classList.add('over');
  }

  function onDragLeave() {
    const zone = document.getElementById('bqDropZone');
    if (zone) zone.classList.remove('over');
  }

  // ── Submit all pending ─────────────────────────────────────────────────────
  async function submit() {
    const pending = _items.filter(it => it.status === STATUS.PENDING);
    if (!pending.length) {
      if (typeof showToast === 'function') showToast('No pending files to queue', 'warning');
      return;
    }
    const btn = document.getElementById('bqSubmitBtn');
    if (btn) btn.disabled = true;

    let queued = 0;
    for (let i = 0; i < pending.length; i++) {
      const item = pending[i];
      await _submitItem(item);
      if (item.status === STATUS.QUEUED || item.status === STATUS.RUNNING) queued++;
      if (i < pending.length - 1) await new Promise(r => setTimeout(r, 200));
    }

    if (btn) btn.disabled = false;
    _startPoll();
    _render();

    const total = pending.length;
    const failed = total - queued;
    const msg = failed ? `Batch: ${queued}/${total} queued (${failed} failed to queue)` : `Batch: ${queued} job${queued !== 1 ? 's' : ''} queued`;
    if (typeof showToast === 'function') showToast(msg, failed && !queued ? 'error' : 'success');
    if (typeof addEvent === 'function') addEvent(`batch_started: ${queued}/${total} jobs queued`, 'render');
  }

  async function _submitItem(item) {
    if (!item.filePath) {
      item.status = STATUS.FAILED;
      item.error = 'File path unavailable (browser restriction)';
      _render();
      return;
    }
    const payload = _buildPayload(item);
    try {
      const res  = await fetch('/api/render/process', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) {
        const err = (typeof _formatApiError === 'function') ? _formatApiError(data.detail) : String(data.detail || 'Failed');
        item.status = STATUS.FAILED;
        item.error  = err;
        if (typeof addEvent === 'function') addEvent(`batch_item_failed (queue): ${item.name}: ${err}`, 'render');
      } else {
        item.jobId  = data.job_id || null;
        item.status = STATUS.QUEUED;
        item.error  = '';
      }
    } catch (e) {
      item.status = STATUS.FAILED;
      item.error  = String(e);
      if (typeof addEvent === 'function') addEvent(`batch_item_failed (queue): ${item.name}: ${e}`, 'render');
    }
    _render();
  }

  // ── Poll loop ──────────────────────────────────────────────────────────────
  function _startPoll() {
    if (_pollTimer) return;
    _pollTimer = setInterval(_tick, POLL_INTERVAL_MS);
  }

  function _stopPollIfDone() {
    const active = _items.some(it => it.status === STATUS.QUEUED || it.status === STATUS.RUNNING);
    // STATUS.RECOVERED is terminal — counts as done for poll purposes
    if (!active && _pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  async function _tick() {
    const active = _items.filter(it => it.status === STATUS.QUEUED || it.status === STATUS.RUNNING);
    if (!active.length) { _stopPollIfDone(); return; }

    const updates = await Promise.allSettled(active.map(it => _fetchJobStatus(it)));
    let anyChange = false;
    updates.forEach((result, i) => {
      if (result.status === 'fulfilled' && result.value) anyChange = true;
    });
    if (anyChange) _render();
    _stopPollIfDone();

    const completed = _items.filter(it => it.status === STATUS.COMPLETED).length;
    const failed    = _items.filter(it => it.status === STATUS.FAILED).length;
    const total     = _items.length;
    const done      = _items.filter(it => it.status === STATUS.COMPLETED || it.status === STATUS.RECOVERED || it.status === STATUS.FAILED || it.status === STATUS.CANCELLED).length;
    if (done === total && total > 0 && !_pollTimer) {
      if (typeof addEvent === 'function') addEvent(`batch_completed: ${completed}/${total} succeeded, ${failed} failed`, 'render');
    }
  }

  async function _fetchJobStatus(item) {
    if (!item.jobId) return false;
    try {
      const res  = await fetch(`/api/jobs/${item.jobId}`);
      if (!res.ok) return false;
      const data = await res.json();
      const prev = item.status;
      const st   = String(data.status || '').toLowerCase();
      item.progress = Number(data.progress_percent || 0);
      if (st === 'running')   item.status = STATUS.RUNNING;
      if (st === 'completed') {
        const msg = String(data.message || '');
        const hasRecovery = msg.includes('[') && msg.includes('failed');
        item.status = hasRecovery ? STATUS.RECOVERED : STATUS.COMPLETED;
        item.error = hasRecovery ? msg.replace(/^Render completed\s*/, '') : '';
        if (typeof addEvent === 'function') addEvent(`batch_item_completed${hasRecovery ? ' (recovered)' : ''}: ${item.name}`, 'render');
      }
      if (st === 'completed_with_errors') {
        item.status = STATUS.RECOVERED;
        item.error = String(data.message || 'Completed with partial failures');
        if (typeof addEvent === 'function') addEvent(`batch_item_completed (recovered): ${item.name}`, 'render');
      }
      if (st === 'failed')    { item.status = STATUS.FAILED; item.error = String(data.message || 'Render failed'); if (typeof addEvent === 'function') addEvent(`batch_item_failed: ${item.name}: ${item.error}`, 'render'); }
      if (st === 'cancelled') item.status = STATUS.CANCELLED;
      return item.status !== prev || item.progress !== Number(data.progress_percent || 0);
    } catch (_) { return false; }
  }

  // ── Cancel / retry / remove ────────────────────────────────────────────────
  async function cancelItem(id) {
    const item = _items.find(it => it.id === id);
    if (!item) return;
    if (item.status === STATUS.PENDING) {
      item.status = STATUS.CANCELLED;
      _render();
      return;
    }
    if (!item.jobId) return;
    try {
      await fetch(`/api/render/${item.jobId}/cancel`, { method: 'POST' });
      item.status = STATUS.CANCELLED;
      if (typeof addEvent === 'function') addEvent(`batch_cancelled: ${item.name}`, 'render');
    } catch (_) {}
    _render();
  }

  async function retryItem(id) {
    const item = _items.find(it => it.id === id);
    if (!item) return;
    item.status   = STATUS.PENDING;
    item.jobId    = null;
    item.progress = 0;
    item.error    = '';
    _render();
    await _submitItem(item);
    _startPoll();
  }

  function removeItem(id) {
    const item = _items.find(it => it.id === id);
    if (!item || item.status === STATUS.RUNNING || item.status === STATUS.QUEUED) return;
    _items = _items.filter(it => it.id !== id);
    _render();
  }

  function clear() {
    _items = _items.filter(it => it.status === STATUS.RUNNING || it.status === STATUS.QUEUED);
    _render();
  }

  // ── Render UI ──────────────────────────────────────────────────────────────
  function _render() {
    const actEl  = document.getElementById('bqActions');
    const listEl = document.getElementById('bqList');
    if (!listEl) return;

    const hasPending = _items.some(it => it.status === STATUS.PENDING);
    if (actEl) actEl.style.display = _items.length ? '' : 'none';
    const submitBtn = document.getElementById('bqSubmitBtn');
    if (submitBtn) {
      submitBtn.disabled  = !hasPending;
      submitBtn.textContent = hasPending ? `Queue ${_items.filter(it=>it.status===STATUS.PENDING).length} file${_items.filter(it=>it.status===STATUS.PENDING).length!==1?'s':''}` : 'All Queued';
    }

    listEl.innerHTML = _items.map(item => {
      const stClass   = 'st-' + item.status;
      const cardClass = 'bqCard bq-' + item.status;
      const stLabel   = item.status === STATUS.RECOVERED ? 'Recovered' : item.status.charAt(0).toUpperCase() + item.status.slice(1);
      const pct       = Math.max(0, Math.min(100, item.progress || 0));
      const showBar   = item.status === STATUS.RUNNING || item.status === STATUS.QUEUED;
      const isRecovered = item.status === STATUS.RECOVERED;
      const actions   = _cardActions(item);
      const noteText  = isRecovered && item.error ? item.error : '';
      return `<div class="${cardClass}" data-bq-id="${item.id}">
  <div class="bqCardTop">
    <div class="bqCardName" title="${_esc(item.name)}">${_esc(item.name)}</div>
    <span class="bqCardStatus ${stClass}" title="${isRecovered ? 'Rendered using safe fallback' : ''}">${stLabel}${item.status === STATUS.RUNNING && pct > 0 ? ' ' + pct + '%' : ''}</span>
  </div>
  ${showBar ? `<div class="bqProgress"><div class="bqProgressBar" style="width:${pct}%"></div></div>` : ''}
  ${noteText ? `<div class="bqCardRecoveredNote">${_esc(noteText)}</div>` : ''}
  ${item.status === STATUS.FAILED && item.error ? `<div class="bqCardError">${_esc(item.error)}</div>` : ''}
  ${actions ? `<div class="bqCardActions">${actions}</div>` : ''}
</div>`;
    }).join('');
  }

  function _cardActions(item) {
    const parts = [];
    if (item.status === STATUS.RUNNING || item.status === STATUS.QUEUED) {
      parts.push(`<button class="bqActionBtn" onclick="BatchQueue.cancelItem('${item.id}')">Cancel</button>`);
    }
    if (item.status === STATUS.FAILED) {
      parts.push(`<button class="bqActionBtn" onclick="BatchQueue.retryItem('${item.id}')">Retry</button>`);
    }
    if (item.status !== STATUS.RUNNING && item.status !== STATUS.QUEUED) {
      parts.push(`<button class="bqActionBtn" onclick="BatchQueue.removeItem('${item.id}')">Remove</button>`);
    }
    return parts.join('');
  }

  function _esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Logging ────────────────────────────────────────────────────────────────
  function _log(event, detail) {
    if (typeof addEvent === 'function') addEvent(`${event}: ${detail}`, 'render');
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  function init() {
    _render();
  }

  return { init, openFilePicker, onFilesSelected, onDrop, onDragOver, onDragLeave, submit, cancelItem, retryItem, removeItem, clear };

})();
