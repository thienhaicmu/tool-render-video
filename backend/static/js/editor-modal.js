let _editorSessionId = null;
let _editorDuration = 0;
let _editorPendingPayload = null;
let _editorIsBatch = false;


function _editorSetStatus(msg) {
  const el = qs('editorStatusLine');
  if (el) el.textContent = msg;
}

function _editorSetDuration(dur) {
  _editorDuration = dur;
  qs('editorOrigDur').textContent = dur > 0 ? _fmtTime(dur) : '—';
  qs('editorDurBadge').textContent = dur > 0 ? `Thời lượng: ${_fmtTime(dur)}` : 'Thời lượng: —';
  if (dur > 0) {
    // Set OUT input default
    if (!qs('trimOutSec').value) qs('trimOutSec').value = Math.round(dur);
    onTrimChange('init');
  }
}

function _editorShowVideo() {
  const video = qs('editorVideo');
  const overlay = qs('editorVideoOverlay');
  video.style.display = 'block';
  overlay.style.display = 'none';
}

function _editorShowNoPreview(msg) {
  const overlay = qs('editorVideoOverlay');
  const spinner = qs('editorSpinner');
  const txt = qs('editorLoadingText');
  if (spinner) spinner.style.display = 'none';
  if (txt) txt.textContent = msg || 'Preview không khả dụng';
  // Add sub-text
  const sub = overlay.querySelector('div:last-child');
  if (sub && sub.style) sub.textContent = 'Trim và volume vẫn hoạt động bình thường ✓';
}

function _showEditorPanels() {
  // Controls are always in DOM now, just enable the apply button
  qs('editorApplyBtn').disabled = false;
  _editorSetStatus('Sẵn sàng. Chỉnh trim/volume rồi nhấn Apply & Render.');
}

function openEditor(sessionId, videoSrc, title, duration, pendingPayload, isBatch) {
  _editorSessionId = sessionId || null;
  _editorPendingPayload = pendingPayload;
  _editorIsBatch = !!isBatch;

  // Reset controls
  qs('trimInSlider').value  = 0;
  qs('trimOutSlider').value = 1000;
  qs('trimInSec').value  = 0;
  qs('trimOutSec').value = '';
  qs('editorVolumeSlider').value = 100;
  qs('editorVolumeNum').value    = 100;
  qs('editorVolInfo').textContent = '100%';
  qs('editorApplyBtn').disabled = true;
  qs('editorSourceName').textContent = title || 'Video';
  qs('editorOrigDur').textContent = '—';
  qs('editorAfterTrimDur').textContent = '—';
  qs('editorDurBadge').textContent = 'Thời lượng: —';
  qs('trimInDisplay').textContent  = '0:00:00';
  qs('trimOutDisplay').textContent = '—';
  qs('trimDurDisplay').textContent = '—';
  qs('trimSelected').style.left  = '0%';
  qs('trimSelected').style.width = '100%';

  // Reset video area to loading state
  const video = qs('editorVideo');
  video.style.display = 'none';
  video.src = '';
  const overlay = qs('editorVideoOverlay');
  overlay.style.display = 'flex';
  const spinner = qs('editorSpinner');
  if (spinner) spinner.style.display = 'block';
  qs('editorLoadingText').textContent = 'Đang download video…';

  _editorSetStatus('Đang chuẩn bị video…');
  qs('editorModal').classList.remove('hiddenView');

  if (duration > 0) {
    _editorSetDuration(duration);
    _showEditorPanels();
  }

  if (videoSrc) {
    video.src = videoSrc;
    video.onloadedmetadata = () => {
      const dur = video.duration || duration;
      _editorSetDuration(dur);
      _editorShowVideo();
      _showEditorPanels();
      _editorSetStatus('Video đã load. Kéo thanh IN/OUT để trim, hoặc nhập số giây.');
    };
    video.onerror = () => {
      _editorShowNoPreview('Preview không khả dụng');
      _showEditorPanels();
      _editorSetStatus('Preview lỗi codec — trim & volume vẫn hoạt động. Nhấn Apply khi xong.');
    };
  } else if (!videoSrc && duration <= 0) {
    // No info yet — loading state, panels active so user can skip
    qs('editorApplyBtn').disabled = false;
    _editorSetStatus('Đang download… Có thể Skip để render ngay.');
  }
}

function onTrimChange(source) {
  const dur = _editorDuration;
  let inV  = Number(qs('trimInSlider').value);
  let outV = Number(qs('trimOutSlider').value);

  if (source === 'input-in') {
    const inSec = Math.max(0, Number(qs('trimInSec').value) || 0);
    if (dur > 0) inV = Math.round(Math.min(inSec / dur, 0.999) * 1000);
    qs('trimInSlider').value = inV;
  } else if (source === 'input-out') {
    const rawOut = qs('trimOutSec').value;
    const outSec = rawOut === '' ? dur : Math.max(0, Number(rawOut) || dur);
    if (dur > 0) outV = Math.round(Math.min(outSec / dur, 1.0) * 1000);
    qs('trimOutSlider').value = outV;
  } else {
    // slider moved — update inputs
    if (dur > 0) {
      qs('trimInSec').value  = Math.round((inV  / 1000) * dur);
      const rawOut = Math.round((outV / 1000) * dur);
      qs('trimOutSec').value = rawOut >= Math.round(dur) ? '' : rawOut;
    }
  }

  const MIN_GAP = 5;
  if (inV >= outV - MIN_GAP) {
    if (source === 'input-in' || document.activeElement === qs('trimInSlider')) {
      inV = Math.max(0, outV - MIN_GAP);
      qs('trimInSlider').value = inV;
    } else {
      outV = Math.min(1000, inV + MIN_GAP);
      qs('trimOutSlider').value = outV;
    }
  }

  const inSec  = dur > 0 ? (inV  / 1000) * dur : 0;
  const outSec = dur > 0 ? (outV / 1000) * dur : 0;
  const selSec = outSec - inSec;

  qs('trimInDisplay').textContent  = _fmtTime(inSec);
  qs('trimOutDisplay').textContent = dur > 0 ? _fmtTime(outSec) : '—';
  qs('trimDurDisplay').textContent = dur > 0 ? _fmtTime(selSec) : '—';
  qs('editorAfterTrimDur').textContent = dur > 0 ? _fmtTime(selSec) : '—';

  // Visual bar
  qs('trimSelected').style.left  = `${inV  * 0.1}%`;
  qs('trimSelected').style.width = `${(outV - inV) * 0.1}%`;
}

function setTrimIn() {
  const video = qs('editorVideo');
  if (!video || isNaN(video.duration)) {
    _editorSetStatus('Cần video đang phát để dùng Set IN at playhead.');
    return;
  }
  const v = Math.round((video.currentTime / video.duration) * 1000);
  qs('trimInSlider').value = Math.min(v, Number(qs('trimOutSlider').value) - 5);
  onTrimChange('slider');
}

function setTrimOut() {
  const video = qs('editorVideo');
  if (!video || isNaN(video.duration)) {
    _editorSetStatus('Cần video đang phát để dùng Set OUT at playhead.');
    return;
  }
  const v = Math.round((video.currentTime / video.duration) * 1000);
  qs('trimOutSlider').value = Math.max(v, Number(qs('trimInSlider').value) + 5);
  onTrimChange('slider');
}

function resetTrim() {
  qs('trimInSlider').value  = 0;
  qs('trimOutSlider').value = 1000;
  qs('trimInSec').value  = 0;
  qs('trimOutSec').value = _editorDuration > 0 ? '' : '';
  onTrimChange('init');
}

function onVolumeChange() {
  const vol = Number(qs('editorVolumeSlider').value);
  qs('editorVolumeNum').value     = vol;
  qs('editorVolInfo').textContent = `${vol}%`;
  const video = qs('editorVideo');
  if (video) video.volume = Math.min(1, vol / 100);
}

function onVolumeNumInput() {
  const vol = Math.max(0, Math.min(200, Number(qs('editorVolumeNum').value) || 100));
  qs('editorVolumeSlider').value  = vol;
  qs('editorVolInfo').textContent = `${vol}%`;
  const video = qs('editorVideo');
  if (video) video.volume = Math.min(1, vol / 100);
}

function setVolume(val) {
  qs('editorVolumeSlider').value = val;
  qs('editorVolumeNum').value    = val;
  qs('editorVolInfo').textContent = `${val}%`;
  const video = qs('editorVideo');
  if (video) video.volume = Math.min(1, val / 100);
}

function closeEditor() {
  qs('editorModal').classList.add('hiddenView');
  const video = qs('editorVideo');
  if (video) { video.pause(); video.src = ''; video.style.display = 'none'; }
}

function cancelEditor() {
  closeEditor();
  _editorPendingPayload = null;
  _editorSessionId = null;
  setRenderActionBusy(false);
  addEvent('Editor: huỷ.', 'render');
}

function skipEditor() {
  const payload = _editorPendingPayload;
  closeEditor();
  if (payload) {
    addEvent('Editor: skip, render không trim/volume.', 'render');
    _submitRenderPayload(payload, _editorIsBatch);
  }
}

async function applyEditsAndRender() {
  const payload = _editorPendingPayload;
  if (!payload) { closeEditor(); return; }
  const dur  = _editorDuration;
  const inV  = Number(qs('trimInSlider').value);
  const outV = Number(qs('trimOutSlider').value);
  const inSec  = dur > 0 ? (inV  / 1000) * dur : Number(qs('trimInSec').value)  || 0;
  const outSec = dur > 0 ? (outV / 1000) * dur : Number(qs('trimOutSec').value) || 0;
  const vol    = Number(qs('editorVolumeSlider').value) / 100;
  payload.edit_session_id = _editorSessionId || null;
  payload.edit_trim_in    = inSec  > 0.5 ? inSec  : 0;
  payload.edit_trim_out   = (outSec > 0.5 && outV < 1000) ? outSec : 0;
  payload.edit_volume     = vol;
  addEvent(`Editor: trim ${_fmtTime(inSec)} → ${_fmtTime(outSec)} | volume ${Math.round(vol*100)}%`, 'render');
  closeEditor();
  await _submitRenderPayload(payload, _editorIsBatch);
}

function _formatApiError(detail) {
  if (!detail) return 'unknown error';
  // Pydantic 422: detail is an array of {loc, msg, type} objects
  if (Array.isArray(detail)) {
    return detail.map(e => {
      const field = Array.isArray(e.loc) ? e.loc.filter(x => x !== 'body').join('.') : '';
      return field ? `${field}: ${e.msg}` : (e.msg || JSON.stringify(e));
    }).join(' | ');
  }
  // HTTPException 400/500: detail is a plain string
  return typeof detail === 'string' ? detail : JSON.stringify(detail);
}

async function _submitRenderPayload(payload, isBatch) {
  const endpoint = isBatch ? '/api/render/process/batch' : '/api/render/process';
  const res  = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok) {
    const errMsg = _formatApiError(data.detail);
    addEvent(`Start render failed: ${errMsg}`, 'render');
    setRenderActionBusy(false);
    return { ok: false, error: errMsg };
  }
  currentJobId = isBatch ? data.batch_id : data.job_id;
  activeJobStartedAt = Date.now();
  lastStage = ''; lastMessage = ''; lastStatus = ''; lastProgressBucket = -1;
  // Reset smooth animation state for fresh job
  _jobTargetPct = 0; _jobDisplayPct = 0;
  for(const k of Object.keys(_partTarget)) delete _partTarget[k];
  for(const k of Object.keys(_partDisplay)) delete _partDisplay[k];
  setRenderActionBusy(true);
  setHeaderJob('Render running');
  addEvent(isBatch ? `Queued render batch (${data.count || '?'} links)` : 'Queued render job', 'render');
  startPolling();
  return { ok: true, error: null };
}
