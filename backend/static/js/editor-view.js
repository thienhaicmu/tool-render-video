// ── Editor View (full-screen) ───────────────────────────────────────────────
let _ev = {
  sessionId: null, exportDir: null, duration: 0, pendingPayload: null,
  videoReady: false, subAnimTimer: null, subWordIdx: 0, bgmPath: null,
  textLayers: [], selectedTextLayer: 0,
  sourceMode: null, sourceUrl: null,
  subXPercent: 50,
  subtitleSegments: [],
  subtitleMode: 'demo',
  selectedObject: null,
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
let _evUiInitialized = false;
let _evMoreCollapsed = true;

// ── Aspect ratio helpers ──────────────────────────────────────────────────────
function _evParseAspectRatio(value) {
  const parts = String(value || '9:16').split(':').map(Number);
  const w = parts[0] > 0 ? parts[0] : 9;
  const h = parts[1] > 0 ? parts[1] : 16;
  return [w, h];
}

function _evGetOutputHeight(aspectValue) {
  const [w, h] = _evParseAspectRatio(aspectValue);
  return Math.round(1080 * h / w);
}

function _evSetText(selector, text) {
  const el = document.querySelector(selector);
  if (el) el.textContent = text;
}

function evSetStatus(message, detail = '', isError = false) {
  const line = qs('evStatusLine');
  const small = qs('evStatusDetail');
  if (line) {
    line.textContent = message || '';
    line.style.color = isError ? '#ef4444' : 'var(--text-muted)';
  }
  if (small) small.textContent = detail || '';
}

function _evToggleCollapse(sectionId) {
  const sec = qs(sectionId);
  if (!sec) return;
  sec.classList.toggle('isCollapsed');
}

function _evEnsureSectionCollapse(sectionId, summaryId, summaryText) {
  const sec = qs(sectionId);
  if (!sec) return;
  sec.classList.add('evSectionCollapsible');
  if (!sec.querySelector('.evCollapseSummary')) {
    const s = document.createElement('div');
    s.className = 'evCollapseSummary';
    s.id = summaryId;
    s.textContent = summaryText;
    sec.insertBefore(s, sec.children[1] || null);
  }
  const title = sec.querySelector('.evSectionTitle');
  if (title && !title.dataset.collapseBound) {
    title.dataset.collapseBound = '1';
    title.style.cursor = 'pointer';
    title.addEventListener('click', () => _evToggleCollapse(sectionId));
  }
}

function evToggleSection(sectionId) {
  _evToggleCollapse(sectionId);
}

function evSyncQuickSetting(kind, source = 'quick') {
  const aspectQuick = qs('evAspectRatioQuick');
  const profileQuick = qs('evRenderProfileQuick');
  const aspectMain = qs('evAspectRatio');
  const profileMain = qs('evRenderProfile');
  if (kind === 'aspect' && aspectQuick && aspectMain && source === 'quick') {
    aspectMain.value = aspectQuick.value;
    evUpdateAspectRatio();
  }
  if (kind === 'aspect' && aspectQuick && aspectMain && source === 'main') {
    aspectQuick.value = aspectMain.value;
  }
  if (kind === 'profile' && profileQuick && profileMain && source === 'quick') {
    profileMain.value = profileQuick.value;
  }
  if (kind === 'profile' && profileQuick && profileMain && source === 'main') {
    profileQuick.value = profileMain.value;
  }
}

function _evSyncQuickControlsFromMain() {
  evSyncQuickSetting('aspect', 'main');
  evSyncQuickSetting('profile', 'main');
}

function evToggleMoreSettings() {
  _evMoreCollapsed = !_evMoreCollapsed;
  document.querySelectorAll('.evMoreSettingItem').forEach((el) => el.classList.toggle('hiddenView', _evMoreCollapsed));
  const sec = qs('evSectionMoreSettings');
  if (sec) sec.classList.toggle('isCollapsed', _evMoreCollapsed);
}

function _evEnsureGuidedSections() {
  const pane = document.querySelector('.evRightScroll.inspPaneBody');
  if (!pane || _evUiInitialized) return;

  const trimSec = pane.querySelector('[data-section-type="trim"]');
  const volSec = pane.querySelector('[data-section-type="volume"]');
  const textSec = pane.querySelector('[data-section-type="text-layers"]');

  if (trimSec) trimSec.id = 'evSectionTrim';
  if (volSec) volSec.id = 'evSectionVolume';

  _evSetText('#evSectionTrim .evSectionTitle', 'Trim');
  _evSetText('#evSectionVolume .evSectionTitle', 'Volume');
  _evSetText('#evTrimInfo', 'Full video');
  _evSetText('#evStatusLine', 'Preparing editor...');
  _evSetText('#evStartBtn', '▶ Start Render');
  _evSetText('#evSourceName', 'No source selected');
  _evSetText('#evSubStaticText', 'Preview subtitle');
  const cancelBtn = document.querySelector('.evRightHeader .ghostButton');
  if (cancelBtn) cancelBtn.textContent = '← Cancel';
  const inLabel = qs('evTrimInSec')?.closest('label')?.querySelector('.fieldLabel');
  const outLabel = qs('evTrimOutSec')?.closest('label')?.querySelector('.fieldLabel');
  if (inLabel) inLabel.textContent = 'Start (sec)';
  if (outLabel) outLabel.textContent = 'End (sec)';

  if (textSec) {
    textSec.id = 'evSectionTextLayers';
    _evEnsureSectionCollapse('evSectionTextLayers', 'evSummaryTextLayers', 'No text layers added');
    textSec.classList.add('isCollapsed');
  }

  _evUiInitialized = true;
}

// ── TEXT LAYER FACTORY + DEFAULTS ────────────────────────────────────────────
function evPresetToXY(position) {
  return EV_TEXT_POS_TO_XY[position] || EV_TEXT_POS_TO_XY['bottom-center'];
}

function _evIsCustomTextLayerPosition(layer) {
  if (!layer) return false;
  const defXY = evPresetToXY(layer.position || 'bottom-center');
  const x = Number(layer.x_percent ?? defXY[0]);
  const y = Number(layer.y_percent ?? defXY[1]);
  return Math.abs(x - defXY[0]) > 0.5 || Math.abs(y - defXY[1]) > 0.5;
}

function _evTextLayerPositionLabel(layer) {
  return _evIsCustomTextLayerPosition(layer) ? 'custom' : String(layer?.position || 'bottom-center');
}

function _evSyncTextLayerPositionUi(layer) {
  const pos = qs('evTxtPos');
  if (!pos) return;
  const isCustom = _evIsCustomTextLayerPosition(layer);
  pos.title = isCustom ? 'Custom position — X/Y values now override the preset anchor.' : '';
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
  _evSetSelectedObject('text_' + index);
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
  const txtSummary = qs('evSummaryTextLayers');
  if (txtSummary) txtSummary.textContent = _ev.textLayers.length ? `${_ev.textLayers.length} text layer(s)` : 'No text layers added';
  if (!_ev.textLayers.length) {
    box.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No text layer configured.</div>';
    const editor = qs('evTextLayerEditor');
    if (editor) editor.style.display = 'none';
    return;
  }
  const selected = _ev.selectedTextLayer;
  const _tlNow = Number(qs('evVideo')?.currentTime || 0);
  box.innerHTML = _ev.textLayers.map((layer, i) => {
    const name = String(layer.text || '').trim() || '(empty)';
    const pos = _evTextLayerPositionLabel(layer);
    const isCustom = _evIsCustomTextLayerPosition(layer);
    const xp = Math.max(0, Math.min(100, Number(layer.x_percent ?? 50)));
    const yp = Math.max(0, Math.min(100, Number(layer.y_percent ?? 90)));
    const st = Number(layer.start_time || 0);
    const et = Number(layer.end_time || 0);
    const timing = et > 0 ? `${st.toFixed(1)}s→${et.toFixed(1)}s` : `${st.toFixed(1)}s→end`;
    const isVis = _tlNow >= st && (et === 0 || _tlNow < et);
    return `<div class="evLayerItem ${selected===i?'active':''}" data-layer-state="${selected===i?'selected':'idle'}">
      <span class="evLayerVis ${isVis?'on':'off'}">${isVis?'VIS':'HID'}</span>
      <button class="evTinyBtn evLayerMainBtn" onclick="evSelectTextLayer(${i})" title="${esc(name)}">
        <span class="evLayerMainTitle">${i+1}. ${esc(name)}</span>
        <span class="evLayerMainMeta">
          <span class="evLayerChip${isCustom ? ' isCustom' : ''}">${esc(pos)}</span>
          <span class="evLayerCoords">${xp.toFixed(0)}%, ${yp.toFixed(0)}%</span>
          <span class="evLayerTiming">${timing}</span>
        </span>
      </button>
      <button class="evTinyBtn" onclick="evDuplicateTextLayer(${i})" title="Duplicate">⧉</button>
      <button class="evTinyBtn" onclick="evMoveTextLayer(${i},-1)" title="Move up">↑</button>
      <button class="evTinyBtn" onclick="evMoveTextLayer(${i},1)" title="Move down">↓</button>
      <button class="evTinyBtn" onclick="evDeleteTextLayer(${i})">✕</button>
    </div>`;
  }).join('');
  box.insertAdjacentHTML('beforeend',
    '<div style="font-size:10.5px;color:rgba(251,146,60,.8);margin-top:8px;padding:4px 8px;border-radius:6px;background:rgba(251,146,60,.07);border:1px solid rgba(251,146,60,.18);line-height:1.4">' +
    '⚠ Long text may be clipped in final render' +
    '</div>'
  );
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
  _evSyncTextLayerPositionUi(cur);
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
  _evSyncTextLayerPositionUi(layer);
  evSetStatus('Text layer updated.', `${_evIsCustomTextLayerPosition(layer) ? 'Custom position' : 'Preset position'} · ${Math.round(layer.font_size)}px`);
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
      style.push(`padding:${Math.max(0, Math.round(Number(l.background.padding || 0) * scale))}px`);
      style.push('border-radius:8px');
    }
    const selClass = isSelected ? ' evTLSelected' : '';
    return `<div class="evTextLayerPreview${selClass}" data-layer-id="${esc(String(l.id || ''))}" onmousedown="evTextLayerDragStart(event,'${l.id}')" style="${style.join(';')}">${esc(String(l.text || ''))}</div>`;
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
  _evSetSelectedObject('text_' + layerIdx);
  evRenderTextLayerList();
  evRenderTextLayerPreview();
  const overlay = qs('evTextLayersOverlay');
  if (overlay) overlay.classList.add('evTLDragging');
  const frame = qs('evVideoFrame');
  if (frame) frame.classList.add('evDraggingObject');
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
    const dragFrame = qs('evVideoFrame');
    if (dragFrame) dragFrame.classList.remove('evDraggingObject');
    document.body.style.cursor = '';
    _evSyncTextLayerPositionUi(layer);
    evSetStatus('Text layer position updated.', `Custom position: ${layer.x_percent.toFixed(1)}% x · ${layer.y_percent.toFixed(1)}% y`);
    evRenderTextLayerList();
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function evToggleBgmFields() {
  const el = qs('evBgmFields');
  if (el) el.style.display = qs('evBgmEnable').checked ? 'flex' : 'none';
}
window.RENDER_I18N = {
  en: {
    ui_language: 'UI language',
    language_voice_section: 'Language & Voice',
    subtitle_style: 'Subtitle Style',
    auto_subtitles: 'Auto subtitles',
    translate_subtitles: 'Translate subtitles',
    target_language: 'Target language',
    ai_narration: 'AI Narration',
    enable_ai_narration: 'Enable AI narration',
    narration_source: 'Narration source',
    manual_text_option: 'Manual text',
    use_subtitles_option: 'Use subtitles',
    use_translated_subtitles_option: 'Use translated subtitles',
    language: 'Language',
    voice_preset: 'Voice preset',
    speed: 'Speed',
    speed_slow: 'Slow',
    speed_normal: 'Normal',
    speed_energetic: 'Energetic',
    audio_mode: 'Audio mode',
    audio_mode_replace: 'Replace original audio',
    audio_mode_mix: 'Keep original audio low + add narration',
    what_should_be_narrated: 'What should be narrated?',
    voice_text_placeholder: 'e.g. "This short clip shows how to..."',
    improve_narration_tone: '✨ Improve narration tone',
    manual_text_reused_warning: '⚠️ This narration text will be used for all rendered clips.',
    subtitle_source_hint: 'ℹ️ Each clip uses original subtitle text.',
    translated_subtitle_source_hint: 'ℹ️ Each clip uses translated subtitle text.',
    turn_on_translate_warning: '⚠️ Turn on Translate subtitles to use translated subtitle narration.',
    start_render: '▶ Start Render',
    char_count_one: 'character',
    char_count_other: 'characters',
    render_complete: 'Render complete',
    voice: 'Voice',
    subtitle_translation: 'Subtitle translation',
    applied: 'applied',
    failed: 'failed',
    partial: 'partial',
    not_used: 'not used',
  },
  vi: {
    ui_language: 'Ngôn ngữ giao diện',
    language_voice_section: 'Ngôn ngữ & Giọng đọc',
    subtitle_style: 'Kiểu phụ đề',
    auto_subtitles: 'Phụ đề tự động',
    translate_subtitles: 'Dịch phụ đề',
    target_language: 'Ngôn ngữ đích',
    ai_narration: 'Thuyết minh AI',
    enable_ai_narration: 'Bật thuyết minh AI',
    narration_source: 'Nguồn thuyết minh',
    manual_text_option: 'Nhập nội dung thủ công',
    use_subtitles_option: 'Dùng phụ đề gốc',
    use_translated_subtitles_option: 'Dùng phụ đề đã dịch',
    language: 'Ngôn ngữ',
    voice_preset: 'Mẫu giọng',
    speed: 'Tốc độ',
    speed_slow: 'Chậm',
    speed_normal: 'Bình thường',
    speed_energetic: 'Năng động',
    audio_mode: 'Cách xử lý âm thanh',
    audio_mode_replace: 'Thay thế âm thanh gốc',
    audio_mode_mix: 'Giữ âm gốc nhỏ + thêm thuyết minh',
    what_should_be_narrated: 'Nội dung cần thuyết minh là gì?',
    voice_text_placeholder: 'Ví dụ: "Đoạn clip ngắn này cho thấy..."',
    improve_narration_tone: '✨ Cải thiện giọng điệu thuyết minh',
    manual_text_reused_warning: '⚠️ Nội dung thuyết minh này sẽ được dùng cho tất cả clip được render.',
    subtitle_source_hint: 'ℹ️ Mỗi clip sẽ đọc theo nội dung phụ đề gốc.',
    translated_subtitle_source_hint: 'ℹ️ Mỗi clip sẽ đọc theo nội dung phụ đề đã dịch.',
    turn_on_translate_warning: '⚠️ Hãy bật Dịch phụ đề để dùng thuyết minh từ phụ đề đã dịch.',
    start_render: '▶ Bắt đầu render',
    char_count_one: 'ký tự',
    char_count_other: 'ký tự',
    render_complete: 'Render hoàn tất',
    voice: 'Giọng đọc',
    subtitle_translation: 'Dịch phụ đề',
    applied: 'đã áp dụng',
    failed: 'thất bại',
    partial: 'một phần',
    not_used: 'không dùng',
  },
};
function getRenderUiLanguage() {
  try {
    const val = localStorage.getItem('render_ui_lang');
    if (val !== 'en') localStorage.setItem('render_ui_lang', 'en');
  } catch (_) {
  }
  return 'en';
}
function _renderI18nValue(key, lang = null) {
  const activeLang = lang || getRenderUiLanguage();
  const dict = window.RENDER_I18N?.[activeLang] || window.RENDER_I18N?.en || {};
  return dict[key] || key;
}
function setRenderUiLanguage(lang) {
  const next = lang === 'vi' ? 'vi' : 'en';
  try { localStorage.setItem('render_ui_lang', next); } catch (_) {}
  applyRenderLanguage(next);
}
function applyRenderLanguage(lang) {
  const activeLang = lang === 'vi' ? 'vi' : 'en';
  const picker = qs('evUiLanguage');
  if (picker && picker.value !== activeLang) picker.value = activeLang;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (!key) return;
    const text = _renderI18nValue(key, activeLang);
    if (typeof text === 'string') el.textContent = text;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (!key) return;
    const text = _renderI18nValue(key, activeLang);
    if ('placeholder' in el) el.placeholder = text;
  });
  evUpdateVoiceCharCount();
}
const _EV_VOICE_PRESETS = {
  'vi-VN': [
    { id: 'vi-VN-HoaiMyNeural',  label: 'HoaiMy',  gender: 'female', recommended_use: 'natural, storytelling' },
    { id: 'vi-VN-NamMinhNeural', label: 'NamMinh', gender: 'male',   recommended_use: 'authoritative, news' },
  ],
  'ja-JP': [
    { id: 'ja-JP-NanamiNeural', label: 'Nanami', gender: 'female', recommended_use: 'warm, conversational' },
    { id: 'ja-JP-KeitaNeural',  label: 'Keita',  gender: 'male',   recommended_use: 'professional' },
  ],
  'en-US': [
    { id: 'en-US-JennyNeural', label: 'Jenny', gender: 'female', recommended_use: 'friendly, conversational' },
    { id: 'en-US-AriaNeural',  label: 'Aria',  gender: 'female', recommended_use: 'expressive, engaging' },
    { id: 'en-US-GuyNeural',   label: 'Guy',   gender: 'male',   recommended_use: 'professional' },
    { id: 'en-US-DavisNeural', label: 'Davis', gender: 'male',   recommended_use: 'podcast, documentary' },
  ],
  'en-GB': [
    { id: 'en-GB-SoniaNeural',  label: 'Sonia',  gender: 'female', recommended_use: 'clear, authoritative' },
    { id: 'en-GB-LibbyNeural',  label: 'Libby',  gender: 'female', recommended_use: 'casual, warm' },
    { id: 'en-GB-RyanNeural',   label: 'Ryan',   gender: 'male',   recommended_use: 'documentary, narration' },
    { id: 'en-GB-OliverNeural', label: 'Oliver', gender: 'male',   recommended_use: 'formal, professional' },
  ],
};

function evPopulateVoicePresets(lang, selectedId) {
  const sel = qs('evVoicePreset');
  if (!sel) return;
  const voices = _EV_VOICE_PRESETS[lang] || [];
  sel.innerHTML = voices.map(v =>
    `<option value="${v.id}">${v.label} — ${v.recommended_use}</option>`
  ).join('');
  if (selectedId && voices.find(v => v.id === selectedId)) {
    sel.value = selectedId;
  } else if (voices.length) {
    sel.value = voices[0].id;
  }
}
function evOnVoiceLanguageChange() {
  evPopulateVoicePresets(qs('evVoiceLanguage')?.value || 'vi-VN');
  evOnVoicePresetChange();
}
function evOnVoicePresetChange() {
  const voiceId = qs('evVoicePreset')?.value || '';
  const lang = qs('evVoiceLanguage')?.value || 'vi-VN';
  const voices = _EV_VOICE_PRESETS[lang] || [];
  const matched = voices.find(v => v.id === voiceId);
  const genderEl = qs('evVoiceGender');
  if (genderEl) genderEl.value = matched?.gender || 'female';
}
function evToggleVoiceFields() {
  const el = qs('evVoiceFields');
  if (el) el.style.display = qs('evVoiceEnable').checked ? 'flex' : 'none';
  evUpdateVoiceCharCount();
  evToggleVoiceSourceMode();
}
function evToggleVoiceSourceMode() {
  const source = qs('evVoiceSource')?.value || 'manual';
  const manualArea = qs('evVoiceManualArea');
  const subtitleHint = qs('evVoiceSubtitleHint');
  const translatedHint = qs('evVoiceTranslatedHint');
  const translateOffWarn = qs('evVoiceTranslateOffWarn');
  if (manualArea) manualArea.style.display = source === 'manual' ? 'flex' : 'none';
  if (subtitleHint) subtitleHint.style.display = source === 'subtitle' ? 'block' : 'none';
  const isTranslated = source === 'translated_subtitle';
  if (translatedHint) translatedHint.style.display = isTranslated ? 'block' : 'none';
  const translateOn = !!qs('evSubTranslate')?.checked;
  if (translateOffWarn) translateOffWarn.style.display = isTranslated && !translateOn ? 'block' : 'none';
}
function evOnSubTranslateChange() {
  const enabled = !!qs('evSubTranslate')?.checked;
  const fields = qs('evSubTranslateFields');
  if (fields) fields.style.display = enabled ? 'block' : 'none';
  evToggleVoiceSourceMode();
}
function evUpdateVoiceCharCount() {
  const count = String(qs('evVoiceText')?.value || '').length;
  const el = qs('evVoiceCharCount');
  const singular = _renderI18nValue('char_count_one');
  const plural = _renderI18nValue('char_count_other');
  if (el) el.textContent = `${count} ${count === 1 ? singular : plural}`;
}

function formatNarrationText(text) {
  let t = String(text || '').trim();
  if (!t) return '';

  // Normalize internal whitespace
  t = t.replace(/\s+/g, ' ');

  // Fix missing space after sentence-ending punctuation before a letter
  t = t.replace(/([.!?])([A-Za-z])/g, '$1 $2');

  // Split into sentence chunks: keep punctuation attached to the sentence before it
  const chunks = [];
  const splitRe = /([.!?]+)\s+/g;
  let last = 0;
  let m;
  while ((m = splitRe.exec(t)) !== null) {
    chunks.push(t.slice(last, m.index + m[1].length));
    last = m.index + m[0].length;
  }
  if (last < t.length) chunks.push(t.slice(last));

  const CONTRAST = /^(But |However[, ]|And yet |Still[, ]|Yet[, ]|Now[, ]|Remember[, ])/i;
  const trimmed = chunks.map(s => s.trim()).filter(Boolean);
  const totalSentences = trimmed.length;

  const processed = trimmed.map((chunk, i) => {
    // Capitalize first letter of each sentence
    if (chunk.length > 0) chunk = chunk.charAt(0).toUpperCase() + chunk.slice(1);

    // Long chunk with no ending punctuation — try to break at the comma nearest the midpoint
    if (chunk.length > 90 && !/[.!?]$/.test(chunk)) {
      const mid = Math.floor(chunk.length / 2);
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let j = 0; j < chunk.length; j++) {
        if (chunk[j] === ',') {
          const d = Math.abs(j - mid);
          if (d < bestDist && j > 15 && j < chunk.length - 15) {
            bestDist = d;
            bestIdx = j;
          }
        }
      }
      if (bestIdx !== -1) {
        const before = chunk.slice(0, bestIdx).trim();
        const after = chunk.slice(bestIdx + 1).trim();
        if (after) chunk = before + '. ' + after.charAt(0).toUpperCase() + after.slice(1);
      }
    }

    // Light pause before rhetorical contrast starters —
    // only when not the first sentence, and only if the text has 3 or more sentences
    if (i > 0 && totalSentences >= 3 && CONTRAST.test(chunk)) return '... ' + chunk;
    return chunk;
  });

  t = processed.join(' ');

  // Ensure sentence ends with punctuation
  if (!/[.!?]$/.test(t)) t += '.';

  // Tidy up
  t = t.replace(/\s{2,}/g, ' ').trim();
  t = t.replace(/\.{4,}/g, '...');
  return t;
}

function evImproveNarrationText() {
  const ta = qs('evVoiceText');
  if (!ta) return;
  if (!ta.value.trim()) {
    showToast('Enter narration text first.', 'info');
    return;
  }
  ta.value = formatNarrationText(ta.value);
  evUpdateVoiceCharCount();
  showToast('Narration text improved.', 'success');
}

function evVoiceSpeedToRate(value) {
  const speed = String(value || 'normal').trim().toLowerCase();
  if (speed === 'slow') return '-10%';
  if (speed === 'energetic') return '+10%';
  return '+0%';
}
function evVoiceSpeedFromRate(value) {
  const rate = String(value || '+0%').trim();
  if (rate === '-10%') return 'slow';
  if (rate === '+10%') return 'energetic';
  return 'normal';
}
function evInitVoiceFields(payload) {
  const p = payload || {};
  if (qs('evVoiceEnable')) qs('evVoiceEnable').checked = !!p.voice_enabled;
  const lang = p.voice_language || 'vi-VN';
  if (qs('evVoiceLanguage')) qs('evVoiceLanguage').value = lang;
  if (qs('evVoiceSpeed')) qs('evVoiceSpeed').value = evVoiceSpeedFromRate(p.voice_rate || '+0%');
  if (qs('evVoiceMixMode')) qs('evVoiceMixMode').value = p.voice_mix_mode || 'replace_original';
  if (qs('evVoiceText')) qs('evVoiceText').value = p.voice_text || '';
  if (qs('evVoiceSource')) qs('evVoiceSource').value = p.voice_source || 'manual';
  const translateEnabled = !!p.subtitle_translate_enabled;
  if (qs('evSubTranslate')) qs('evSubTranslate').checked = translateEnabled;
  if (qs('evSubTranslateFields')) qs('evSubTranslateFields').style.display = translateEnabled ? 'block' : 'none';
  if (qs('evSubTranslateTarget')) qs('evSubTranslateTarget').value = p.subtitle_target_language || 'en';
  // Resolve which preset to select: explicit voice_id first, then gender fallback
  let resolvedId = p.voice_id || null;
  if (!resolvedId) {
    const gender = p.voice_gender || 'female';
    const voices = _EV_VOICE_PRESETS[lang] || [];
    const match = voices.find(v => v.gender === gender);
    if (match) resolvedId = match.id;
  }
  evPopulateVoicePresets(lang, resolvedId);
  evOnVoicePresetChange();
  evToggleVoiceFields();
  applyRenderLanguage(getRenderUiLanguage());
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
  if (typeof deactivateRenderUiForEditorOpen === 'function') deactivateRenderUiForEditorOpen();
  _evEnsureGuidedSections();
  qs('evSectionTextLayers')?.classList.add('isCollapsed');
  _ev.selectedObject = null;
  _evUpdateSelLabel();
  _evSyncQuickControlsFromMain();
  _ev.sessionId = null;
  _ev.exportDir = null;
  _ev.duration = 0;
  _ev.pendingPayload = pendingPayload;
  _ev.videoReady = false;
  _ev.sourceMode = sourceMode;
  _ev.sourceUrl = urlOrPath;
  _ev.subXPercent = 50;
  _ev.subtitleSegments = [];
  _ev.subtitleMode = 'demo';
  if (qs('evSubPosX'))    qs('evSubPosX').value       = 50;
  if (qs('evSubPosXVal')) qs('evSubPosXVal').textContent = 50;

  // Init editor settings with defaults (editor is source of truth for all render params)

  setView('editor');
  setInspectorTab('mode');
  setRenderFlowState('configure', 'Preparing editor');
  qs('evSourceName').textContent = urlOrPath || '…';
  qs('evLoadingOverlay').style.display = 'flex';
  qs('evLoadingText').textContent = sourceMode === 'youtube' ? 'Downloading video from YouTube...' : 'Analyzing video...';
  qs('evVideo').style.display = 'none';
  qs('evSubOverlay').style.display = 'none';  // hide until video ready
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = '▶ Start Render';
  if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'none';
  qs('evStatusLine').textContent = sourceMode === 'youtube' ? 'Downloading YouTube source (may take 30-60 seconds)...' : 'Preparing preview...';
  qs('evStatusLine').style.color = '';
  _evUpdateInfoStrip();
  _evResetTrimUI();
  evUpdateSubPreview();
  _evUpdateSubLabel();
  evInitTextLayers();
  evUpdateAspectRatio();  // apply aspect ratio frame from dropdown
  evInitVoiceFields(pendingPayload);

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
    _evUpdateReadiness();

    // Always use backend preview endpoint (H.264 transcoded, range-supported)
    _evLoadVideo(`/api/render/preview-video/${pd.session_id}`);

  } catch(err) {
    qs('evLoadingText').textContent = `Error: ${err.message}`;
    qs('evStartBtn').disabled = true;
    qs('evStartBtn').textContent = 'Preview unavailable';
    if (qs('evReopenBtn')) { qs('evReopenBtn').textContent = 'Retry Open Editor'; qs('evReopenBtn').style.display = 'inline-flex'; }
    qs('evStatusLine').textContent = 'Could not prepare preview. Please retry opening the editor.';
    addEvent(`Editor prepare error: ${err.message}`, 'render');
    if (_ev.duration > 0) _evSetDuration(_ev.duration);
  }
}

/* ── Open editor with pre-downloaded YouTube session ──────── */
function openEditorView_withSession(pd, urlOrPath, pendingPayload) {
  if (typeof deactivateRenderUiForEditorOpen === 'function') deactivateRenderUiForEditorOpen();
  _evEnsureGuidedSections();
  qs('evSectionTextLayers')?.classList.add('isCollapsed');
  _ev.selectedObject = null;
  _evUpdateSelLabel();
  _evSyncQuickControlsFromMain();
  _ev.sessionId = pd.session_id;
  _ev.exportDir = pd.export_dir || null;
  _ev.duration = pd.duration || 0;
  _ev.pendingPayload = pendingPayload;
  _ev.videoReady = false;
  _ev.sourceMode = _ev.sourceMode || 'youtube';
  _ev.subXPercent = 50;
  _ev.subtitleSegments = [];
  _ev.subtitleMode = 'demo';
  if (qs('evSubPosX'))    qs('evSubPosX').value       = 50;
  if (qs('evSubPosXVal')) qs('evSubPosXVal').textContent = 50;
  _ev.sourceUrl = _ev.sourceUrl || urlOrPath;

  setView('editor');
  setInspectorTab('mode');
  setRenderFlowState('configure', 'Editing clip');
  qs('evSourceName').textContent = pd.title || urlOrPath || '…';
  if (qs('evTitleOverlayText') && !String(qs('evTitleOverlayText').value || '').trim()) {
    qs('evTitleOverlayText').value = String(pd.title || '');
  }
  qs('evLoadingOverlay').style.display = 'flex';
  qs('evLoadingText').textContent = 'Loading preview...';
  qs('evVideo').style.display = 'none';
  qs('evSubOverlay').style.display = 'none';
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = '▶ Start Render';
  if (qs('evReopenBtn')) { qs('evReopenBtn').textContent = 'Retry Open Editor'; qs('evReopenBtn').style.display = 'none'; }
  qs('evStatusLine').textContent = 'Loading video preview...';
  qs('evStatusLine').style.color = '';
  _evUpdateInfoStrip();
  _evResetTrimUI();
  evUpdateSubPreview();
  _evUpdateSubLabel();
  evInitTextLayers();
  evUpdateAspectRatio();
  evInitVoiceFields(pendingPayload);

  if (pendingPayload) pendingPayload.edit_session_id = pd.session_id;
  _evSetDuration(_ev.duration);
  _evUpdateReadiness();
  _evLoadVideo(`/api/render/preview-video/${pd.session_id}`);

  // Restore start button
  const btn = qs('start_render_btn');
  if (btn) { btn.disabled = false; btn.textContent = 'Open Editor'; btn.style.opacity = '1'; }
}

function _evLoadVideo(src) {
  const video = qs('evVideo');
  video.removeEventListener('timeupdate', _evOnTimeUpdate);
  video.src = src;
  video.onloadedmetadata = () => {
    _ev.duration = video.duration || _ev.duration;
    _evSetDuration(_ev.duration);
    qs('evLoadingOverlay').style.display = 'none';
    video.style.display = 'block';
    _ev.videoReady = true;
    qs('evStartBtn').disabled = false;
    qs('evStatusLine').textContent = 'Video is ready. Adjust settings and click Start Render.';
    qs('evSubOverlay').style.display = 'flex';
    // Sync subtitle overlay and start animation
    _evSyncSubOverlay();
    _evUpdateSubLabel();
    requestAnimationFrame(() => { _evStartSubAnim(); });
    video.removeEventListener('timeupdate', _evOnTimeUpdate);
    video.addEventListener('timeupdate', _evOnTimeUpdate);
    // Fetch real transcript in background — updates overlay once ready
    if (_ev.sessionId) _evFetchTranscript(_ev.sessionId);
  };
  video.onerror = () => {
    qs('evLoadingText').textContent = 'Preview unavailable';
    qs('evLoadingOverlay').querySelector('div:last-child').textContent = 'Trim and subtitle preview are still available';
    qs('evLoadingOverlay').querySelector('.editorSpinner').style.display = 'none';
    qs('evStartBtn').disabled = true;
    qs('evStartBtn').textContent = 'Preview unavailable';
    if (qs('evReopenBtn')) { qs('evReopenBtn').textContent = 'Retry Open Editor'; qs('evReopenBtn').style.display = 'inline-flex'; }
    qs('evStatusLine').textContent = 'Preview codec is unsupported. Please reopen the editor or load the source again.';
    // Show subtitle preview even without video (over loading overlay)
    qs('evSubOverlay').style.display   = 'flex';
    qs('evSubOverlay').style.left      = `${_ev.subXPercent || 50}%`;
    qs('evSubOverlay').style.right     = 'auto';
    qs('evSubOverlay').style.bottom    = '15%';
    qs('evSubOverlay').style.transform = 'translateX(-50%)';
    qs('evSubOverlay').style.zIndex    = '6'; // above loading overlay
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
  if (_ev.subtitleMode === 'real') _evSyncSubTime(video.currentTime);
  if (_ev.textLayers.length) _evRenderTimelineLayers();
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
  const trimLabel = qs('evTrimRegionLabel');
  if (trimLabel) trimLabel.textContent = `Trim ${_fmtTime(inSec)} → ${_fmtTime(outSec)}`;
  qs('evTrimInfo').textContent = dur > 0
    ? `${_fmtTime(inSec)} → ${_fmtTime(outSec)} (${_fmtTime(sel)})`
    : 'Full video';
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

function _evUpdateSubLabel() {
  const label = qs('evSubModeLabel');
  const modeRow = qs('inspSubModeRow');
  if (label) {
    if (_ev.subtitleMode === 'real') {
      label.textContent = 'Real subtitle preview';
      label.className = 'evSubModeLabel real';
    } else {
      label.textContent = 'Preview sample';
      label.className = 'evSubModeLabel demo';
    }
  }
  if (modeRow) {
    if (_ev.subtitleMode === 'real') {
      modeRow.textContent = 'Real subtitle preview · from Whisper transcript';
      modeRow.className = 'inspSubModeRow real';
    } else {
      modeRow.textContent = 'Preview sample · AI subtitle will be generated on render';
      modeRow.className = 'inspSubModeRow demo';
    }
  }
  _evUpdateReadiness();
}

/* Build word spans for evSubInner using current subtitle style settings. */
function _evBuildWordSpans(words, activeIdx, baseStyle, color, highlight) {
  return words.map((w, i) =>
    `<span style="${baseStyle};color:${i === activeIdx ? highlight : color}">${w} </span>`
  ).join('');
}

/* Find the active subtitle segment for currentTime and render it. */
function _evSyncSubTime(currentTime) {
  if (!_ev.subtitleSegments.length) return;
  const inner = qs('evSubInner');
  if (!inner) return;

  const font      = qs('evSubFont')?.value || 'Bungee';
  const size      = Number(qs('evSubSize')?.value || 46);
  const color     = qs('evSubColor')?.value || '#FFFFFF';
  const highlight = qs('evSubHighlight')?.value || '#FFFF00';
  const outline   = Number(qs('evSubOutline')?.value || 3);
  const strokeCSS = `${outline}px`;
  const shadowCSS = `-${outline}px -${outline}px 0 #000,${outline}px -${outline}px 0 #000,-${outline}px ${outline}px 0 #000,${outline}px ${outline}px 0 #000`;
  // Same scale formula as demo mode (evUpdateSubPreview) — frameWidth / 1080, clamped
  const _fW = Number(qs('evVideoFrame')?.getBoundingClientRect().width || 0);
  const _fScale = _fW > 0 ? Math.max(0.45, Math.min(1.2, _fW / 1080)) : 1;
  const _fontPx = Math.max(12, Math.round(size * _fScale));
  const baseStyle = `font-family:'${font}',sans-serif;font-size:${_fontPx}px;-webkit-text-stroke:${strokeCSS} #000;text-shadow:${shadowCSS}`;

  const seg = _ev.subtitleSegments.find(s => currentTime >= s.start && currentTime < s.end);
  if (!seg) {
    inner.innerHTML = '';
    return;
  }

  const words = String(seg.text || '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) { inner.innerHTML = ''; return; }

  const dur = Math.max(0.01, seg.end - seg.start);
  const wordIdx = Math.min(words.length - 1, Math.floor(((currentTime - seg.start) / dur) * words.length));
  inner.innerHTML = _evBuildWordSpans(words, wordIdx, baseStyle, color, highlight);
}

/* Fetch transcript from backend after video loads. Non-blocking — falls back to demo on any error. */
async function _evFetchTranscript(sessionId) {
  if (!sessionId) return;
  try {
    const resp = await fetch(`/api/render/preview-transcript/${encodeURIComponent(sessionId)}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const segs = Array.isArray(data?.segments) ? data.segments.filter(s => s && s.text) : [];
    if (!segs.length) return;
    if (_ev.sessionId !== sessionId) return;
    _ev.subtitleSegments = segs;
    _ev.subtitleMode = 'real';
    if (_ev.subAnimTimer) { clearInterval(_ev.subAnimTimer); _ev.subAnimTimer = null; }
    _evUpdateSubLabel();
    const vid = qs('evVideo');
    if (vid) _evSyncSubTime(vid.currentTime || 0);
  } catch (_) {
    // silently ignore — demo fallback stays active
  }
}

/* ── Sync subtitle overlay position ────────────────────────── */
/* Overlay is inside .evVideoFrame which has exact aspect ratio  */
/* so bottom: X% is relative to frame height == output height   */
function _evSyncSubOverlay() {
  const overlay = qs('evSubOverlay');
  if (!overlay) return;
  const posY = Number(qs('evSubPos')?.value || 15);
  const posX = Math.max(5, Math.min(95, Number(qs('evSubPosX')?.value ?? _ev.subXPercent ?? 50)));
  _ev.subXPercent     = posX;
  overlay.style.left      = `${posX}%`;
  overlay.style.right     = 'auto';
  overlay.style.bottom    = `${posY}%`;
  overlay.style.transform = 'translateX(-50%)';
}

/* ── Subtitle overlay: 2D drag (vertical + horizontal) ───────── */
function evSubOverlayDragStart(e) {
  e.preventDefault();
  e.stopPropagation();
  _evSetSelectedObject('subtitle');
  const overlay   = qs('evSubOverlay');
  const frame     = qs('evVideoFrame');
  const sliderY   = qs('evSubPos');
  const sliderX   = qs('evSubPosX');
  const posValElY = qs('evSubPosVal');
  const posValElX = qs('evSubPosXVal');
  if (!overlay || !frame || !sliderY) return;

  overlay.classList.add('evSubDragging');
  const rect  = frame.getBoundingClientRect();
  const yMin  = Number(sliderY.min || 5);
  const yMax  = Number(sliderY.max || 60);
  const X_MIN = 5, X_MAX = 95;

  function onMove(me) {
    const relX     = me.clientX - rect.left;
    const relY     = me.clientY - rect.top;
    const rawX     = Math.round((relX / rect.width)  * 100);
    const rawY     = Math.round(((rect.height - relY) / rect.height) * 100);
    const clampedX = Math.max(X_MIN, Math.min(X_MAX, rawX));
    const clampedY = Math.max(yMin,  Math.min(yMax,  rawY));
    _ev.subXPercent = clampedX;
    if (sliderX)   sliderX.value         = clampedX;
    if (posValElX) posValElX.textContent = clampedX;
    sliderY.value         = clampedY;
    if (posValElY) posValElY.textContent = clampedY;
    overlay.style.left      = `${clampedX}%`;
    overlay.style.right     = 'auto';
    overlay.style.bottom    = `${clampedY}%`;
    overlay.style.transform = 'translateX(-50%)';
    const label = qs('evSubDragLabel');
    if (label) { label.textContent = `Subtitle: ${clampedX}%, ${clampedY}%`; label.classList.add('visible'); }
  }

  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup',   onUp);
    overlay.classList.remove('evSubDragging');
    evUpdateSubPreview();
    const label = qs('evSubDragLabel');
    if (label) setTimeout(() => label.classList.remove('visible'), 800);
  }

  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup',   onUp);
}

function evSubPosXChange() {
  const x = Math.max(5, Math.min(95, Number(qs('evSubPosX')?.value || 50)));
  _ev.subXPercent = x;
  const el = qs('evSubPosXVal');
  if (el) el.textContent = x;
  _evSyncSubOverlay();
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
  const frameWidth = Number(qs('evVideoFrame')?.getBoundingClientRect().width || 0);
  const previewScale = frameWidth > 0 ? Math.max(0.45, Math.min(1.2, frameWidth / 1080)) : 1;
  const previewFontPx = Math.max(12, Math.round(size * previewScale));
  const sampleFontPx = Math.max(12, Math.round(size * Math.max(0.5, previewScale * 0.88)));

  qs('evSubSizeVal').textContent    = size;
  qs('evSubPosVal').textContent     = posY;
  qs('evSubOutlineVal').textContent = outline;
  const subSummary = qs('evSummarySubtitle');
  if (subSummary) subSummary.textContent = `${font} · ${size}px`;

  // Sync overlay position to actual video frame
  _evSyncSubOverlay();

  // Rebuild word spans with current style
  const strokeCSS = `${outline}px`;
  const shadowCSS = `-${outline}px -${outline}px 0 #000, ${outline}px -${outline}px 0 #000, -${outline}px ${outline}px 0 #000, ${outline}px ${outline}px 0 #000`;
  const baseStyle = `font-family:'${font}',sans-serif;font-size:${previewFontPx}px;-webkit-text-stroke:${strokeCSS} #000;text-shadow:${shadowCSS}`;

  const inner = qs('evSubInner');
  if (_ev.subtitleMode === 'real') {
    // Re-render current real subtitle with updated style settings
    const vid = qs('evVideo');
    if (vid) _evSyncSubTime(vid.currentTime || 0);
  } else {
    const words = _EV_DEMO_WORDS;
    inner.innerHTML = _evBuildWordSpans(words, _ev.subWordIdx, baseStyle, color, highlight);
  }

  // Static preview box — always uses demo words as a style reference sample
  const sp = qs('evSubStaticText');
  sp.style.fontFamily = `'${font}',sans-serif`;
  sp.style.fontSize = `${sampleFontPx}px`;
  sp.style.color = color;
  sp.style.webkitTextStroke = `${outline}px #000`;
  sp.style.textShadow = shadowCSS;
  const demoWords = _EV_DEMO_WORDS;
  const half = Math.floor(demoWords.length / 2);
  sp.innerHTML = demoWords.map((w, i) =>
    `<span style="color:${i===half?highlight:color}">${w} </span>`
  ).join('');
}

function _evStartSubAnim() {
  if (_ev.subtitleMode === 'real') return;
  if (_ev.subAnimTimer) clearInterval(_ev.subAnimTimer);
  _ev.subWordIdx = 0;
  _ev.subAnimTimer = setInterval(() => {
    if (_ev.subtitleMode === 'real') {
      clearInterval(_ev.subAnimTimer);
      _ev.subAnimTimer = null;
      return;
    }
    _ev.subWordIdx = (_ev.subWordIdx + 1) % _EV_DEMO_WORDS.length;
    evUpdateSubPreview();
  }, 600);
}

/* ── Phase 5: Guide toggle ────────────────────────────────── */
function evToggleGuides() {
  const frame = qs('evVideoFrame');
  const btn = qs('evGuideToggleBtn');
  if (!frame) return;
  frame.classList.toggle('showGuides');
  if (btn) btn.classList.toggle('active', frame.classList.contains('showGuides'));
}

/* ── Phase 5: Selection system ───────────────────────────── */
function _evSetSelectedObject(obj) {
  _ev.selectedObject = obj;
  const overlay = qs('evSubOverlay');
  if (overlay) overlay.classList.toggle('evSubSelected', obj === 'subtitle');
  _evUpdateSelLabel();
}

function _evUpdateSelLabel() {
  const label = qs('evSelLabel');
  const ctxBar = qs('inspContextBar');
  if (!_ev.selectedObject) {
    if (label) label.classList.remove('visible');
    if (ctxBar) ctxBar.textContent = 'Editor';
    return;
  }
  if (_ev.selectedObject === 'subtitle') {
    if (label) label.textContent = 'Subtitle';
    if (ctxBar) ctxBar.textContent = 'Editing: Subtitle';
  } else if (String(_ev.selectedObject).startsWith('text_')) {
    const idx = parseInt(_ev.selectedObject.replace('text_', ''), 10);
    const layer = _ev.textLayers[idx];
    const name = layer ? (String(layer.text || '').trim() || `Layer ${idx + 1}`) : `Layer ${idx + 1}`;
    if (label) label.textContent = `Text: ${name.length > 18 ? name.slice(0, 18) + '…' : name}`;
    if (ctxBar) ctxBar.textContent = `Editing: Text Layer ${idx + 1}`;
  }
  if (label) label.classList.add('visible');
}

/* ── Phase 5: Duplicate text layer ──────────────────────── */
function evDuplicateTextLayer(index) {
  if ((_ev.textLayers || []).length >= EV_MAX_TEXT_LAYERS) {
    showToast(`Max text layers (${EV_MAX_TEXT_LAYERS}) reached`, 'info');
    return;
  }
  const src = _ev.textLayers[index];
  if (!src) return;
  const copy = JSON.parse(JSON.stringify(src));
  copy.id = `txt_${Date.now()}_${Math.floor(Math.random() * 9999)}`;
  copy.x_percent = Math.min(100, Number(copy.x_percent || 50) + 3);
  copy.y_percent = Math.min(100, Number(copy.y_percent || 90) + 3);
  _ev.textLayers.splice(index + 1, 0, copy);
  _ev.textLayers.forEach((l, i) => l.order = i);
  _ev.selectedTextLayer = index + 1;
  evRenderTextLayerList();
  evRenderTextLayerPreview();
}

/* ── Phase 5: Timeline layer tracks ─────────────────────── */
function _evRenderTimelineLayers() {
  const container = qs('evTimelineLayers');
  if (!container) return;
  if (!_ev.textLayers.length || !_ev.duration) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = _ev.textLayers.map((l, i) => {
    const dur = _ev.duration;
    const st = Math.max(0, Number(l.start_time || 0));
    const et = Number(l.end_time || 0);
    const left = (st / dur) * 100;
    const width = et > 0 ? Math.max(0.5, ((et - st) / dur) * 100) : (100 - left);
    const isSel = i === _ev.selectedTextLayer;
    return `<div class="evLayerTrack"><div class="evLayerTrackBar${isSel ? ' selected' : ''}" style="left:${left.toFixed(1)}%;width:${width.toFixed(1)}%"></div></div>`;
  }).join('');
}

/* ── Phase 5: Readiness bar ──────────────────────────────── */
function _evUpdateReadiness() {
  const bar = qs('evReadinessBar');
  if (!bar) return;
  const payload = _ev.pendingPayload;
  const hasSource = !!(_ev.sourceMode && _ev.sourceUrl);
  const hasSession = !!_ev.sessionId;
  const hasOutput = !!(_ev.exportDir || payload?.output_dir);
  const pills = [];
  if (hasSource) pills.push('<span class="evReadinessPill ok">Source ✓</span>');
  else pills.push('<span class="evReadinessPill warn">No source</span>');
  if (hasSession) pills.push('<span class="evReadinessPill ok">Session ✓</span>');
  else pills.push('<span class="evReadinessPill warn">Session…</span>');
  if (hasOutput) pills.push('<span class="evReadinessPill ok">Output ✓</span>');
  else pills.push('<span class="evReadinessPill err">No output</span>');
  bar.innerHTML = pills.join('');
}

/* ── Inspector group collapse ────────────────────────────── */
function evToggleInspGroup(group) {
  const groupMap = {
    audio:       { body: 'inspGroupAudioBody', hdr: 'inspGroupAudioHdr' },
    performance: { body: 'inspGroupPerfBody',  hdr: 'inspGroupPerfHdr' },
    advanced:    { body: 'inspGroupAdvBody',   hdr: 'inspGroupAdvHdr' },
  };
  const ids = groupMap[group];
  if (!ids) return;
  const body = qs(ids.body);
  const hdr  = qs(ids.hdr);
  if (!body) return;
  const isOpen = body.classList.toggle('open');
  if (hdr) hdr.classList.toggle('open', isOpen);
}

function evSetInspGroupOpen(group, open) {
  const groupMap = {
    audio:       { body: 'inspGroupAudioBody', hdr: 'inspGroupAudioHdr' },
    performance: { body: 'inspGroupPerfBody',  hdr: 'inspGroupPerfHdr' },
    advanced:    { body: 'inspGroupAdvBody',   hdr: 'inspGroupAdvHdr' },
  };
  const ids = groupMap[group];
  if (!ids) return;
  const body = qs(ids.body);
  const hdr  = qs(ids.hdr);
  if (!body) return;
  body.classList.toggle('open', !!open);
  if (hdr) hdr.classList.toggle('open', !!open);
}

/* ── Cancel / close ───────────────────────────────────────── */
function cancelEditorView() {
  if (_ev.subAnimTimer) { clearInterval(_ev.subAnimTimer); _ev.subAnimTimer = null; }
  const video = qs('evVideo');
  if (video) {
    video.removeEventListener('timeupdate', _evOnTimeUpdate);
    video.pause();
    video.src = '';
    video.style.display = 'none';
  }
  setView('render');
  setRenderActionBusy(false);
  addEvent('Editor view closed.', 'render');
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
  setRenderFlowState('configure', 'Submitting render request', { force: true });
  if (!payload) {
    const msg = 'Render could not start';
    addEvent('Missing render payload.', 'render');
    if (typeof showToast === 'function') showToast(msg, 'error');
    setRenderFlowState('configure', msg, { force: true });
    return;
  }

  // Pre-submit validation
  if (!_ev.sessionId) {
    const _noSessionMsg = 'No session found. Please re-open editor first.';
    qs('evStatusLine').textContent = _noSessionMsg;
    qs('evStatusLine').style.color = '#ef4444';
    addEvent(_noSessionMsg, 'render');
    if (typeof showToast === 'function') showToast(_noSessionMsg, 'error');
    setRenderFlowState('configure', 'Render could not start', { force: true });
    return;
  }
  const invalidLayer = (_ev.textLayers || []).find(l => !String(l.text || '').trim());
  if (invalidLayer !== undefined) {
    const idx = (_ev.textLayers || []).indexOf(invalidLayer) + 1;
    const _layerMsg = `Text layer #${idx} is empty. Add content or remove it.`;
    qs('evStatusLine').textContent = _layerMsg;
    qs('evStatusLine').style.color = '#ef4444';
    if (typeof showToast === 'function') showToast(_layerMsg, 'error');
    setRenderFlowState('configure', 'Render could not start', { force: true });
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
  // 1440 matches subtitle_engine.py PlayResY — not the actual video height
  payload.sub_margin_v   = Math.round((posY / 100) * 1440);
  payload.subtitle_style = qs('evSubStyle')?.value || 'pro_karaoke';
  payload.sub_x_percent  = Math.max(5, Math.min(95, Number(qs('evSubPosX')?.value ?? _ev.subXPercent ?? 50)));
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

  const voiceEnabled = !!qs('evVoiceEnable')?.checked;
  const voiceSource = qs('evVoiceSource')?.value || 'manual';
  const voiceText = String(qs('evVoiceText')?.value || '').trim();
  if (voiceEnabled && voiceSource === 'manual' && !voiceText) {
    const _voiceMsg = 'Please enter narration text, or turn off AI narration.';
    qs('evStatusLine').textContent = _voiceMsg;
    qs('evStatusLine').style.color = '#ef4444';
    qs('evStartBtn').disabled = false;
    qs('evStartBtn').textContent = '▶ Start Render';
    if (typeof showToast === 'function') showToast(_voiceMsg, 'error');
    setRenderFlowState('configure', 'Render could not start', { force: true });
    return;
  }
  payload.voice_enabled = voiceEnabled;
  payload.voice_source = voiceSource;
  payload.voice_language = qs('evVoiceLanguage')?.value || 'vi-VN';
  payload.voice_gender = qs('evVoiceGender')?.value || 'female';
  payload.voice_id = qs('evVoicePreset')?.value || null;
  payload.voice_rate = evVoiceSpeedToRate(qs('evVoiceSpeed')?.value || 'normal');
  payload.voice_mix_mode = qs('evVoiceMixMode')?.value || 'replace_original';
  payload.voice_text = voiceEnabled ? voiceText : null;
  payload.subtitle_translate_enabled = !!qs('evSubTranslate')?.checked;
  payload.subtitle_target_language = qs('evSubTranslateTarget')?.value || 'en';

  // ── Output dir override (editor→render: bypass channel selection) ────────────
  {
    let raw = (payload.output_dir || '').replace(/\\/g, '/').trim();
    if (!raw) {
      // Fall back to the export_dir returned by prepare-source for this session.
      raw = (_ev.exportDir || '').replace(/\\/g, '/').trim();
    }
    if (!raw) {
      const _outputMsg = 'Output folder is not configured. Choose a channel or manual folder on the main screen, then re-open editor.';
      qs('evStatusLine').textContent = _outputMsg;
      qs('evStatusLine').style.color = '#ef4444';
      qs('evStartBtn').disabled = false;
      if (typeof showToast === 'function') showToast('Please choose an output folder before rendering', 'error');
      setRenderFlowState('configure', 'Render could not start', { force: true });
      return;
    }
    const leaf = raw.split('/').filter(Boolean).pop().toLowerCase();
    payload.output_dir   = ['video_output', 'video_out'].includes(leaf) ? raw : raw + '/video_output';
    payload.output_mode  = 'manual';
    payload.channel_code = '';
    payload.render_output_subdir = '';
  }

  addEvent(`Editor -> Render | device=${evDev} | profile=${profile} | aspect=${payload.aspect_ratio} | speed=${payload.playback_speed}x | trim ${_fmtTime(inSec)}->${_fmtTime(outSec)} | vol ${Math.round(vol*100)}% | text_layers=${layers.length} | title=off`, 'render');

  if (_ev.subAnimTimer) { clearInterval(_ev.subAnimTimer); _ev.subAnimTimer = null; }
  qs('evStartBtn').disabled = true;
  qs('evStartBtn').textContent = 'Sending...';
  evSetStatus('Submitting render request...');
  if (qs('evReopenBtn')) qs('evReopenBtn').style.display = 'none';
  qs('evStatusLine').textContent = 'Submitting render request...';
  qs('evStatusLine').style.color = '';

  if (typeof _submitRenderPayload !== 'function') {
    const _missingFnMsg = 'Internal error: render helper not loaded. Reload the app and try again.';
    qs('evStatusLine').textContent = _missingFnMsg;
    qs('evStatusLine').style.color = '#ef4444';
    qs('evStartBtn').disabled = false;
    qs('evStartBtn').textContent = '▶ Start Render';
    addEvent(_missingFnMsg, 'render');
    if (typeof showToast === 'function') showToast(_missingFnMsg, 'error');
    setRenderFlowState('configure', 'Render could not start', { force: true });
    return;
  }
  const _renderResult = await _submitRenderPayload(payload, false);
  if (_renderResult && _renderResult.ok) {
    evSetStatus('Render started. Tracking in process panel...');
    qs('evStatusLine').textContent = 'Render started. Opening process panel...';
    qs('evStatusLine').style.color = 'var(--success)';
    showToast('Render queued', 'success');
    const video = qs('evVideo');
    if (video) { video.pause(); video.style.display = 'none'; }
    setView('render');
    setRenderFlowState('rendering', 'Queued - 0%');
    focusBottomPanel();
    evSetStatus('Render started. Tracking in process panel...');
  } else {
    const errMsg = (_renderResult && _renderResult.error) || 'Unable to submit render request.';
    const friendlyMsg = (typeof friendlyRenderError === 'function')
      ? friendlyRenderError(errMsg, 'Render could not start')
      : 'Render could not start';
    const isSessionErr = /editor session|session.*expired|session.*not found|no active session/i.test(errMsg);
    const logHint = ' | Logs: %APPDATA%\\tool-render-video\\logs';
    if (isSessionErr) {
      evSetStatus('Session expired. Re-open editor.', 'Technical details: %APPDATA%\\tool-render-video\\logs', true);
      qs('evStatusLine').textContent = 'Session expired. Please re-open editor.' + logHint;
      qs('evStatusLine').style.color = '#ef4444';
      evSetStatus('Session expired. Re-open editor.', 'Technical details: %APPDATA%\\tool-render-video\\logs', true);
      if (qs('evReopenBtn')) { qs('evReopenBtn').textContent = 'Retry Open Editor'; qs('evReopenBtn').style.display = 'inline-flex'; }
      qs('evStartBtn').disabled = true;
      qs('evStartBtn').textContent = 'Start Render';
      if (typeof showToast === 'function') showToast('Render could not start', 'error');
    } else {
      evSetStatus(friendlyMsg, `Technical details: ${errMsg}`, true);
      qs('evStartBtn').disabled = false;
      qs('evStartBtn').textContent = 'Retry Start Render';
      qs('evStatusLine').textContent = friendlyMsg;
      qs('evStatusLine').style.color = '#ef4444';
      evSetStatus(friendlyMsg, `Technical details: ${errMsg}`, true);
      if (typeof showToast === 'function') showToast(friendlyMsg, 'error');
    }
    setRenderFlowState('configure', 'Render could not start', { force: true });
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

// ── Inspector tab system ─────────────────────────────────────────────────────
function setInspectorTab(tab) {
  const validTabs = ['mode', 'subtitle', 'voice', 'text', 'audio', 'performance', 'advanced'];
  const tabTitles = {
    mode: 'Mode',
    subtitle: 'Subtitle',
    voice: 'Voice',
    text: 'Text',
    audio: 'Audio',
    performance: 'Performance',
    advanced: 'Advanced',
  };
  const activeTab = validTabs.includes(tab) ? tab : 'mode';
  const insp = document.getElementById('appInspector');
  if (insp) insp.classList.add('insp-tabs-init');
  const pane = document.querySelector('.inspPaneBody');
  if (pane) {
    pane.setAttribute('data-active-insp-tab', activeTab);
    pane.setAttribute('data-active-insp-title', tabTitles[activeTab] || 'Mode');
  }
  document.querySelectorAll('.insp-tab[data-insp-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-insp-tab') === activeTab);
  });

  document.querySelectorAll('[data-insp-panel]').forEach((el) => {
    const panel = el.getAttribute('data-insp-panel');
    el.classList.toggle('insp-panel-active', panel === activeTab);
  });

  if (['audio', 'performance', 'advanced'].includes(activeTab)) {
    evSetInspGroupOpen(activeTab, true);
  }
}

// ── Video Editor (old modal — kept for reference/batch) ─────────────────────
