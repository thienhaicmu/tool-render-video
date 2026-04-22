// ── Editor View (full-screen) ───────────────────────────────────────────────
let _ev = {
  sessionId: null, exportDir: null, duration: 0, pendingPayload: null,
  videoReady: false, subAnimTimer: null, subWordIdx: 0, bgmPath: null,
  textLayers: [], selectedTextLayer: 0,
  sourceMode: null, sourceUrl: null,
};
const EV_MAX_TEXT_LAYERS = 8;
const EV_TEXT_POS_TO_XY = {
  'top-left': [5, 5],
  'top-center': [50, 5],
  'top-right': [95, 5],
  'center': [50, 50],
  'bottom-left': [5, 90],
  'bottom-center': [50, 90],
  'bottom-right': [95, 90],
};

// ── TEXT LAYER FACTORY + DEFAULTS ────────────────────────────────────────────
function evPresetToXY(position) {
  return EV_TEXT_POS_TO_XY[position] || EV_TEXT_POS_TO_XY['bottom-center'];
}

function _evNewTextLayer(order) {
  const duration = Number(_ev.duration || 0);
  return {
    id: `txt_${Date.now()}_${Math.floor(Math.random() * 9999)}`,
    text: 'New Text',
    font_family: 'Bungee',
    font_size: 48,
    color: '#ffffff',
    position: 'bottom-center',
    x_percent: 50,
    y_percent: 90,
    alignment: 'center',
    bold: false,
    outline: { enabled: true, thickness: 2 },
    shadow: { enabled: false, offset_x: 2, offset_y: 2 },
    background: { enabled: false, color: '#00000099', padding: 10 },
    start_time: 0,
    end_time: duration > 0 ? Math.round(duration * 10) / 10 : 0,
    order: Number(order || 0),
  };
}

function evInitTextLayers() {
  _ev.textLayers = [];
  _ev.selectedTextLayer = 0;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

function evAddTextLayer() {
  if ((_ev.textLayers || []).length >= EV_MAX_TEXT_LAYERS) {
    addEvent(`Text overlay limit reached (${EV_MAX_TEXT_LAYERS}).`, 'render');
    showToast(`Max text layers (${EV_MAX_TEXT_LAYERS}) reached`, 'info'); // log panel hidden in editor view
    return;
  }
  _ev.textLayers.push(_evNewTextLayer(_ev.textLayers.length));
  _ev.selectedTextLayer = _ev.textLayers.length - 1;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

function evApplyLayerPresetPosition() {
  const [x, y] = evPresetToXY(qs('evTxtPos')?.value || 'bottom-center');
  if (qs('evTxtX')) qs('evTxtX').value = x;
  if (qs('evTxtY')) qs('evTxtY').value = y;
  evUpdateSelectedTextLayer();
}

function evSetLayerX(val) {
  if (qs('evTxtX')) qs('evTxtX').value = val;
  evUpdateSelectedTextLayer();
}

function evSelectTextLayer(index) {
  if (index < 0 || index >= _ev.textLayers.length) return;
  _ev.selectedTextLayer = index;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
  _evFlashSelectedLayer();
}

function _evFlashSelectedLayer() {
  const overlay = qs('evTextLayersOverlay');
  if (!overlay) return;
  const sel = overlay.querySelector('.evTLSelected');
  if (!sel) return;
  sel.classList.remove('evTLFlash');
  void sel.offsetWidth;
  sel.classList.add('evTLFlash');
  setTimeout(() => sel.classList.remove('evTLFlash'), 170);
}

function evMoveTextLayer(index, dir) {
  const j = index + dir;
  if (index < 0 || j < 0 || index >= _ev.textLayers.length || j >= _ev.textLayers.length) return;
  const arr = _ev.textLayers;
  [arr[index], arr[j]] = [arr[j], arr[index]];
  _ev.selectedTextLayer = j;
  arr.forEach((l, i) => l.order = i);
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

function evDeleteTextLayer(index) {
  if (index < 0 || index >= _ev.textLayers.length) return;
  _ev.textLayers.splice(index, 1);
  _ev.textLayers.forEach((l, i) => l.order = i);
  _ev.selectedTextLayer = Math.max(0, Math.min(_ev.selectedTextLayer, _ev.textLayers.length - 1));
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

// ── TEXT LAYER LIST RENDER + FORM SYNC ───────────────────────────────────────
function evRenderTextLayerList() {
  const box = qs('evTextLayerList');
  if (!box) return;
  document.getElementById('appInspector')?.classList.toggle('inspHasLayers', !!_ev.textLayers.length);
  if (!_ev.textLayers.length) {
    box.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No text layer configured.</div>';
    const editor = qs('evTextLayerEditor');
    if (editor) editor.style.display = 'none';
    return;
  }
  const selected = _ev.selectedTextLayer;
  box.innerHTML = _ev.textLayers.map((layer, i) => {
    const name = String(layer.text || '').trim() || '(empty)';
    const pos = String(layer.position || 'bottom-center');
    const xp = Math.max(0, Math.min(100, Number(layer.x_percent ?? 50)));
    const yp = Math.max(0, Math.min(100, Number(layer.y_percent ?? 90)));
    const st = Number(layer.start_time || 0);
    const et = Number(layer.end_time || 0);
    const timing = et > 0 ? `${st.toFixed(1)}s→${et.toFixed(1)}s` : `${st.toFixed(1)}s→end`;
    return `<div class="evLayerItem ${selected===i?'active':''}">
      <button class="evTinyBtn" onclick="evSelectTextLayer(${i})" style="flex:1;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${i+1}. ${esc(name)} <span style="opacity:.7">• ${esc(pos)} (${xp.toFixed(0)}%,${yp.toFixed(0)}%) • ${timing}</span></button>
      <button class="evTinyBtn" onclick="evMoveTextLayer(${i},-1)" title="Move forward (render on top)">↑ Forward</button>
      <button class="evTinyBtn" onclick="evMoveTextLayer(${i},1)" title="Move behind (render below)">↓ Behind</button>
      <button class="evTinyBtn" onclick="evDeleteTextLayer(${i})">✕</button>
    </div>`;
  }).join('');
  const editor = qs('evTextLayerEditor');
  if (editor) editor.style.display = 'block';
  const cur = _ev.textLayers[selected];
  if (!cur) return;
  qs('evTxtContent').value = cur.text || '';
  qs('evTxtFont').value = cur.font_family || 'Bungee';
  qs('evTxtSize').value = Number(cur.font_size || 42);
  qs('evTxtColor').value = cur.color || '#ffffff';
  qs('evTxtPos').value = cur.position || 'bottom-center';
  qs('evTxtX').value = Math.max(0, Math.min(100, Number(cur.x_percent ?? evPresetToXY(cur.position || 'bottom-center')[0])));
  qs('evTxtY').value = Math.max(0, Math.min(100, Number(cur.y_percent ?? evPresetToXY(cur.position || 'bottom-center')[1])));
  qs('evTxtAlign').value = cur.alignment || 'center';
  qs('evTxtStartTime').value = Number(cur.start_time || 0);
  qs('evTxtEndTime').value = Number(cur.end_time || 0);
  qs('evTxtBold').checked = !!cur.bold;
  qs('evTxtOutlineEnabled').checked = !!cur.outline?.enabled;
  qs('evTxtOutlineThickness').value = Number(cur.outline?.thickness ?? 2);
  qs('evTxtShadowEnabled').checked = !!cur.shadow?.enabled;
  qs('evTxtShadowX').value = Number(cur.shadow?.offset_x ?? 2);
  qs('evTxtShadowY').value = Number(cur.shadow?.offset_y ?? 2);
  qs('evTxtBgEnabled').checked = !!cur.background?.enabled;
  qs('evTxtBgColor').value = String(cur.background?.color || '#00000099').slice(0, 7);
  qs('evTxtBgPadding').value = Number(cur.background?.padding ?? 10);
}

function evUpdateSelectedTextLayer() {
  const i = _ev.selectedTextLayer;
  const layer = _ev.textLayers[i];
  if (!layer) return;
  layer.text = String(qs('evTxtContent')?.value || '');
  layer.font_family = qs('evTxtFont')?.value || 'Bungee';
  layer.font_size = Math.max(12, Math.min(300, Number(qs('evTxtSize')?.value || 48)));
  layer.color = qs('evTxtColor')?.value || '#ffffff';
  layer.position = qs('evTxtPos')?.value || 'bottom-center';
  layer.x_percent = Math.max(0, Math.min(100, Number(qs('evTxtX')?.value || 50)));
  layer.y_percent = Math.max(0, Math.min(100, Number(qs('evTxtY')?.value || 90)));
  layer.alignment = qs('evTxtAlign')?.value || 'center';
  const startTime = Math.max(0, Number(qs('evTxtStartTime')?.value || 0));
  const rawEndTime = Math.max(0, Number(qs('evTxtEndTime')?.value || 0));
  let endTime = rawEndTime;
  if (endTime > 0 && endTime <= startTime) {
    endTime = startTime + 0.1;
    if (qs('evTxtEndTime')) qs('evTxtEndTime').value = String(Math.round(endTime * 10) / 10);
  }
  layer.start_time = startTime;
  layer.end_time = endTime;
  layer.bold = !!qs('evTxtBold')?.checked;
  layer.outline = {
    enabled: !!qs('evTxtOutlineEnabled')?.checked,
    thickness: Math.max(0, Math.min(8, Number(qs('evTxtOutlineThickness')?.value || 0))),
  };
  layer.shadow = {
    enabled: !!qs('evTxtShadowEnabled')?.checked,
    offset_x: Math.max(-20, Math.min(20, Number(qs('evTxtShadowX')?.value || 0))),
    offset_y: Math.max(-20, Math.min(20, Number(qs('evTxtShadowY')?.value || 0))),
  };
  const bgHex = qs('evTxtBgColor')?.value || '#000000';
  layer.background = {
    enabled: !!qs('evTxtBgEnabled')?.checked,
    color: `${bgHex}99`,
    padding: Math.max(0, Math.min(64, Number(qs('evTxtBgPadding')?.value || 0))),
  };
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

// ── TEXT LAYER PREVIEW (video overlay) ───────────────────────────────────────
function evRenderTextLayerPreview() {
  const overlay = qs('evTextLayersOverlay');
  if (!overlay) return;
  const layers = (_ev.textLayers || []).slice().sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
  if (!layers.length) {
    overlay.innerHTML = '';
    return;
  }
  // Scale font sizes relative to 1080px reference width so preview matches render output
  const overlayRect = overlay.getBoundingClientRect();
  const scale = overlayRect.width > 0 ? overlayRect.width / 1080 : 1;
  const now = Number(qs('evVideo')?.currentTime || 0);
  overlay.innerHTML = layers.filter((l) => {
    const st = Math.max(0, Number(l.start_time || 0));
    const et = Math.max(0, Number(l.end_time || 0));
    if (now < st) return false;
    if (et > 0 && now >= et) return false;
    return true;
  }).map((l) => {
    const origIdx = _ev.textLayers.findIndex(tl => tl.id === l.id);
    const isSelected = origIdx === _ev.selectedTextLayer;
    const defXY = evPresetToXY(l.position || 'bottom-center');
    const x = Math.max(0, Math.min(100, Number(l.x_percent ?? defXY[0])));
    const y = Math.max(0, Math.min(100, Number(l.y_percent ?? defXY[1])));
    const style = [];
    style.push(`left:${x}%`);
    style.push(`top:${y}%`);
    // translate(-x%, -y%) so the anchor point tracks (w-text_w)*x/100 — matches ffmpeg drawtext formula exactly
    style.push(`transform:translate(-${x}%,-${y}%)`);
    style.push(`font-family:'${String(l.font_family || 'Bungee').replace(/'/g,'')}','Arial',sans-serif`);
    const scaledSize = Math.max(8, Math.round(Number(l.font_size || 42) * scale));
    style.push(`font-size:${scaledSize}px`);
    style.push(`color:${l.color || '#ffffff'}`);
    style.push(`font-weight:${l.bold ? '700' : '500'}`);
    style.push(`text-align:${l.alignment || 'center'}`);
    const outlinePx = (l.outline?.enabled ? Number(l.outline?.thickness || 0) : 0);
    if (outlinePx > 0) style.push(`-webkit-text-stroke:${outlinePx}px #000`);
    if (l.shadow?.enabled) style.push(`text-shadow:${Number(l.shadow.offset_x||2)}px ${Number(l.shadow.offset_y||2)}px 4px rgba(0,0,0,.75)`);
    if (l.background?.enabled) {
      style.push(`background:${l.background.color || '#00000099'}`);
      style.push(`padding:${Math.max(0, Number(l.background.padding || 0))}px`);
      style.push('border-radius:6px');
    }
    const selClass = isSelected ? ' evTLSelected' : '';
    return `<div class="evTextLayerPreview${selClass}" onmousedown="evTextLayerDragStart(event,'${l.id}')" style="${style.join(';')}">${esc(String(l.text || ''))}</div>`;
  }).join('');
  overlay.classList.toggle('evHasSelection', !!overlay.querySelector('.evTLSelected'));
}

// ── TEXT LAYER DRAG ───────────────────────────────────────────────────────────
function evTextLayerDragStart(e, layerId) {
  e.preventDefault(); e.stopPropagation();
  const layerIdx = _ev.textLayers.findIndex(tl => tl.id === layerId);
  if (layerIdx < 0) return;
  const layer = _ev.textLayers[layerIdx];
  _ev.selectedTextLayer = layerIdx;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
  const overlay = qs('evTextLayersOverlay');
  if (overlay) overlay.classList.add('evTLDragging');
  document.body.style.cursor = 'grabbing';
  const rect = overlay.getBoundingClientRect();
  const startClientX = e.clientX, startClientY = e.clientY;
  const startXPct = Number(layer.x_percent ?? 50);
  const startYPct = Number(layer.y_percent ?? 90);
  function onMove(me) {
    const dx = (me.clientX - startClientX) / rect.width * 100;
    const dy = (me.clientY - startClientY) / rect.height * 100;
    layer.x_percent = Math.round(Math.max(0, Math.min(100, startXPct + dx)) * 10) / 10;
    layer.y_percent = Math.round(Math.max(0, Math.min(100, startYPct + dy)) * 10) / 10;
    if (qs('evTxtX')) qs('evTxtX').value = layer.x_percent.toFixed(1);
    if (qs('evTxtY')) qs('evTxtY').value = layer.y_percent.toFixed(1);
    evRenderTextLayerPreview();
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    const dragOverlay = qs('evTextLayersOverlay');
    if (dragOverlay) dragOverlay.classList.remove('evTLDragging');
    document.body.style.cursor = '';
    evRenderTextLayerList();
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function evToggleBgmFields() {
  const el = qs('evBgmFields');
  if (el) el.style.display = qs('evBgmEnable').checked ? 'flex' : 'none';
}
function evPickBgmFile() { qs('ev_bgm_file_picker')?.click(); }
async function evOnBgmPicked(ev) {
  const file = ev?.target?.files?.[0];
  if (!file) return;
  const realPath = String(file.path || '').trim();
  if (realPath) {
    _ev.bgmPath = realPath;
    if (qs('evBgmPath')) qs('evBgmPath').value = realPath;
  } else {
    // Browser: upload
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch('/api/upload-file', { method:'POST', body: fd });
      if (r.ok) { const d = await r.json(); _ev.bgmPath = d.path; if (qs('evBgmPath')) qs('evBgmPath').value = d.path || file.name; }
    } catch(_) { if (qs('evBgmPath')) qs('evBgmPath').value = file.name; }
  }
}

/* ── Info strip helper ────────────────────────────────────── */
// ── EDITOR OPEN / CLOSE / REOPEN ─────────────────────────────────────────────
function _evUpdateInfoStrip() {
  const dot = qs('evSessionDot');
  const sessionEl = qs('evInfoSession');
  const outputEl = qs('evInfoOutput');
  if (dot) {
    if (_ev.sessionId) { dot.classList.add('active'); } else { dot.classList.remove('active'); }
  }
  if (sessionEl) sessionEl.textContent = _ev.sessionId ? 'Active (may expire)' : '—';
  if (outputEl) outputEl.textContent = _ev.exportDir ? _ev.exportDir.replace(/\\/g, '/') : '—';
}

/* ── Open editor view ─────────────────────────────────────── */
async function openEditorView(sourceMode, urlOrPath, pendingPayload) {
  _ev.sessionId = null;
  _ev.exportDir = null;
  _ev.duration = 0;
  _ev.pendingPayload = pendingPayload;
  _ev.videoReady = false;
  _ev.sourceMode = sourceMode;
  _ev.sourceUrl = urlOrPath;

  // Init editor settings with defaults (editor is source of truth for all render params)

  setView('editor');
  qs('evSourceName').textContent = urlOrPath || '…';
  qs('evLoadingOverlay').style.display = 'flex';
  qs('evLoadingText').textContent = sourceMode === 'youtube' ? 'Đang tải video từ YouTube…' : 'Đang phân tích video…';
  qs('evVideo').style.display = 'none';
  qs('evSubOverlay').style.display = 'none';  // hide until video ready
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = '▶ Bắt đầu Render';
  if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'none';
  qs('evStatusLine').textContent = sourceMode === 'youtube' ? '⏳ Download YouTube — có thể mất 30–60 giây…' : '⏳ Đang chuẩn bị preview…';
  qs('evStatusLine').style.color = '';
  _evUpdateInfoStrip();
  _evResetTrimUI();
  evUpdateSubPreview();
  evInitTextLayers();
  evUpdateAspectRatio();  // apply aspect ratio frame from dropdown

  try {
    const pr = await fetch('/api/render/prepare-source', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ source_mode: sourceMode, youtube_url: sourceMode === 'youtube' ? urlOrPath : null, source_video_path: sourceMode === 'local' ? urlOrPath : null }),
    });
    const pd = await pr.json();
    if (!pr.ok) throw new Error(_formatApiError(pd.detail));
    _ev.sessionId = pd.session_id;
    _ev.exportDir = pd.export_dir || null;
    _ev.duration  = pd.duration || 0;
    qs('evSourceName').textContent = pd.title || urlOrPath;
    if (qs('evTitleOverlayText') && !String(qs('evTitleOverlayText').value || '').trim()) {
      qs('evTitleOverlayText').value = String(pd.title || '');
    }
    if (pendingPayload) pendingPayload.edit_session_id = pd.session_id;
    _evSetDuration(_ev.duration);
    _evUpdateInfoStrip();

    // Always use backend preview endpoint (H.264 transcoded, range-supported)
    _evLoadVideo(`/api/render/preview-video/${pd.session_id}`);

  } catch(err) {
    qs('evLoadingText').textContent = `Lỗi: ${err.message}`;
    qs('evStartBtn').disabled = false;
    qs('evStatusLine').textContent = `Lỗi chuẩn bị video. Vẫn có thể render.`;
    addEvent(`Editor prepare error: ${err.message}`, 'render');
    if (_ev.duration > 0) _evSetDuration(_ev.duration);
  }
}

/* ── Open editor with pre-downloaded YouTube session ──────── */
function openEditorView_withSession(pd, urlOrPath, pendingPayload) {
  _ev.sessionId = pd.session_id;
  _ev.exportDir = pd.export_dir || null;
  _ev.duration = pd.duration || 0;
  _ev.pendingPayload = pendingPayload;
  _ev.videoReady = false;
  _ev.sourceMode = _ev.sourceMode || 'youtube';
  _ev.sourceUrl = _ev.sourceUrl || urlOrPath;

  setView('editor');
  qs('evSourceName').textContent = pd.title || urlOrPath || '…';
  if (qs('evTitleOverlayText') && !String(qs('evTitleOverlayText').value || '').trim()) {
    qs('evTitleOverlayText').value = String(pd.title || '');
  }
  qs('evLoadingOverlay').style.display = 'flex';
  qs('evLoadingText').textContent = 'Đang tải preview…';
  qs('evVideo').style.display = 'none';
  qs('evSubOverlay').style.display = 'none';
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = '▶ Bắt đầu Render';
  if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'none';
  qs('evStatusLine').textContent = '⏳ Đang tải preview video…';
  qs('evStatusLine').style.color = '';
  _evUpdateInfoStrip();
  _evResetTrimUI();
  evUpdateSubPreview();
  evInitTextLayers();
  evUpdateAspectRatio();

  if (pendingPayload) pendingPayload.edit_session_id = pd.session_id;
  _evSetDuration(_ev.duration);
  _evLoadVideo(`/api/render/preview-video/${pd.session_id}`);

  // Restore start button
  const btn = qs('start_render_btn');
  if (btn) { btn.disabled = false; btn.textContent = '▶ Tiếp theo: Chỉnh sửa & Render'; btn.style.opacity = '1'; }
}

function _evLoadVideo(src) {
  const video = qs('evVideo');
  video.src = src;
  video.onloadedmetadata = () => {
    _ev.duration = video.duration || _ev.duration;
    _evSetDuration(_ev.duration);
    qs('evLoadingOverlay').style.display = 'none';
    video.style.display = 'block';
    _ev.videoReady = true;
    qs('evStartBtn').disabled = false;
    qs('evStatusLine').textContent = 'Video sẵn sàng. Chỉnh sửa rồi nhấn Bắt đầu Render.';
    qs('evSubOverlay').style.display = 'flex';
    // Sync subtitle overlay and start animation
    _evSyncSubOverlay();
    requestAnimationFrame(() => { _evStartSubAnim(); });
    video.addEventListener('timeupdate', _evOnTimeUpdate);
  };
  video.onerror = () => {
    qs('evLoadingText').textContent = 'Preview không khả dụng';
    qs('evLoadingOverlay').querySelector('div:last-child').textContent = 'Trim & subtitle vẫn hoạt động ✓';
    qs('evLoadingOverlay').querySelector('.editorSpinner').style.display = 'none';
    qs('evStartBtn').disabled = false;
    qs('evStatusLine').textContent = 'Preview lỗi codec — mọi chức năng vẫn hoạt động.';
    // Show subtitle preview even without video (over loading overlay)
    qs('evSubOverlay').style.display = 'flex';
    qs('evSubOverlay').style.left = '0';
    qs('evSubOverlay').style.right = '0';
    qs('evSubOverlay').style.bottom = '15%';
    qs('evSubOverlay').style.zIndex = '6'; // above loading overlay
    _evStartSubAnim();
  };
}

function _evOnTimeUpdate() {
  const video = qs('evVideo');
  if (!video || !_ev.duration) return;
  const pct = (video.currentTime / _ev.duration) * 100;
  qs('evTimelineProgress').style.width = `${pct}%`;
  qs('evCurTime').textContent = _fmtTime(video.currentTime);
  evRenderTextLayerPreview();
}

function evSeekClick(e) {
  const bar = qs('evTimelineBarWrap');
  const video = qs('evVideo');
  if (!video || !_ev.duration) return;
  const rect = bar.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  video.currentTime = pct * _ev.duration;
}

function evTogglePlay() {
  const video = qs('evVideo');
  if (!video) return;
  if (video.paused) { video.play(); qs('evPlayBtn').textContent = '⏸'; }
  else { video.pause(); qs('evPlayBtn').textContent = '▶'; }
}

/* ── Duration setup ───────────────────────────────────────── */
function _evSetDuration(dur) {
  _ev.duration = dur;
  qs('evTotalTime').textContent = _fmtTime(dur);
  if (!qs('evTrimOutSec').value) qs('evTrimOutSec').value = Math.round(dur);
  _evUpdateTrimUI();
}

/* ── Trim ─────────────────────────────────────────────────── */
function _evResetTrimUI() {
  qs('evTrimInSlider').value  = 0;
  qs('evTrimOutSlider').value = 1000;
  qs('evTrimInSec').value  = 0;
  qs('evTrimOutSec').value = '';
  _evUpdateTrimUI();
}

function evTrimSliderChange() {
  const dur = _ev.duration;
  let inV  = Number(qs('evTrimInSlider').value);
  let outV = Number(qs('evTrimOutSlider').value);
  if (inV >= outV - 5) {
    if (document.activeElement === qs('evTrimInSlider')) inV = outV - 5;
    else outV = inV + 5;
    qs('evTrimInSlider').value  = inV;
    qs('evTrimOutSlider').value = outV;
  }
  qs('evTrimInSec').value  = dur > 0 ? Math.round((inV/1000)*dur) : 0;
  const outSec = dur > 0 ? Math.round((outV/1000)*dur) : 0;
  qs('evTrimOutSec').value = outV >= 1000 ? '' : outSec;
  _evUpdateTrimUI();
}

function evTrimSecChange() {
  const dur = _ev.duration;
  if (dur <= 0) return;
  const inSec  = Math.max(0, Number(qs('evTrimInSec').value) || 0);
  const outRaw = qs('evTrimOutSec').value;
  const outSec = outRaw === '' ? dur : Math.max(inSec+1, Number(outRaw) || dur);
  qs('evTrimInSlider').value  = Math.round(Math.min(inSec/dur, .999)*1000);
  qs('evTrimOutSlider').value = Math.round(Math.min(outSec/dur, 1)*1000);
  _evUpdateTrimUI();
}

function _evUpdateTrimUI() {
  const dur  = _ev.duration;
  const inV  = Number(qs('evTrimInSlider').value);
  const outV = Number(qs('evTrimOutSlider').value);
  const inSec  = dur > 0 ? (inV/1000)*dur : 0;
  const outSec = dur > 0 ? (outV/1000)*dur : dur;
  const sel    = outSec - inSec;
  qs('evTrimFill').style.left  = `${inV*0.1}%`;
  qs('evTrimFill').style.width = `${(outV-inV)*0.1}%`;
  qs('evTrimRegion').style.left  = `${inV*0.1}%`;
  qs('evTrimRegion').style.width = `${(outV-inV)*0.1}%`;
  qs('evTrimInfo').textContent = dur > 0
    ? `${_fmtTime(inSec)} → ${_fmtTime(outSec)} (${_fmtTime(sel)})`
    : 'Toàn bộ video';
}

function evSetTrimIn() {
  const v = qs('evVideo'); if (!v||isNaN(v.duration)) return;
  qs('evTrimInSlider').value = Math.round((v.currentTime/v.duration)*1000);
  qs('evTrimInSec').value = Math.round(v.currentTime);
  _evUpdateTrimUI();
}
function evSetTrimOut() {
  const v = qs('evVideo'); if (!v||isNaN(v.duration)) return;
  qs('evTrimOutSlider').value = Math.round((v.currentTime/v.duration)*1000);
  qs('evTrimOutSec').value = Math.round(v.currentTime);
  _evUpdateTrimUI();
}
function evResetTrim() { _evResetTrimUI(); }

/* ── Volume ───────────────────────────────────────────────── */
function evVolumeSliderChange() {
  const v = Number(qs('evVolume').value);
  qs('evVolumeNum').value = v;
  const vid = qs('evVideo'); if (vid) vid.volume = Math.min(1,v/100);
}
function evVolumeNumChange() {
  const v = Math.max(0,Math.min(200, Number(qs('evVolumeNum').value)||100));
  qs('evVolume').value = v;
  const vid = qs('evVideo'); if (vid) vid.volume = Math.min(1,v/100);
}
function evSetVolume(val) {
  qs('evVolume').value = val; qs('evVolumeNum').value = val;
  const vid = qs('evVideo'); if (vid) vid.volume = Math.min(1,val/100);
}

/* ── Subtitle live preview ────────────────────────────────── */
const _EV_DEMO_WORDS = ['POV:', 'never', 'gonna', 'give', 'you', 'up', '🔥'];

/* ── Sync subtitle overlay position ────────────────────────── */
/* Overlay is inside .evVideoFrame which has exact aspect ratio  */
/* so bottom: X% is relative to frame height == output height   */
function _evSyncSubOverlay() {
  const overlay = qs('evSubOverlay');
  if (!overlay) return;
  const posY = Number(qs('evSubPos')?.value || 15);
  overlay.style.left   = '0';
  overlay.style.right  = '0';
  overlay.style.bottom = `${posY}%`;
}

/* ── Update aspect ratio frame when dropdown changes ─────────── */
function evUpdateAspectRatio() {
  const val   = (qs('evAspectRatio')?.value || '9:16');
  const parts = val.split(':').map(Number);
  const w = parts[0] || 9, h = parts[1] || 16;
  const frame = qs('evVideoFrame');
  if (frame) frame.style.aspectRatio = `${w} / ${h}`;
  const badge = qs('evAspectBadge');
  if (badge) badge.textContent = val;
  _evSyncSubOverlay();
}

// ── VIDEO PLAYBACK + TIMELINE ─────────────────────────────────────────────────
function evUpdateSubPreview() {
  const font      = qs('evSubFont').value;
  const size      = Number(qs('evSubSize').value);
  const color     = qs('evSubColor').value;
  const highlight = qs('evSubHighlight').value;
  const posY      = Number(qs('evSubPos').value);
  const outline   = Number(qs('evSubOutline').value);

  qs('evSubSizeVal').textContent    = size;
  qs('evSubPosVal').textContent     = posY;
  qs('evSubOutlineVal').textContent = outline;

  // Sync overlay position to actual video frame
  _evSyncSubOverlay();

  // Rebuild demo words with current style
  const strokeCSS = `${outline}px`;
  const shadowCSS = `-${outline}px -${outline}px 0 #000, ${outline}px -${outline}px 0 #000, -${outline}px ${outline}px 0 #000, ${outline}px ${outline}px 0 #000`;
  const baseStyle = `font-family:'${font}',sans-serif;font-size:clamp(12px,3vw,${Math.round(size*0.65)}px);-webkit-text-stroke:${strokeCSS} #000;text-shadow:${shadowCSS}`;

  const words = _EV_DEMO_WORDS;
  const inner = qs('evSubInner');
  inner.innerHTML = words.map((w, i) =>
    `<span style="${baseStyle};color:${i === _ev.subWordIdx ? highlight : color}">${w} </span>`
  ).join('');

  // Static preview box
  const sp = qs('evSubStaticText');
  sp.style.fontFamily = `'${font}',sans-serif`;
  sp.style.fontSize = `${Math.round(size*0.6)}px`;
  sp.style.color = color;
  sp.style.webkitTextStroke = `${outline}px #000`;
  sp.style.textShadow = shadowCSS;
  const half = Math.floor(words.length/2);
  sp.innerHTML = words.map((w, i) =>
    `<span style="color:${i===half?highlight:color}">${w} </span>`
  ).join('');
}

function _evStartSubAnim() {
  if (_ev.subAnimTimer) clearInterval(_ev.subAnimTimer);
  _ev.subWordIdx = 0;
  _ev.subAnimTimer = setInterval(() => {
    _ev.subWordIdx = (_ev.subWordIdx + 1) % _EV_DEMO_WORDS.length;
    evUpdateSubPreview();
  }, 600);
}

/* ── Cancel / close ───────────────────────────────────────── */
function cancelEditorView() {
  if (_ev.subAnimTimer) { clearInterval(_ev.subAnimTimer); _ev.subAnimTimer = null; }
  const video = qs('evVideo');
  if (video) { video.pause(); video.src = ''; video.style.display = 'none'; }
  setView('render');
  setRenderActionBusy(false);
  addEvent('Editor view: huỷ.', 'render');
}

/* ── Re-open editor after session expiry ──────────────────── */
function evReopenEditor() {
  if (!_ev.sourceMode || !_ev.sourceUrl) {
    qs('evStatusLine').textContent = '⚠ Source info not available — please start a new render.';
    return;
  }
  openEditorView(_ev.sourceMode, _ev.sourceUrl, _ev.pendingPayload);
}

/* ── Apply style preset to selected text layer ────────────── */
// ── STYLE PRESETS ─────────────────────────────────────────────────────────────
function evApplyStylePreset(name) {
  const i = _ev.selectedTextLayer;
  const layer = _ev.textLayers[i];
  if (!layer) return;
  const PRESETS = {
    default:    { font_size: 48, color: '#ffffff', bold: false,
                  outline: { enabled: true,  thickness: 2 },
                  shadow:  { enabled: false, offset_x: 2, offset_y: 2 },
                  background: { enabled: false, color: '#00000099', padding: 10 } },
    bold_white: { font_size: 64, color: '#ffffff', bold: true,
                  outline: { enabled: true,  thickness: 3 },
                  shadow:  { enabled: false, offset_x: 2, offset_y: 2 },
                  background: { enabled: false, color: '#00000099', padding: 10 } },
    yellow_sub: { font_size: 52, color: '#ffff00', bold: false,
                  outline: { enabled: true,  thickness: 2 },
                  shadow:  { enabled: false, offset_x: 2, offset_y: 2 },
                  background: { enabled: false, color: '#00000099', padding: 10 } },
    meme:       { font_size: 96, color: '#ffffff', bold: true,
                  outline: { enabled: true,  thickness: 4 },
                  shadow:  { enabled: false, offset_x: 2, offset_y: 2 },
                  background: { enabled: false, color: '#00000099', padding: 10 },
                  alignment: 'center' },
  };
  const p = PRESETS[name];
  if (!p) return;
  // Apply style fields only — x_percent, y_percent, position are intentionally not touched
  layer.font_size  = p.font_size;
  layer.color      = p.color;
  layer.bold       = p.bold;
  layer.outline    = { ...p.outline };
  layer.shadow     = { ...p.shadow };
  layer.background = { ...p.background };
  if (p.alignment !== undefined) layer.alignment = p.alignment;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

/* ── Start render from editor ─────────────────────────────── */
// ── RENDER SUBMIT ─────────────────────────────────────────────────────────────
async function startRenderFromEditor() {
  const payload = _ev.pendingPayload;
  if (!payload) { addEvent('Không có render payload!', 'render'); return; }

  // Pre-submit validation
  if (!_ev.sessionId) {
    qs('evStatusLine').textContent = '⚠ No session — please re-open editor first.';
    qs('evStatusLine').style.color = '#ef4444';
    return;
  }
  const invalidLayer = (_ev.textLayers || []).find(l => !String(l.text || '').trim());
  if (invalidLayer !== undefined) {
    const idx = (_ev.textLayers || []).indexOf(invalidLayer) + 1;
    qs('evStatusLine').textContent = `⚠ Text layer #${idx} is empty — add content or remove it.`;
    qs('evStatusLine').style.color = '#ef4444';
    return;
  }

  // ── Trim & Volume ───────────────────────────────────────────
  const dur  = _ev.duration;
  const inV  = Number(qs('evTrimInSlider').value);
  const outV = Number(qs('evTrimOutSlider').value);
  const inSec  = dur > 0 ? (inV/1000)*dur : Number(qs('evTrimInSec').value)||0;
  const outSec = dur > 0 ? (outV/1000)*dur : Number(qs('evTrimOutSec').value)||0;
  const vol    = Number(qs('evVolume').value) / 100;

  payload.edit_session_id = _ev.sessionId || null;
  payload.edit_trim_in    = inSec  > 0.5 ? inSec  : 0;
  payload.edit_trim_out   = (outSec > 0.5 && outV < 1000) ? outSec : 0;
  payload.edit_volume     = vol;

  // ── Subtitle style ───────────────────────────────────────────
  payload.sub_font      = qs('evSubFont').value;
  payload.sub_font_size = Number(qs('evSubSize').value);
  payload.sub_color     = qs('evSubColor').value;
  payload.sub_highlight = qs('evSubHighlight').value;
  payload.sub_outline   = Number(qs('evSubOutline').value);
  const posY = Number(qs('evSubPos').value);
  payload.sub_margin_v  = Math.round((posY / 100) * 1440 * 0.85);
  payload.subtitle_style = 'pro_karaoke';
  // Editor mode: user expects subtitle on all exported parts.
  payload.subtitle_only_viral_high = false;
  payload.subtitle_viral_min_score = 0;
  payload.subtitle_viral_top_ratio = 1.0;

  // ── Multi-layer text overlay ──────────────────────────────────
  const _toOutline = (v) => (v && typeof v === 'object') ? v : { enabled: false, thickness: typeof v === 'number' ? Math.max(0, Math.min(8, v)) : 2 };
  const _toShadow  = (v) => (v && typeof v === 'object') ? v : { enabled: false, offset_x: 2, offset_y: 2 };
  const _toBg      = (v) => (v && typeof v === 'object') ? v : { enabled: false, color: '#00000099', padding: 10 };
  const layers = (_ev.textLayers || [])
    .map((l, i) => {
      const start = Math.max(0, Number(l.start_time || 0));
      const rawEnd = Math.max(0, Number(l.end_time || 0));
      const end = (rawEnd > 0 && rawEnd <= start) ? (start + 0.1) : rawEnd;
      return { ...l, order: i, start_time: start, end_time: end, outline: _toOutline(l.outline), shadow: _toShadow(l.shadow), background: _toBg(l.background) };
    })
    .filter((l) => String(l.text || '').trim().length > 0)
    .slice(0, EV_MAX_TEXT_LAYERS);
  payload.text_layers = layers;

  // ── Render settings ──────────────────────────────────────────
  payload.aspect_ratio   = qs('evAspectRatio').value;
  payload.playback_speed = Number(qs('evPlaybackSpeed').value);
  payload.min_part_sec   = Number(qs('evMinPart').value);
  payload.max_part_sec   = Number(qs('evMaxPart').value);
  payload.output_fps     = Number(qs('evOutputFps').value || 60);
  payload.max_export_parts = Number(qs('evMaxExportParts').value || 0);
  payload.part_order     = qs('evPartOrder').value;
  payload.frame_scale_y  = Math.max(80, Math.min(130, Number(qs('evFrameScaleY').value || 106)));
  payload.title_overlay_text = '';
  payload.add_title_overlay = false;

  const evDev = qs('evRenderDevice').value;
  payload.encoder_mode = evDev === 'gpu' ? 'nvenc' : (evDev === 'cpu' ? 'cpu' : 'auto');

  const profile = qs('evRenderProfile').value;
  const presetByProfile = { fast:'faster', balanced:'slow', quality:'slower', best:'veryslow' };
  payload.render_profile = profile;
  payload.video_preset   = presetByProfile[profile] || 'slow';

  // 0 = adaptive: backend selects safe workers based on cpu_count, encoder mode, pipeline type
  payload.max_parallel_parts = 0;

  // ── Toggles ──────────────────────────────────────────────────
  payload.add_subtitle    = qs('evAddSubtitle').checked;
  payload.motion_aware_crop = qs('evMotionCrop').checked;
  payload.reframe_mode    = qs('evReframeMode').value;
  payload.cleanup_temp_files = qs('evCleanupTemp').checked;

  // ── Reup Mode ────────────────────────────────────────────────
  const reupEnabled = qs('evReupMode').checked;
  const transformPreset = qs('evTransformPreset').value;
  payload.reup_mode = reupEnabled;
  payload.reup_overlay_enable = reupEnabled;
  if (reupEnabled && transformPreset === 'strong') {
    payload.effect_preset    = 'slay_pop_01';
    payload.transition_sec   = 0.35;
    payload.reup_overlay_opacity = 0.12;
    payload.subtitle_style   = 'viral_pop_anton';
  } else if (reupEnabled) {
    payload.effect_preset    = 'story_clean_01';
    payload.transition_sec   = 0.20;
    payload.reup_overlay_opacity = 0.06;
  } else {
    payload.effect_preset    = 'story_clean_01';
    payload.transition_sec   = 0.25;
    payload.reup_overlay_opacity = 0.08;
  }

  // ── BGM ──────────────────────────────────────────────────────
  const bgmEnabled = qs('evBgmEnable').checked;
  payload.reup_bgm_enable = bgmEnabled;
  payload.reup_bgm_gain   = Number(qs('evBgmGain').value || 0.18);
  if (bgmEnabled && _ev.bgmPath) {
    payload.reup_bgm_path = _ev.bgmPath;
  } else {
    payload.reup_bgm_path = null;
  }

  // ── Output dir override (editor→render: bypass channel selection) ────────────
  {
    let raw = (payload.output_dir || '').replace(/\\/g, '/').trim();
    if (!raw) {
      // Fall back to the export_dir returned by prepare-source for this session.
      raw = (_ev.exportDir || '').replace(/\\/g, '/').trim();
    }
    if (!raw) {
      qs('evStatusLine').textContent = '⚠ Thư mục xuất chưa cấu hình. Vui lòng chọn channel hoặc nhập thư mục ở màn hình chính rồi mở lại editor.';
      qs('evStatusLine').style.color = '#ef4444';
      qs('evStartBtn').disabled = false;
      return;
    }
    const leaf = raw.split('/').filter(Boolean).pop().toLowerCase();
    payload.output_dir   = ['video_output', 'video_out'].includes(leaf) ? raw : raw + '/video_output';
    payload.output_mode  = 'manual';
    payload.channel_code = '';
    payload.render_output_subdir = '';
  }

  addEvent(`Editor → Render | device=${evDev} | profile=${profile} | aspect=${payload.aspect_ratio} | speed=${payload.playback_speed}x | trim ${_fmtTime(inSec)}→${_fmtTime(outSec)} | vol ${Math.round(vol*100)}% | text_layers=${layers.length} | title=off`, 'render');

  if (_ev.subAnimTimer) { clearInterval(_ev.subAnimTimer); _ev.subAnimTimer = null; }
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = '⏳ Sending…';
  if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'none';
  qs('evStatusLine').textContent = '⏳ Đang gửi yêu cầu render…';
  qs('evStatusLine').style.color = '';

  const _renderResult = await _submitRenderPayload(payload, false);
  if (_renderResult && _renderResult.ok) {
    qs('evStatusLine').textContent = 'Render started ✓ — opening monitor…';
    qs('evStatusLine').style.color = 'var(--success)';
    showToast('Render queued ✓', 'success');
    const video = qs('evVideo');
    if (video) { video.pause(); video.src = ''; video.style.display = 'none'; }
    setView('monitor');
  } else {
    const errMsg = (_renderResult && _renderResult.error) || 'Không thể gửi yêu cầu render.';
    const isSessionErr = /editor session|session.*expired|session.*not found|no active session/i.test(errMsg);
    const logHint = ' · Logs: %APPDATA%\\tool-render-video\\logs';
    if (isSessionErr) {
      qs('evStatusLine').textContent = 'Session expired — please re-open editor.' + logHint;
      qs('evStatusLine').style.color = '#ef4444';
      if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'inline-flex';
      qs('evStartBtn').disabled = true;
      qs('evStartBtn').textContent = '▶ Bắt đầu Render';
    } else {
      qs('evStartBtn').disabled = false;
      qs('evStartBtn').textContent = '↺ Retry Render';
      qs('evStatusLine').textContent = `⚠ ${errMsg}${logHint}`;
      qs('evStatusLine').style.color = '#ef4444';
    }
  }
}

// ── Resizable divider (preview ↔ controls) ────────────────────────────────
// mousedown on #evDivider only. mousemove/mouseup go on document during drag
// and are removed immediately on release. No interference with text-layer drag
// (which is gated on _ev.dragLayer inside evTextLayersOverlay).
(function () {
  var divider = document.getElementById('evDivider');
  if (!divider) return;

  var _drag   = false;
  var _startX = 0;
  var _startW = 0;

  function _onMove(e) {
    if (!_drag) return;
    var right = document.querySelector('.evRight');
    if (!right) return;
    // Dragging right → deltaX > 0 → right panel narrows (preview expands) ✓
    var newW = Math.min(700, Math.max(300, _startW - (e.clientX - _startX)));
    right.style.width = newW + 'px';
  }

  function _onUp() {
    if (!_drag) return;
    _drag = false;
    var layout = document.getElementById('view_editor');
    if (layout) layout.classList.remove('resizing');
    document.removeEventListener('mousemove', _onMove);
    document.removeEventListener('mouseup',   _onUp);
  }

  divider.addEventListener('mousedown', function (e) {
    if (window.innerWidth < 900) return; // stacked layout on small screens — no drag
    var right = document.querySelector('.evRight');
    if (!right) return;
    _drag   = true;
    _startX = e.clientX;
    _startW = right.getBoundingClientRect().width;
    var layout = document.getElementById('view_editor');
    if (layout) layout.classList.add('resizing');
    e.preventDefault(); // prevent text selection on drag start
    document.addEventListener('mousemove', _onMove);
    document.addEventListener('mouseup',   _onUp);
  });
})();

// ── Video Editor (old modal — kept for reference/batch) ─────────────────────
