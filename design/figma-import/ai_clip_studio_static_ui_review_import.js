/**
 * AI Clip Studio — Static UI Review Figma Import
 * Paste into code.js of a Figma plugin and Run.
 *
 * Creates page: "AI Clip Studio — Static UI Review Import"
 * Creates 11 frames (00–10) reflecting the real product structure.
 *
 * Generated via UI audit of backend/static (index.html, app.css, nav.js,
 * render-ui.js, editor-view.js). No external API. No npm. Pure Figma Plugin API.
 */

(async () => {
  /* ─────────────────────────────────────────────────────
     STEP 1 — Fonts
  ───────────────────────────────────────────────────── */
  await Promise.all([
    figma.loadFontAsync({ family: 'Inter', style: 'Regular' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Bold' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Medium' }),
  ]);

  /* ─────────────────────────────────────────────────────
     STEP 2 — Target page
  ───────────────────────────────────────────────────── */
  const PAGE_NAME = 'AI Clip Studio — Static UI Review Import';
  let targetPage = figma.pages.find(p => p.name === PAGE_NAME);
  if (!targetPage) {
    targetPage = figma.createPage();
    targetPage.name = PAGE_NAME;
  }
  figma.currentPage = targetPage;

  /* ─────────────────────────────────────────────────────
     STEP 3 — Color tokens (match app.css :root)
  ───────────────────────────────────────────────────── */
  const _hex = h => ({
    r: parseInt(h.slice(1, 3), 16) / 255,
    g: parseInt(h.slice(3, 5), 16) / 255,
    b: parseInt(h.slice(5, 7), 16) / 255,
  });
  const C = {
    bg:        _hex('#0b0f1c'),
    sidebar:   _hex('#070a14'),
    card:      _hex('#111827'),
    border:    _hex('#1e2d45'),
    inputBg:   _hex('#0d1526'),
    inputBdr:  _hex('#1e3154'),
    text:      _hex('#e2e8f0'),
    textMuted: _hex('#7a8fa8'),
    textDim:   _hex('#94a3b8'),
    accent:    _hex('#3b82f6'),
    accentLt:  _hex('#60a5fa'),
    accentGlow:_hex('#1d4ed8'),
    success:   _hex('#10b981'),
    warn:      _hex('#f59e0b'),
    danger:    _hex('#ef4444'),
    purple:    _hex('#8b5cf6'),
    white:     _hex('#ffffff'),
    dark:      _hex('#020617'),
    elevated:  _hex('#131f35'),
    sep:       _hex('#253550'),
  };

  /* ─────────────────────────────────────────────────────
     STEP 4 — Helpers
  ───────────────────────────────────────────────────── */
  const solid = (c, a = 1) => [{ type: 'SOLID', color: c, opacity: a }];

  function mkRect(w, h, color, { cr = 0, op = 1, x = 0, y = 0, name = '', stroke, sw = 1 } = {}) {
    const n = figma.createRectangle();
    n.resize(w, h);
    n.fills = solid(color, op);
    if (cr) n.cornerRadius = cr;
    n.x = x; n.y = y;
    if (name) n.name = name;
    if (stroke) { n.strokes = solid(stroke); n.strokeWeight = sw; }
    return n;
  }

  function mkText(str, { sz = 12, color, bold = false, medium = false, x = 0, y = 0, name = '', maxW, align = 'LEFT' } = {}) {
    const n = figma.createText();
    n.fontName = { family: 'Inter', style: bold ? 'Bold' : medium ? 'Medium' : 'Regular' };
    n.textAutoResize = maxW ? 'HEIGHT' : 'WIDTH_AND_HEIGHT';
    if (maxW) n.resize(maxW, 20);
    n.characters = str;
    n.fontSize = sz;
    n.fills = solid(color || C.text);
    n.x = x; n.y = y;
    if (name) n.name = name;
    if (align !== 'LEFT') n.textAlignHorizontal = align;
    return n;
  }

  function mkFrame(name, w, h, { fill = C.bg, x = 0, y = 0, clip = true } = {}) {
    const f = figma.createFrame();
    f.name = name;
    f.resize(w, h);
    f.fills = solid(fill);
    f.x = x; f.y = y;
    f.clipsContent = clip;
    return f;
  }

  function append(parent, ...children) {
    children.forEach(c => parent.appendChild(c));
  }

  function mkDivider(w, { x = 0, y = 0, color } = {}) {
    const n = figma.createLine();
    n.resize(w, 0);
    n.x = x; n.y = y;
    n.strokes = solid(color || C.border);
    n.strokeWeight = 1;
    return n;
  }

  // Pill / badge
  function mkPill(label, { bg, textColor, cr = 999, x = 0, y = 0, h = 20, px = 10 } = {}) {
    const estW = label.length * 6.5 + px * 2;
    const f = mkFrame('pill/' + label, estW, h, { fill: bg || C.card, x, y });
    f.cornerRadius = cr;
    f.clipsContent = false;
    append(f, mkText(label, { sz: 10, bold: true, color: textColor || C.textDim, x: px, y: 4 }));
    return f;
  }

  // Button
  function mkBtn(label, { variant = 'primary', x = 0, y = 0, w = 120, h = 32 } = {}) {
    const bgMap = { primary: C.accent, secondary: C.elevated, ghost: C.bg };
    const f = mkFrame('btn/' + label, w, h, { fill: bgMap[variant] || C.accent, x, y });
    f.cornerRadius = 10;
    if (variant === 'ghost') { f.strokes = solid(C.border); f.strokeWeight = 1; }
    const tCol = variant === 'secondary' ? C.text : C.white;
    append(f, mkText(label, { sz: 11, bold: true, color: tCol, x: Math.max(6, (w - label.length * 6.5) / 2), y: 9 }));
    return f;
  }

  // Input field (label + box)
  function mkInput(label, placeholder, { x = 0, y = 0, w = 240 } = {}) {
    const g = mkFrame('input/' + label, w, 58, { fill: { r: 0, g: 0, b: 0 }, x, y });
    g.fills = [];
    g.clipsContent = false;
    append(g,
      mkText(label.toUpperCase(), { sz: 9, bold: true, color: C.textDim, x: 0, y: 0 }),
    );
    const box = mkFrame('box', w, 36, { fill: C.inputBg, x: 0, y: 16 });
    box.cornerRadius = 8;
    box.strokes = solid(C.inputBdr);
    box.strokeWeight = 1;
    append(box, mkText(placeholder, { sz: 11, color: C.textMuted, x: 10, y: 10 }));
    append(g, box);
    return g;
  }

  // Section header (label + thin accent)
  function mkSectionHead(label, { x = 0, y = 0, w = 300 } = {}) {
    const g = mkFrame('sec/' + label, w, 28, { fill: { r: 0, g: 0, b: 0 }, x, y });
    g.fills = [];
    g.clipsContent = false;
    append(g,
      mkRect(3, 14, C.accent, { cr: 2, x: 0, y: 7 }),
      mkText(label.toUpperCase(), { sz: 9, bold: true, color: C.accent, x: 10, y: 8 }),
    );
    return g;
  }

  // Part / clip progress card (bottom panel)
  function mkPartCard(no, stage, pct, { x = 0, y = 0 } = {}) {
    const stageColors = {
      done:         C.success,
      rendering:    C.accent,
      transcribing: C.purple,
      cutting:      C.warn,
      waiting:      C.textDim,
      failed:       C.danger,
    };
    const c = stageColors[stage] || C.textMuted;
    const f = mkFrame('part/' + no, 108, 66, { fill: C.inputBg, x, y });
    f.cornerRadius = 10;
    f.strokes = solid(c, 0.4);
    f.strokeWeight = 1;
    append(f,
      mkText('Part ' + no, { sz: 10, bold: true, color: C.text, x: 8, y: 8 }),
      mkText(pct + '%', { sz: 9, color: C.textMuted, x: 75, y: 9 }),
    );
    // Progress bar
    const track = mkRect(92, 4, C.border, { cr: 2, x: 8, y: 28 });
    const fill_ = mkRect(Math.round(92 * pct / 100), 4, c, { cr: 2, x: 8, y: 28, op: 0.9 });
    const stageText = mkText(stage, { sz: 9, color: c, x: 8, y: 38 });
    append(f, track, fill_, stageText);
    return f;
  }

  // Clip output card
  function mkClipCard(rank, score, durationSec, aspect, status, { x = 0, y = 0 } = {}) {
    const sColor = score >= 8 ? C.success : score >= 5 ? C.warn : C.danger;
    const statusCol = { done: C.success, failed: C.danger, skipped: C.textMuted }[status] || C.textMuted;
    const thumbH = aspect === '9:16' ? 180 : aspect === '1:1' ? 140 : 165;
    const cardH = thumbH + 64;
    const f = mkFrame('clip/#' + rank, 140, cardH, { fill: C.elevated, x, y });
    f.cornerRadius = 12;
    f.strokes = solid(status === 'done' && score >= 8 ? C.success : C.border, 0.5);
    f.strokeWeight = 1;

    // Thumbnail
    const thumb = mkFrame('thumb', 140, thumbH, { fill: _hex('#0f172a'), x: 0, y: 0 });
    // Score badge
    const badge = mkFrame('score', 36, 18, { fill: sColor, x: 6, y: 6 });
    badge.fills = solid(sColor, 0.2);
    badge.cornerRadius = 4;
    badge.strokes = solid(sColor, 0.6);
    badge.strokeWeight = 1;
    append(badge, mkText(score.toFixed(1), { sz: 9, bold: true, color: sColor, x: 5, y: 3 }));
    // Rank badge
    const rankB = mkFrame('rank', 24, 24, { fill: C.accentGlow, x: 6, y: thumbH - 30 });
    rankB.cornerRadius = 5;
    rankB.fills = solid(C.accent, 0.85);
    append(rankB, mkText('#' + rank, { sz: 9, bold: true, color: C.white, x: 3, y: 6 }));
    // Duration
    const dur = mkFrame('dur', 46, 16, { fill: C.dark, x: thumb.width - 52, y: thumbH - 22 });
    dur.cornerRadius = 3;
    dur.fills = solid(C.dark, 0.7);
    const mins = Math.floor(durationSec / 60);
    const secs = durationSec % 60;
    append(dur, mkText(`${mins}:${secs.toString().padStart(2, '0')}`, { sz: 9, color: C.white, x: 4, y: 2 }));
    // Aspect badge
    const aspB = mkFrame('asp', 28, 14, { fill: C.dark, x: 8, y: thumbH - 20 });
    aspB.cornerRadius = 2;
    aspB.fills = solid(C.border, 0.6);
    append(aspB, mkText(aspect, { sz: 8, color: C.textDim, x: 3, y: 1 }));
    append(thumb, badge, rankB, dur, aspB);

    // Info footer
    const info = mkFrame('info', 140, 64, { fill: C.elevated, x: 0, y: thumbH });
    info.fills = [];
    append(info,
      mkText('Part ' + rank + (score >= 8 ? '  ★' : ''), { sz: 10, bold: true, color: C.text, x: 8, y: 6 }),
      mkText(status, { sz: 9, color: statusCol, x: 8, y: 22 }),
    );
    // Action buttons
    const dl = mkFrame('dl', 52, 20, { fill: C.inputBg, x: 8, y: 38 });
    dl.cornerRadius = 4;
    dl.strokes = solid(C.border);
    dl.strokeWeight = 1;
    append(dl, mkText('Download', { sz: 8, color: C.textDim, x: 4, y: 4 }));
    const pr = mkFrame('pr', 52, 20, { fill: C.inputBg, x: 66, y: 38 });
    pr.cornerRadius = 4;
    pr.strokes = solid(C.border);
    pr.strokeWeight = 1;
    append(pr, mkText('Preview', { sz: 8, color: C.accentLt, x: 7, y: 4 }));
    append(info, dl, pr);
    append(f, thumb, info);
    return f;
  }

  /* ─────────────────────────────────────────────────────
     STEP 5 — Shared layout constants
  ───────────────────────────────────────────────────── */
  const FW = 1440;    // Frame width (standard desktop)
  const FH = 900;     // Frame height
  const GAP = 100;    // Gap between frames
  const TOPBAR_H = 42;
  const STATUS_H = 28;
  const SIDEBAR_W = 280;
  const INSPECTOR_W = 360;
  const BOTTOM_FULL = 360;
  const BOTTOM_COLL = 52;  // Collapsed to toolbar only
  const CENTER_W = FW - SIDEBAR_W - INSPECTOR_W;

  // Helper: draw the app topbar into a frame
  function drawTopbar(parent, { activeTab = 'render', statusText = 'Local AI render engine' } = {}) {
    const tb = mkFrame('Topbar', FW, TOPBAR_H, { fill: C.sidebar, x: 0, y: 0 });
    // Brand
    const brand = mkRect(30, 30, C.accent, { cr: 8, x: 12, y: 6 });
    append(tb, brand, mkText('AI', { sz: 12, bold: true, color: C.white, x: 16, y: 13 }));
    append(tb, mkText('AI Clip Studio', { sz: 14, bold: true, color: C.text, x: 48, y: 8 }));
    append(tb, mkText('Creator-ready short video workspace', { sz: 9, color: C.textMuted, x: 48, y: 26 }));
    // Nav tabs
    const tabs = ['Render', 'Download', 'History'];
    tabs.forEach((t, i) => {
      const isActive = t.toLowerCase() === activeTab;
      const tw = 72;
      const tx = 220 + i * (tw + 4);
      const tabF = mkFrame('tab/' + t, tw, 28, { fill: isActive ? _hex('#162035') : C.sidebar, x: tx, y: 7 });
      tabF.cornerRadius = 6;
      if (isActive) { tabF.strokes = solid(C.accent, 0.2); tabF.strokeWeight = 1; }
      append(tabF, mkText(t, { sz: 12, bold: isActive, color: isActive ? C.accentLt : C.textDim, x: isActive ? 16 : 18, y: 7 }));
      append(tb, tabF);
    });
    // Status chip
    const chip = mkPill(statusText, { bg: C.card, textColor: C.textDim, x: 420, y: 10, h: 22, px: 10 });
    append(tb, chip);
    // Settings icon
    const settingsBox = mkRect(30, 30, C.card, { cr: 8, x: FW - 48, y: 6, stroke: C.border, sw: 1 });
    append(tb, settingsBox, mkText('⚙', { sz: 13, color: C.textMuted, x: FW - 38, y: 13 }));
    append(parent, tb);
  }

  // Helper: draw the status bar
  function drawStatusBar(parent) {
    const sb = mkFrame('StatusBar', FW, STATUS_H, { fill: C.sidebar, x: 0, y: FH - STATUS_H });
    sb.strokes = solid(C.border, 0.4);
    sb.strokeWeight = 1;
    append(sb,
      mkRect(6, 6, C.success, { cr: 3, x: 12, y: 11 }),
      mkText('Ready  ·  FFmpeg OK  ·  GPU auto  ·  Whisper loaded', { sz: 10, color: C.textMuted, x: 24, y: 8 }),
      mkText('AI Clip Studio v3 · Electron + FastAPI', { sz: 10, color: C.textMuted, x: FW - 240, y: 8 }),
    );
    append(parent, sb);
  }

  // Helper: draw the sidebar (source setup)
  function drawSidebar(parent, { view = 'render', sourceType = 'youtube', outputFolderSet = false } = {}) {
    const sb = mkFrame('Sidebar', SIDEBAR_W, FH - TOPBAR_H - STATUS_H, { fill: C.sidebar, x: 0, y: TOPBAR_H });
    sb.strokes = solid(C.border, 0.3);
    sb.strokeWeight = 1;

    // Header
    append(sb,
      mkText('Render Setup', { sz: 9, bold: true, color: C.textDim, x: 14, y: 12 }),
      mkDivider(SIDEBAR_W, { x: 0, y: 30, color: C.border }),
    );

    // Source group
    append(sb, mkText('1. SOURCE', { sz: 8, bold: true, color: C.accent, x: 14, y: 42 }));
    append(sb, mkInput('Source Type', 'Video URL', { x: 14, y: 56, w: SIDEBAR_W - 28 }));
    if (sourceType === 'youtube') {
      append(sb, mkInput('Video URL', 'https://youtube.com/watch?v=...', { x: 14, y: 122, w: SIDEBAR_W - 28 }));
    } else {
      append(sb, mkInput('Local Video', 'No file selected', { x: 14, y: 122, w: SIDEBAR_W - 28 }));
      append(sb, mkBtn('Choose Video', { variant: 'secondary', x: 14, y: 162, w: 120, h: 28 }));
    }

    // Output group
    append(sb, mkDivider(SIDEBAR_W - 28, { x: 14, y: 210, color: C.border }));
    append(sb, mkText('2. PACKAGE', { sz: 8, bold: true, color: C.accent, x: 14, y: 220 }));
    const folderBox = mkInput('Output Folder', outputFolderSet ? 'D:\\videos\\output' : 'e.g. D:\\videos\\output', { x: 14, y: 234, w: SIDEBAR_W - 28 });
    append(sb, folderBox);
    append(sb, mkBtn('📁 Choose', { variant: 'ghost', x: 14, y: 296, w: 88, h: 26 }));

    // Actions
    append(sb, mkDivider(SIDEBAR_W - 28, { x: 14, y: 336, color: C.border }));
    append(sb, mkBtn('Open Editor', { variant: 'primary', x: 14, y: 352, w: SIDEBAR_W - 28, h: 36 }));
    append(sb, mkBtn('↺ Resume Job', { variant: 'ghost', x: 14, y: 396, w: 120, h: 28 }));

    append(parent, sb);
  }

  // Helper: draw the inspector (right panel, editor only)
  function drawInspector(parent, { activeTab = 'mode' } = {}) {
    const insp = mkFrame('Inspector/Right', INSPECTOR_W, FH - TOPBAR_H - STATUS_H, { fill: C.sidebar, x: FW - INSPECTOR_W, y: TOPBAR_H });
    insp.strokes = solid(C.border, 0.3);
    insp.strokeWeight = 1;

    // Header
    append(insp,
      mkText('Video Editor', { sz: 14, bold: true, color: C.text, x: 16, y: 12 }),
      mkText('source_video.mp4 — 1h 24m', { sz: 10, color: C.textMuted, x: 16, y: 32 }),
      mkRect(INSPECTOR_W, 1, C.border, { x: 0, y: 50 }),
    );

    // Tab bar
    const tabs = ['Cut', 'Subtitles', 'Text & Voice', 'Audio', 'Render'];
    tabs.forEach((t, i) => {
      const isActive = t.toLowerCase().startsWith(activeTab);
      const tw = Math.round(INSPECTOR_W / tabs.length);
      const tabF = mkFrame('insp-tab/' + t, tw - 2, 28, { fill: isActive ? C.card : C.sidebar, x: 2 + i * tw, y: 54 });
      tabF.cornerRadius = 4;
      if (isActive) { tabF.strokes = solid(C.accent, 0.3); tabF.strokeWeight = 1; }
      append(tabF, mkText(t, { sz: 10, bold: isActive, color: isActive ? C.accentLt : C.textDim, x: 4, y: 8 }));
      append(insp, tabF);
    });

    // Body content (Cut tab)
    append(insp, mkRect(INSPECTOR_W, 1, C.border, { x: 0, y: 86 }));
    let bodyY = 96;

    // Trim section
    append(insp, mkSectionHead('✂️  Trim', { x: 14, y: bodyY, w: INSPECTOR_W - 28 }));
    bodyY += 34;
    const trimTrack = mkRect(INSPECTOR_W - 28, 6, C.border, { cr: 3, x: 14, y: bodyY });
    const trimFill = mkRect(200, 6, C.accent, { cr: 3, x: 14, y: bodyY, op: 0.85 });
    append(insp, trimTrack, trimFill);
    bodyY += 18;
    append(insp,
      mkInput('Start (sec)', '0', { x: 14, y: bodyY, w: 152 }),
      mkInput('End (sec)', '–', { x: 172, y: bodyY, w: 172 }),
    );
    bodyY += 68;

    // Quick Start Presets
    append(insp, mkSectionHead('Quick Start Preset', { x: 14, y: bodyY, w: INSPECTOR_W - 28 }));
    bodyY += 34;
    const presets = ['📱 TikTok / Reels', '🎙️ Podcast Clip', '💼 Clean Business', '⬆️ High Quality'];
    presets.forEach((p, i) => {
      const col = i % 2; const row = Math.floor(i / 2);
      const pBtn = mkFrame('preset/' + p, 156, 44, { fill: C.inputBg, x: 14 + col * 164, y: bodyY + row * 52 });
      pBtn.cornerRadius = 8;
      pBtn.strokes = solid(C.border);
      pBtn.strokeWeight = 1;
      append(pBtn, mkText(p, { sz: 10, bold: true, color: C.text, x: 10, y: 14 }));
      append(insp, pBtn);
    });
    bodyY += 110;

    // Output settings
    append(insp, mkSectionHead('Output', { x: 14, y: bodyY, w: INSPECTOR_W - 28 }));
    bodyY += 34;
    append(insp,
      mkInput('Aspect Ratio', '3:4 Vertical', { x: 14, y: bodyY, w: 152 }),
      mkInput('Profile', 'Balanced', { x: 172, y: bodyY, w: 172 }),
    );
    bodyY += 68;

    // Footer
    append(insp,
      mkRect(INSPECTOR_W, 1, C.border, { x: 0, y: FH - STATUS_H - TOPBAR_H - 56 }),
      mkBtn('Start Render', { variant: 'primary', x: 14, y: FH - STATUS_H - TOPBAR_H - 44, w: INSPECTOR_W - 28, h: 36 }),
    );

    append(parent, insp);
  }

  // Helper: draw the bottom panel (collapsed toolbar state)
  function drawBottomCollapsed(parent) {
    const bp = mkFrame('BottomPanel/Collapsed', FW, BOTTOM_COLL, { fill: C.sidebar, x: 0, y: FH - STATUS_H - BOTTOM_COLL });
    bp.strokes = solid(_hex('#1e3a5f'), 0.8);
    bp.strokeWeight = 2;
    append(bp,
      mkText('No active job', { sz: 11, bold: true, color: C.text, x: 16, y: 10 }),
      mkText('Channel – | Source –', { sz: 9, color: C.textMuted, x: 16, y: 26 }),
    );
    const progTrack = mkRect(FW - 500, 6, C.border, { cr: 3, x: 200, y: 22 });
    append(bp, progTrack);
    append(bp, mkText('0%', { sz: 13, bold: true, color: C.accentLt, x: FW - 280, y: 16 }));
    const idlePill = mkPill('Idle', { bg: _hex('#1e2d45'), textColor: C.textDim, x: FW - 200, y: 14, h: 22 });
    append(bp, idlePill);
    append(bp, mkBtn('▴', { variant: 'ghost', x: FW - 52, y: 10, w: 32, h: 30 }));
    append(parent, bp);
  }

  // Helper: draw expanded bottom panel (active render)
  function drawBottomExpanded(parent, { pct = 67, stage = 'rendering', partsData = [] } = {}) {
    const bp = mkFrame('BottomPanel/Expanded', FW, BOTTOM_FULL, { fill: C.sidebar, x: 0, y: FH - STATUS_H - BOTTOM_FULL });
    bp.strokes = solid(_hex('#1e3a5f'), 0.8);
    bp.strokeWeight = 2;

    // Toolbar
    const toolbar = mkFrame('abpToolbar', FW, 44, { fill: _hex('#060910'), x: 0, y: 0 });
    append(toolbar,
      mkText('render_job_2025_...', { sz: 11, bold: true, color: C.text, x: 16, y: 8 }),
      mkText('3 / 5 clips done  ·  source_video.mp4', { sz: 9, color: C.textMuted, x: 16, y: 26 }),
    );
    const progTrack = mkRect(FW - 500, 8, C.border, { cr: 4, x: 220, y: 18 });
    const progFill = mkRect(Math.round((FW - 500) * pct / 100), 8, C.accent, { cr: 4, x: 220, y: 18, op: 0.9 });
    append(toolbar, progTrack, progFill);
    append(toolbar,
      mkText(pct + '%', { sz: 14, bold: true, color: C.accentLt, x: FW - 280, y: 12 }),
      mkPill(stage.charAt(0).toUpperCase() + stage.slice(1), { bg: _hex('#162035'), textColor: C.accentLt, x: FW - 200, y: 11, h: 22 }),
      mkBtn('▾', { variant: 'ghost', x: FW - 52, y: 8, w: 32, h: 28 }),
    );
    append(bp, toolbar);

    // Body: Queue panel (left 60%)
    const qW = Math.round(FW * 0.6);
    const qPanel = mkFrame('rcQueuePanel', qW, BOTTOM_FULL - 44, { fill: _hex('#030712'), x: 0, y: 44 });
    // Panel header
    append(qPanel,
      mkText('Render Queue', { sz: 11, bold: true, color: C.text, x: 14, y: 10 }),
      mkPill('3 waiting', { bg: C.card, textColor: C.textMuted, x: 130, y: 8, h: 20 }),
      mkPill('Rendering', { bg: _hex('#162035'), textColor: C.accentLt, x: 220, y: 8, h: 20 }),
      mkBtn('‹ Logs', { variant: 'ghost', x: qW - 80, y: 8, w: 64, h: 24 }),
      mkRect(qW, 1, C.border, { x: 0, y: 34 }),
    );

    // Active card
    const activeCard = mkFrame('rcActiveCard', qW - 16, 64, { fill: C.elevated, x: 8, y: 42 });
    activeCard.cornerRadius = 8;
    activeCard.strokes = solid(C.accent, 0.25);
    activeCard.strokeWeight = 1;
    const activeProg = mkRect(qW - 56, 4, C.border, { cr: 2, x: 8, y: 36 });
    const activeFill = mkRect(Math.round((qW - 56) * pct / 100), 4, C.accent, { cr: 2, x: 8, y: 36, op: 0.9 });
    append(activeCard,
      mkText('Part 3 — Rendering (67%)', { sz: 11, bold: true, color: C.text, x: 12, y: 10 }),
      mkText('cutting → transcribing → rendering → done', { sz: 9, color: C.textMuted, x: 12, y: 26 }),
      activeProg, activeFill,
    );
    append(qPanel, activeCard);

    // Part cards grid
    const defaultParts = [
      [1, 'done', 100], [2, 'done', 100], [3, 'rendering', pct],
      [4, 'waiting', 0], [5, 'waiting', 0],
    ];
    const parts = partsData.length ? partsData : defaultParts;
    parts.forEach(([no, stg, p], i) => {
      const card = mkPartCard(no, stg, p, { x: 8 + (i % 4) * 116, y: 116 + Math.floor(i / 4) * 74 });
      append(qPanel, card);
    });
    append(bp, qPanel);

    // Body: Log panel (right 40%)
    const logW = FW - qW;
    const logPanel = mkFrame('rcLogPanel', logW, BOTTOM_FULL - 44, { fill: _hex('#030712'), x: qW, y: 44 });
    logPanel.strokes = solid(C.border, 0.2);
    logPanel.strokeWeight = 1;
    append(logPanel,
      mkText('Recent Activity', { sz: 11, bold: true, color: C.text, x: 14, y: 10 }),
      mkBtn('↑ Auto', { variant: 'ghost', x: logW - 140, y: 6, w: 52, h: 24 }),
      mkBtn('Copy', { variant: 'ghost', x: logW - 80, y: 6, w: 40, h: 24 }),
      mkRect(logW, 1, C.border, { x: 0, y: 34 }),
    );
    // Log entries (id: event_log_render — must not rename)
    const logs = [
      ['[system]', 'Render job started: 5 parts queued', C.textDim],
      ['[ffmpeg]', 'Part 1: scene detection complete', C.textMuted],
      ['[ffmpeg]', 'Part 1: Whisper transcription done', C.textMuted],
      ['[ffmpeg]', 'Part 1: render complete → output/part_01.mp4', C.success],
      ['[ffmpeg]', 'Part 2: scene detection complete', C.textMuted],
      ['[system]', 'Part 2: transcription started (Whisper)', C.textMuted],
      ['[ffmpeg]', 'Part 2: render complete → output/part_02.mp4', C.success],
      ['[ffmpeg]', 'Part 3: cutting started', C.accentLt],
    ];
    logs.forEach(([tag, msg, col], i) => {
      const logRow = mkFrame('log/' + i, logW - 16, 22, { fill: { r: 0, g: 0, b: 0 }, x: 8, y: 42 + i * 24 });
      logRow.fills = [];
      logRow.clipsContent = false;
      append(logRow,
        mkText(tag, { sz: 9, bold: true, color: C.accent, x: 0, y: 4 }),
        mkText(msg, { sz: 9, color: col, x: 64, y: 4, maxW: logW - 80 }),
      );
      append(logPanel, logRow);
    });
    append(bp, logPanel);
    append(parent, bp);
  }

  /* ─────────────────────────────────────────────────────
     STEP 6 — Create all frames
  ───────────────────────────────────────────────────── */
  const allFrames = [];

  // ── 00: Product Shell / App Architecture ─────────────────────────────────
  {
    const f = mkFrame('00 · Product Shell / App Architecture', FW, FH, { x: 0 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));

    // Title block
    append(f,
      mkText('00 — Product Shell / App Architecture', { sz: 24, bold: true, color: C.accentLt, x: 40, y: 32 }),
      mkText('AI Clip Studio · Desktop App · Electron + FastAPI · 4-zone grid layout', { sz: 13, color: C.textMuted, x: 40, y: 64 }),
    );

    // Architecture diagram (scaled to fit)
    const DY = 100;        // diagram top
    const DH = FH - DY - 40;  // diagram height
    const scale = DH / FH;
    const dW = Math.round(FW * scale);
    const dX = 40;

    // Draw zones
    const zones = [
      { name: 'appTopBar\ngrid-row:1  ·  42px', color: _hex('#070a14'), h: Math.round(TOPBAR_H * scale), col: C.accentLt, stroke: _hex('#0e1729') },
    ];
    let dCurY = DY;

    // Topbar zone
    const zTbH = Math.round(TOPBAR_H * scale);
    const zTb = mkRect(dW, zTbH, _hex('#070a14'), { x: dX, y: dCurY, stroke: _hex('#0e1729'), sw: 1 });
    append(f, zTb, mkText('appTopBar · grid-row:1 · 42px', { sz: 8, bold: true, color: C.accentLt, x: dX + 8, y: dCurY + 8 }));
    dCurY += zTbH;

    // Main row (rs-main) - split 3 columns
    const zMainH = Math.round((FH - TOPBAR_H - BOTTOM_FULL - STATUS_H) * scale);
    const dSbW = Math.round(SIDEBAR_W * scale);
    const dInspW = Math.round(INSPECTOR_W * scale);
    const dCenW = dW - dSbW - dInspW;

    const zSide = mkRect(dSbW, zMainH, _hex('#060910'), { x: dX, y: dCurY, stroke: _hex('#0e1729'), sw: 1 });
    append(f, zSide,
      mkText('sidebar\nrs-left-panel\n280px', { sz: 8, bold: true, color: C.accent, x: dX + 6, y: dCurY + 8 }),
    );
    const zCen = mkRect(dCenW, zMainH, C.bg, { x: dX + dSbW, y: dCurY, stroke: C.border, sw: 1 });
    append(f, zCen,
      mkText('mainArea · rs-center-panel\noverflow-y:auto · display:contents children', { sz: 8, color: C.accentLt, x: dX + dSbW + 6, y: dCurY + 8 }),
    );
    const zInsp = mkRect(dInspW, zMainH, _hex('#060910'), { x: dX + dSbW + dCenW, y: dCurY, stroke: _hex('#0e1729'), sw: 1 });
    append(f, zInsp,
      mkText('appInspector\nrs-right-panel\n360px (editor only)', { sz: 8, color: C.purple, x: dX + dSbW + dCenW + 6, y: dCurY + 8 }),
    );
    dCurY += zMainH;

    // Bottom panel zone
    const zBotH = Math.round(BOTTOM_FULL * scale);
    const zBot = mkRect(dW, zBotH, _hex('#06090e'), { x: dX, y: dCurY, stroke: _hex('#1e3a5f'), sw: 2 });
    append(f, zBot,
      mkText('appBottomPanel · rs-bottom-panel · grid-row:3 · clamp(260px,40vh,420px)\nabpToolbar(44px) + rcQueuePanel(60%) + rcLogPanel(40%)', { sz: 8, bold: true, color: C.warn, x: dX + 8, y: dCurY + 8 }),
    );
    dCurY += zBotH;

    // Status bar zone
    const zStatH = DH - (dCurY - DY);
    const zStat = mkRect(dW, zStatH, _hex('#070a14'), { x: dX, y: dCurY, stroke: _hex('#0e1729'), sw: 1 });
    append(f, zStat, mkText('appStatusBar · grid-row:4 · 28px', { sz: 8, color: C.textMuted, x: dX + 8, y: dCurY + 8 }));

    // Annotations panel (right of diagram)
    const annoX = dX + dW + 28;
    append(f,
      mkText('CSS Grid: appShell', { sz: 14, bold: true, color: C.text, x: annoX, y: DY }),
      mkText('grid-template-rows:\n  42px       ← topbar\n  1fr        ← rs-main (workspace)\n  40vh/420px ← bottom panel\n  28px       ← status bar\n\ngrid-template-columns:\n  1fr  (rs-main owns columns)', { sz: 10, color: C.textDim, x: annoX, y: DY + 26 }),
    );
    append(f,
      mkText('rs-main (row 2):', { sz: 13, bold: true, color: C.text, x: annoX, y: DY + 200 }),
      mkText('280px sidebar | flex center | 360px inspector', { sz: 10, color: C.textDim, x: annoX, y: DY + 220 }),
    );
    append(f,
      mkText('Key IDs — DO NOT RENAME:', { sz: 12, bold: true, color: C.danger, x: annoX, y: DY + 268 }),
      mkText('event_log_render  job_bar  job_percent\njob_stage_pill  job_title  job_meta_1\nrc_* (all)   abp_* (all)', { sz: 10, color: C.textDim, x: annoX, y: DY + 290 }),
    );

    // Color swatches
    append(f, mkText('Design Tokens', { sz: 13, bold: true, color: C.text, x: annoX, y: DY + 380 }));
    const swatches = [
      ['--bg', '#0b0f1c', C.bg], ['--sidebar-bg', '#070a14', C.sidebar],
      ['--card-bg', '#111827', C.card], ['--card-border', '#1e2d45', C.border],
      ['--accent', '#3b82f6', C.accent], ['--success', '#10b981', C.success],
      ['--warn', '#f59e0b', C.warn], ['--danger', '#ef4444', C.danger],
      ['--text', '#e2e8f0', C.text], ['--text-muted', '#7a8fa8', C.textMuted],
    ];
    swatches.forEach(([name, hex_, col], i) => {
      append(f,
        mkRect(16, 16, col, { cr: 4, x: annoX, y: DY + 402 + i * 22 }),
        mkText(name, { sz: 10, color: C.textDim, x: annoX + 24, y: DY + 404 + i * 22 }),
        mkText(hex_, { sz: 10, color: C.textMuted, x: annoX + 140, y: DY + 404 + i * 22 }),
      );
    });

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 01: Render Flow — Source Setup (idle state) ───────────────────────────
  {
    const f = mkFrame('01 · Render Flow — Source Setup', FW, FH, { x: 1 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawSidebar(f, { view: 'render', sourceType: 'youtube' });

    // Center: render home panel (hero + step rail + cards)
    const cenX = SIDEBAR_W;
    const cenW = FW - SIDEBAR_W;
    const cenY = TOPBAR_H;
    const cenH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;

    // Hero section
    const hero = mkFrame('renderHeroPanel', cenW - 40, 120, { fill: C.bg, x: cenX + 20, y: cenY + 24 });
    hero.fills = [];
    append(hero,
      mkPill('Render workspace', { bg: _hex('#162035'), textColor: C.accentLt, x: 0, y: 0, h: 22 }),
      mkText('Turn one source into ranked short clips.', { sz: 28, bold: true, color: C.text, x: 0, y: 30 }),
      mkText('Prepare a video, let AI plan clips, edit, render locally, then review best outputs.', { sz: 13, color: C.textMuted, x: 0, y: 72 }),
    );
    append(f, hero);

    // Step rail
    const stepRailY = cenY + 156;
    const stepRail = mkFrame('renderStepRail', cenW - 40, 70, { fill: C.bg, x: cenX + 20, y: stepRailY });
    stepRail.fills = [];
    const steps = [
      ['1', 'Source', 'Paste link or choose file', true],
      ['2', 'Plan', 'AI ranks hooks & market fit', false],
      ['3', 'Editor', 'Trim, crop, subtitles, voice', false],
      ['4', 'Rendering', 'Track parts, logs, retries', false],
      ['5', 'Review', 'Preview, compare, export', false],
    ];
    const stepW = Math.round((cenW - 40) / steps.length);
    steps.forEach(([num, title, desc, active], i) => {
      const sc = mkFrame('step/' + title, stepW - 8, 66, { fill: active ? _hex('#0f1b2e') : _hex('#0a0f1a'), x: i * stepW, y: 0 });
      sc.cornerRadius = 8;
      sc.strokes = solid(active ? C.accent : C.border, active ? 0.5 : 0.3);
      sc.strokeWeight = 1;
      const numBadge = mkFrame('num', 22, 22, { fill: active ? C.accent : C.border, x: 10, y: 8 });
      numBadge.cornerRadius = 11;
      append(numBadge, mkText(num, { sz: 10, bold: true, color: C.white, x: 6, y: 4 }));
      append(sc, numBadge,
        mkText(title, { sz: 11, bold: true, color: active ? C.text : C.textDim, x: 36, y: 10 }),
        mkText(desc, { sz: 9, color: C.textMuted, x: 10, y: 36, maxW: stepW - 20 }),
      );
      append(stepRail, sc);
    });
    append(f, stepRail);

    // Feature cards grid
    const gridY = stepRailY + 86;
    const cardW = Math.round((cenW - 40 - 24) / 3);
    const cards = [
      ['Clip Recipe', ['Format presets: TikTok/Reels, podcast, business', 'Auto subtitles: karaoke, translation, narration', 'AI hook scoring + market intelligence ranking']],
      ['System Readiness', ['✓  FFmpeg execution backend ready', '✓  Whisper subtitle pipeline available', '◎  GPU auto-detect enabled', '◉  Advanced AI features opt-in']],
      ['Recent Renders', ['No recent renders yet.', '', '→ Complete a render to see history here.']],
    ];
    cards.forEach(([title, items], ci) => {
      const card = mkFrame('card/' + title, cardW, 180, { fill: C.elevated, x: cenX + 20 + ci * (cardW + 12), y: gridY });
      card.cornerRadius = 14;
      card.strokes = solid(C.sep, 0.7);
      card.strokeWeight = 1;
      append(card, mkText(title, { sz: 12, bold: true, color: C.text, x: 14, y: 14 }));
      items.forEach((item, ii) => {
        append(card, mkText(item, { sz: 10, color: C.textDim, x: 14, y: 40 + ii * 22, maxW: cardW - 28 }));
      });
      append(f, card);
    });

    // Annotation overlay
    append(f,
      mkRect(3, 160, C.accent, { cr: 2, op: 0.5, x: cenX + 6, y: cenY + 24 }),
      mkText('Center · renderHomePanel\nhiddenView when job active', { sz: 9, color: C.accent, x: cenX + 14, y: cenY + 24 }),
      mkRect(3, 80, C.success, { cr: 2, op: 0.5, x: FW - 16, y: cenY + 24 }),
      mkText('noInspector state\n→ inspector hidden', { sz: 9, color: C.success, x: FW - 130, y: cenY + 24 }),
    );

    drawBottomCollapsed(f);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 02: Render Flow — Editor (Format & Options) ───────────────────────────
  {
    const f = mkFrame('02 · Render Flow — Editor / Format & Options', FW, FH, { x: 2 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.dark));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawSidebar(f, { view: 'editor', sourceType: 'youtube', outputFolderSet: true });
    drawInspector(f, { activeTab: 'mode' });

    // Center: Editor video preview + timeline
    const cenX = SIDEBAR_W;
    const cenW = FW - SIDEBAR_W - INSPECTOR_W;
    const cenY = TOPBAR_H;

    // Aspect bar
    const aspectBar = mkFrame('evAspectBar', cenW, 28, { fill: _hex('#070a14'), x: cenX, y: cenY });
    append(aspectBar,
      mkText('Aspect ratio:', { sz: 9, color: C.textMuted, x: 12, y: 9 }),
      mkPill('9:16', { bg: _hex('#162035'), textColor: C.accentLt, x: 100, y: 4, h: 20 }),
      mkText('— preview crop matches output framing', { sz: 9, color: C.textMuted, x: 148, y: 9 }),
      mkBtn('Guides', { variant: 'ghost', x: cenW - 70, y: 4, w: 60, h: 20 }),
    );
    append(f, aspectBar);

    // Video box (dark background)
    const videoBoxH = FH - TOPBAR_H - 28 - 72 - STATUS_H - BOTTOM_COLL;
    const videoBox = mkFrame('evVideoBox', cenW, videoBoxH, { fill: _hex('#0a0a0a'), x: cenX, y: cenY + 28 });
    // Frame (9:16 aspect — centered)
    const frameH = videoBoxH - 16;
    const frameW = Math.round(frameH * 9 / 16);
    const frameX = Math.round((cenW - frameW) / 2);
    const videoFrame = mkFrame('evVideoFrame', frameW, frameH, { fill: C.dark, x: frameX, y: 8 });
    videoFrame.cornerRadius = 16;
    videoFrame.strokes = solid(C.white, 0.12);
    videoFrame.strokeWeight = 1;
    // Subtitle preview overlay
    const subOvly = mkFrame('evSubOverlay', frameW, 36, { fill: { r: 0, g: 0, b: 0 }, x: 0, y: Math.round(frameH * 0.78) });
    subOvly.fills = [];
    append(subOvly, mkText('POV: never gonna give you up', { sz: 18, bold: true, color: C.white, x: 8, y: 6 }));
    // Timeline layers placeholder
    const tlLayers = mkRect(frameW, 4, C.accent, { cr: 2, op: 0.3, x: 0, y: Math.round(frameH * 0.5) });
    append(videoFrame, subOvly, tlLayers);
    append(videoBox, videoFrame);
    append(f, videoBox);

    // Timeline bar
    const tlBar = mkFrame('evTimeline', cenW, 72, { fill: _hex('#06090f'), x: cenX, y: cenY + 28 + videoBoxH });
    tlBar.strokes = solid(_hex('#1e3a5f'), 0.8);
    tlBar.strokeWeight = 2;
    append(tlBar,
      mkText('0:00:00', { sz: 10, color: C.textMuted, x: 10, y: 28 }),
    );
    const tlTrack = mkFrame('tlTrack', cenW - 120, 36, { fill: _hex('#080c12'), x: 50, y: 18 });
    tlTrack.cornerRadius = 6;
    tlTrack.strokes = solid(C.border, 0.5);
    tlTrack.strokeWeight = 1;
    // Progress / trim region
    const trimRegion = mkRect(tlTrack.width - 20, 32, C.accentGlow, { cr: 4, x: 10, y: 2, op: 0.4 });
    const playhead = mkRect(2, 36, C.white, { cr: 1, x: Math.round((tlTrack.width - 20) * 0.35), y: 0, op: 0.88 });
    append(tlTrack, trimRegion, playhead);
    append(tlBar, tlTrack,
      mkText('1:24:37', { sz: 10, color: C.textMuted, x: cenW - 80, y: 28 }),
      mkBtn('▶', { variant: 'ghost', x: cenW - 44, y: 22, w: 32, h: 28 }),
    );
    append(f, tlBar);

    drawBottomCollapsed(f);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 03: Render Flow — Render Monitor (active job) ─────────────────────────
  {
    const f = mkFrame('03 · Render Flow — Render Monitor (Active)', FW, FH, { x: 3 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawSidebar(f, { view: 'render', outputFolderSet: true });

    // Center: render active panel (rdCard + AI insights + runtime mount)
    const cenX = SIDEBAR_W + 16;
    const cenW = FW - SIDEBAR_W - 32;
    const cenY = TOPBAR_H + 12;

    // rdCard — summary card
    const rdCard = mkFrame('rdCard', cenW, 88, { fill: C.elevated, x: cenX, y: cenY });
    rdCard.cornerRadius = 14;
    rdCard.strokes = solid(C.accent, 0.25);
    rdCard.strokeWeight = 1;
    // Header
    const rdBadge = mkPill('Rendering', { bg: _hex('#162035'), textColor: C.accentLt, x: 14, y: 12, h: 22 });
    append(rdCard, rdBadge,
      mkText('render_job_2025_01_15_143012', { sz: 16, bold: true, color: C.text, x: 108, y: 13 }),
      mkBtn('View Logs', { variant: 'ghost', x: cenW - 102, y: 12, w: 86, h: 24 }),
    );
    // Progress
    append(rdCard,
      mkText('Part 3 of 5 — Rendering subtitles', { sz: 12, color: C.textDim, x: 14, y: 44 }),
    );
    const rdTrack = mkRect(cenW - 140, 6, C.border, { cr: 3, x: 14, y: 62 });
    const rdFill = mkRect(Math.round((cenW - 140) * 0.67), 6, C.accent, { cr: 3, x: 14, y: 62, op: 0.9 });
    append(rdCard,
      rdTrack, rdFill,
      mkText('67%', { sz: 20, bold: true, color: C.accentLt, x: cenW - 110, y: 44 }),
      mkText('Clips will appear below as they finish.', { sz: 10, color: C.textMuted, x: cenW - 110, y: 68 }),
    );
    append(f, rdCard);

    // AI insights panel
    const aiY = cenY + 100;
    const aiPanel = mkFrame('aiInsightsPanel', cenW, 52, { fill: _hex('#0a1520'), x: cenX, y: aiY });
    aiPanel.cornerRadius = 10;
    aiPanel.strokes = solid(_hex('#162035'), 0.8);
    aiPanel.strokeWeight = 1;
    append(aiPanel,
      mkText('AI Insights', { sz: 10, bold: true, color: C.accentLt, x: 14, y: 10 }),
      mkPill('High engagement probability', { bg: _hex('#162035'), textColor: C.success, x: 100, y: 8, h: 22 }),
      mkText('Hook density: 4.2  ·  Pacing: optimal  ·  Keyword hits: 7', { sz: 10, color: C.textMuted, x: 14, y: 32 }),
    );
    append(f, aiPanel);

    // Render Runtime Mount (toolbar + rcBottom moved here by JS)
    const rtY = aiY + 64;
    const rtH = FH - TOPBAR_H - STATUS_H - (BOTTOM_COLL) - rtY + TOPBAR_H;
    const rtMount = mkFrame('renderRuntimeMount', cenW, rtH, { fill: _hex('#030712'), x: cenX, y: rtY });
    rtMount.cornerRadius = 12;
    rtMount.strokes = solid(C.border, 0.4);
    rtMount.strokeWeight = 1;

    // Mini toolbar inside mount
    const miniToolbar = mkFrame('abpToolbar(mounted)', cenW, 44, { fill: _hex('#060910'), x: 0, y: 0 });
    miniToolbar.cornerRadius = 10;
    append(miniToolbar,
      mkText('Part 3/5 · 67%  ·  Rendering…', { sz: 11, bold: true, color: C.text, x: 16, y: 8 }),
      mkText('source_video.mp4  ·  3 clips done', { sz: 9, color: C.textMuted, x: 16, y: 26 }),
    );
    const mtTrack = mkRect(cenW - 400, 6, C.border, { cr: 3, x: 180, y: 19 });
    const mtFill = mkRect(Math.round((cenW - 400) * 0.67), 6, C.accent, { cr: 3, x: 180, y: 19 });
    append(miniToolbar, mtTrack, mtFill,
      mkText('67%', { sz: 13, bold: true, color: C.accentLt, x: cenW - 200, y: 14 }),
      mkPill('Rendering', { bg: _hex('#162035'), textColor: C.accentLt, x: cenW - 140, y: 11, h: 22 }),
    );
    append(rtMount, miniToolbar);

    // Queue + logs inside mount
    const qW2 = Math.round(cenW * 0.58);
    const qPanel2 = mkFrame('rcQueuePanel(mounted)', qW2, rtH - 44, { fill: _hex('#030508'), x: 0, y: 44 });
    append(qPanel2,
      mkText('Render Queue', { sz: 11, bold: true, color: C.text, x: 14, y: 10 }),
      mkRect(qW2, 1, C.border, { x: 0, y: 30 }),
    );
    // Active card
    const ac2 = mkFrame('activeCard', qW2 - 16, 52, { fill: C.elevated, x: 8, y: 36 });
    ac2.cornerRadius = 8;
    ac2.strokes = solid(C.accent, 0.3);
    ac2.strokeWeight = 1;
    append(ac2, mkText('Part 3 — Rendering (67%)', { sz: 11, bold: true, color: C.text, x: 10, y: 8 }));
    const ac2Track = mkRect(qW2 - 40, 4, C.border, { cr: 2, x: 10, y: 30 });
    const ac2Fill = mkRect(Math.round((qW2 - 40) * 0.67), 4, C.accent, { cr: 2, x: 10, y: 30 });
    append(ac2, ac2Track, ac2Fill);
    append(qPanel2, ac2);

    // Part cards
    [[1,'done',100],[2,'done',100],[3,'rendering',67],[4,'waiting',0],[5,'waiting',0]].forEach(([n,s,p],i) => {
      append(qPanel2, mkPartCard(n, s, p, { x: 8 + (i % 4) * 116, y: 96 + Math.floor(i / 4) * 74 }));
    });
    append(rtMount, qPanel2);

    // Log strip inside mount
    const logW2 = cenW - qW2;
    const logStrip2 = mkFrame('rcLogStrip(mounted)', logW2, rtH - 44, { fill: _hex('#020508'), x: qW2, y: 44 });
    logStrip2.strokes = solid(C.border, 0.15);
    logStrip2.strokeWeight = 1;
    append(logStrip2,
      mkText('Recent Activity', { sz: 11, bold: true, color: C.text, x: 14, y: 10 }),
      mkRect(logW2, 1, C.border, { x: 0, y: 30 }),
    );
    const logItems = ['[system] Render job started: 5 parts', '[ffmpeg] Part 1: done', '[ffmpeg] Part 2: done', '[ffmpeg] Part 3: cutting→transcribing→rendering'];
    logItems.forEach((l, i) => append(logStrip2, mkText(l, { sz: 9, color: i === 3 ? C.accentLt : C.textMuted, x: 10, y: 38 + i * 20 })));
    append(rtMount, logStrip2);
    append(f, rtMount);

    // Bottom panel is renderCompatWrapper (display:none → 0 space)
    append(f,
      mkText('Note: bottom panel has renderCompatWrapper → display:none, height:0.\nRuntime monitor is inside render_runtime_mount in center.', { sz: 9, color: C.warn, x: SIDEBAR_W + 16, y: FH - STATUS_H - 20 }),
    );

    drawStatusBar(f);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 04: Render Monitor — Bottom Panel Detail ──────────────────────────────
  {
    const f = mkFrame('04 · Render Monitor — Bottom Panel Detail', FW, FH, { x: 4 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawSidebar(f, { view: 'render', outputFolderSet: true });

    // Center: show normal view (no editor) with bottom expanded
    const cenX = SIDEBAR_W + 16;
    const cenW2 = FW - SIDEBAR_W - 32;

    // Title in center
    append(f,
      mkText('04 — Bottom Panel / Render Monitor Detail', { sz: 18, bold: true, color: C.accentLt, x: cenX, y: TOPBAR_H + 20 }),
      mkText('The runtime panel (abpToolbar + rcQueuePanel + rcLogStrip) — always visible, collapsible', { sz: 12, color: C.textMuted, x: cenX, y: TOPBAR_H + 46 }),
    );

    // Render flow bar (4-step flow indicator)
    const rfY = TOPBAR_H + 80;
    const rfBar = mkFrame('renderFlowBar', cenW2, 52, { fill: _hex('#0a1220'), x: cenX, y: rfY });
    rfBar.cornerRadius = 8;
    rfBar.strokes = solid(C.border, 0.3);
    rfBar.strokeWeight = 1;
    const flowSteps = [['1','Source','source_video.mp4','done'], ['2','Configure','TikTok 9:16 · Balanced','done'], ['3','Rendering','Part 3/5 · 67%','active'], ['4','Review','Waiting…','pending']];
    const fsW = Math.round(cenW2 / flowSteps.length);
    flowSteps.forEach(([n, title, sub, state], i) => {
      const fsColors = { done: C.success, active: C.accent, pending: C.textMuted };
      const fc = mkFrame('fstep/' + title, fsW - 8, 44, { fill: state === 'active' ? _hex('#0e1b30') : _hex('#09101b'), x: 4 + i * fsW, y: 4 });
      fc.cornerRadius = 6;
      if (state === 'active') { fc.strokes = solid(C.accent, 0.4); fc.strokeWeight = 1; }
      const nb = mkFrame('fnum', 18, 18, { fill: fsColors[state] || C.textMuted, x: 8, y: 12 });
      nb.cornerRadius = 9;
      append(nb, mkText(n, { sz: 9, bold: true, color: C.white, x: 4, y: 3 }));
      append(fc, nb, mkText(title, { sz: 10, bold: true, color: fsColors[state] || C.textMuted, x: 32, y: 8 }));
      append(fc, mkText(sub, { sz: 9, color: C.textMuted, x: 32, y: 24, maxW: fsW - 40 }));
      append(rfBar, fc);
    });
    append(f, rfBar);

    // Draw expanded bottom panel (main focus of this frame)
    drawBottomExpanded(f, { pct: 67, stage: 'rendering' });

    // Annotations on bottom panel components
    const botPanelY = FH - STATUS_H - BOTTOM_FULL;
    const annotations = [
      [16, 2, 'abpToolbar — 44px fixed height. Contains: job_title, job_bar, job_percent, job_stage_pill, abp_collapse_btn'],
      [16, 54, 'rcQueuePanel — left 60%. Contains: rc_active_card, rc_part_cards (grid), rc_output_preview'],
      [FW * 0.6 + 8, 54, 'rcLogStrip — right 40%. Contains: event_log_render (ID must not change). overflow-y:auto'],
      [16, 120, 'rc_part_cards — partsProgressGrid. repeat(auto-fill, minmax(108px, 1fr)). max-height:220px overflow:auto'],
    ];
    annotations.forEach(([ax, ay, txt]) => {
      append(f,
        mkRect(4, 2, C.warn, { cr: 1, x: ax - 4, y: botPanelY + ay }),
        mkText(txt, { sz: 8, color: C.warn, x: ax, y: botPanelY + ay - 8, maxW: 500 }),
      );
    });

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 05: Output Preview / Clip Gallery ─────────────────────────────────────
  {
    const f = mkFrame('05 · Output Preview — Clip Gallery', FW, FH, { x: 5 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawSidebar(f, { view: 'render', outputFolderSet: true });

    const cenX = SIDEBAR_W + 16;
    const cenW3 = FW - SIDEBAR_W - 32;
    const cenY2 = TOPBAR_H + 12;

    // Completion banner
    const banner = mkFrame('renderCompletionBar', cenW3, 64, { fill: _hex('#0c2414'), x: cenX, y: cenY2 });
    banner.cornerRadius = 10;
    banner.strokes = solid(C.success, 0.3);
    banner.strokeWeight = 1;
    const checkCircle = mkFrame('icon', 36, 36, { fill: C.success, x: 14, y: 14 });
    checkCircle.cornerRadius = 18;
    checkCircle.fills = solid(C.success, 0.2);
    append(checkCircle, mkText('✓', { sz: 16, bold: true, color: C.success, x: 9, y: 8 }));
    append(banner, checkCircle,
      mkText('Render complete — 5 clips ready', { sz: 14, bold: true, color: C.success, x: 58, y: 12 }),
      mkText('Ranked by AI score. Best clips flagged. Output: D:\\videos\\output\\', { sz: 10, color: C.textDim, x: 58, y: 34 }),
    );
    append(banner,
      mkBtn('← Back to Editor', { variant: 'ghost', x: cenW3 - 320, y: 16, w: 128, h: 32 }),
      mkBtn('Review Clips', { variant: 'ghost', x: cenW3 - 182, y: 16, w: 96, h: 32 }),
      mkBtn('Open Output Folder', { variant: 'primary', x: cenW3 - 78, y: 16, w: 64, h: 32 }),
    );
    append(f, banner);

    // Output panel header
    const opY = cenY2 + 80;
    const opHeader = mkFrame('renderOutputHeader', cenW3, 36, { fill: C.bg, x: cenX, y: opY });
    opHeader.fills = [];
    append(opHeader,
      mkText('CLIPS', { sz: 10, bold: true, color: C.textDim, x: 0, y: 8 }),
      mkPill('5', { bg: _hex('#162035'), textColor: C.accentLt, x: 52, y: 6, h: 22 }),
      mkBtn('Best first ▾', { variant: 'ghost', x: cenW3 - 180, y: 4, w: 96, h: 28 }),
      mkBtn('Open Folder', { variant: 'ghost', x: cenW3 - 78, y: 4, w: 74, h: 28 }),
    );
    append(f, opHeader);

    // Center preview for selected clip
    const cpY = opY + 44;
    const cpH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL - cpY + TOPBAR_H;
    const cpW = Math.round(cenW3 * 0.38);
    const csPreview = mkFrame('csPreviewArea', cpW, cpH, { fill: _hex('#030712'), x: cenX, y: cpY });
    csPreview.cornerRadius = 10;
    csPreview.strokes = solid(C.border, 0.4);
    csPreview.strokeWeight = 1;
    const previewVid = mkFrame('previewVideo', cpW - 24, Math.round((cpW - 24) * 16 / 9), { fill: C.dark, x: 12, y: 12 });
    previewVid.cornerRadius = 8;
    append(previewVid, mkText('▶  Playing Part 1', { sz: 12, color: C.textMuted, x: Math.round((cpW - 24) / 2) - 50, y: Math.round((cpW - 24) * 16 / 9 / 2) - 10 }));
    append(csPreview, previewVid,
      mkText('part_01_score_9.2.mp4', { sz: 10, bold: true, color: C.text, x: 12, y: cpH - 44 }),
      mkText('⭐ 9.2 score  ·  1:18 duration  ·  9:16', { sz: 9, color: C.textMuted, x: 12, y: cpH - 26 }),
    );
    append(f, csPreview);

    // Clips grid (right side)
    const clipsX = cenX + cpW + 16;
    const clipsW = cenW3 - cpW - 16;
    const clipsGrid = mkFrame('renderOutputList/clipsGrid', clipsW, cpH, { fill: C.bg, x: clipsX, y: cpY });
    clipsGrid.fills = [];
    const clipData = [[1, 9.2, 78, '9:16', 'done'], [2, 8.7, 95, '9:16', 'done'], [3, 7.1, 112, '9:16', 'done'], [4, 5.4, 88, '9:16', 'done'], [5, 3.2, 67, '9:16', 'failed']];
    const cols = 4;
    const cW = Math.floor((clipsW - (cols - 1) * 12) / cols);
    clipData.forEach(([r, sc, dur, asp, st], i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const cardH = Math.round(cW * 16 / 9) + 64;
      const card = mkClipCard(r, sc, dur, asp, st, { x: col * (cW + 12), y: row * (cardH + 12) });
      card.resize(cW, card.height);
      append(clipsGrid, card);
    });
    append(f, clipsGrid);
    drawBottomCollapsed(f);

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 06: History / Downloads ───────────────────────────────────────────────
  {
    const f = mkFrame('06 · History / Downloads', FW, FH, { x: 6 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'history' });
    drawStatusBar(f);

    // Download sidebar
    const dlSb = mkFrame('Sidebar/Download', SIDEBAR_W, FH - TOPBAR_H - STATUS_H, { fill: C.sidebar, x: 0, y: TOPBAR_H });
    append(dlSb,
      mkText('Download Setup', { sz: 9, bold: true, color: C.textDim, x: 14, y: 12 }),
      mkRect(SIDEBAR_W, 1, C.border, { x: 0, y: 30 }),
      mkText('1. LINKS', { sz: 8, bold: true, color: C.accent, x: 14, y: 42 }),
    );
    const textarea = mkFrame('linksInput', SIDEBAR_W - 28, 80, { fill: C.inputBg, x: 14, y: 58 });
    textarea.cornerRadius = 8;
    textarea.strokes = solid(C.inputBdr);
    textarea.strokeWeight = 1;
    append(textarea, mkText('https://youtube.com/watch?v=...\nhttps://www.instagram.com/reel/...\nhttps://www.tiktok.com/@user/...', { sz: 9, color: C.textMuted, x: 8, y: 8 }));
    append(dlSb, textarea);
    append(dlSb,
      mkBtn('Parse Links', { variant: 'secondary', x: 14, y: 146, w: 100, h: 28 }),
      mkBtn('Clear', { variant: 'ghost', x: 122, y: 146, w: 60, h: 28 }),
      mkText('2. SAVE FOLDER', { sz: 8, bold: true, color: C.accent, x: 14, y: 188 }),
    );
    append(dlSb, mkInput('Destination', 'Choose a local save folder', { x: 14, y: 202, w: SIDEBAR_W - 28 }));
    append(dlSb,
      mkBtn('Start Download', { variant: 'primary', x: 14, y: 274, w: SIDEBAR_W - 28, h: 36 }),
      mkBtn('Retry Failed', { variant: 'secondary', x: 14, y: 318, w: SIDEBAR_W - 28, h: 28 }),
      mkBtn('Open Folder', { variant: 'ghost', x: 14, y: 354, w: SIDEBAR_W - 28, h: 28 }),
    );
    append(f, dlSb);

    // Center: History view
    const histX = SIDEBAR_W + 20;
    const histW = FW - SIDEBAR_W - 40;
    append(f,
      mkText('Render History', { sz: 22, bold: true, color: C.text, x: histX, y: TOPBAR_H + 20 }),
      mkText('Recent render activity · click a job to view clips', { sz: 12, color: C.textMuted, x: histX, y: TOPBAR_H + 48 }),
      mkRect(histW, 1, C.border, { x: histX, y: TOPBAR_H + 68 }),
    );

    const histItems = [
      { id: 'job_20250115_143012', status: 'done', parts: 5, score: 8.7, src: 'source_video_01.mp4', dur: '32m 18s', ts: '2025-01-15  14:30' },
      { id: 'job_20250115_101245', status: 'done', parts: 3, score: 7.2, src: 'podcast_episode_42.mp4', dur: '18m 02s', ts: '2025-01-15  10:12' },
      { id: 'job_20250114_183312', status: 'failed', parts: 0, score: 0, src: 'long_stream.mp4', dur: '—', ts: '2025-01-14  18:33' },
      { id: 'job_20250114_120000', status: 'done', parts: 8, score: 9.1, src: 'interview_raw.mp4', dur: '1h 04m', ts: '2025-01-14  12:00' },
    ];
    histItems.forEach((item, i) => {
      const rowY = TOPBAR_H + 82 + i * 72;
      const row = mkFrame('histRow/' + item.id, histW, 64, { fill: _hex('#0a0f1a'), x: histX, y: rowY });
      row.cornerRadius = 10;
      row.strokes = solid(C.border, 0.3);
      row.strokeWeight = 1;
      const stColor = item.status === 'done' ? C.success : C.danger;
      const stDot = mkRect(8, 8, stColor, { cr: 4, x: 14, y: 28 });
      append(row, stDot,
        mkText(item.id, { sz: 11, bold: true, color: C.text, x: 30, y: 10 }),
        mkText(item.src + '  ·  ' + item.ts, { sz: 10, color: C.textMuted, x: 30, y: 28 }),
        mkText(item.status, { sz: 10, color: stColor, x: 30, y: 44 }),
        mkText(item.parts + ' clips', { sz: 11, bold: true, color: C.textDim, x: histW - 320, y: 24 }),
        mkText('Score: ' + (item.score || '—'), { sz: 11, color: item.score >= 8 ? C.success : item.score >= 5 ? C.warn : C.textMuted, x: histW - 220, y: 24 }),
        mkText(item.dur, { sz: 10, color: C.textMuted, x: histW - 140, y: 24 }),
        mkBtn('View Clips', { variant: 'ghost', x: histW - 104, y: 18, w: 84, h: 28 }),
      );
      append(f, row);
    });

    drawBottomCollapsed(f);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 07: Empty / Loading / Error States ────────────────────────────────────
  {
    const f = mkFrame('07 · Empty / Loading / Error States', FW, FH, { x: 7 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);

    append(f, mkText('07 — Empty / Loading / Error States', { sz: 20, bold: true, color: C.accentLt, x: 40, y: TOPBAR_H + 20 }));

    const stateY = TOPBAR_H + 64;
    const stateW = Math.round((FW - 80 - 48) / 4);

    // State 1: Empty render home
    const s1 = mkFrame('State/Empty', stateW, 280, { fill: C.elevated, x: 40, y: stateY });
    s1.cornerRadius = 14;
    s1.strokes = solid(C.border, 0.4);
    s1.strokeWeight = 1;
    const emptyIcon = mkRect(48, 48, C.accent, { cr: 24, op: 0.15, x: Math.round((stateW - 48) / 2), y: 40 });
    append(s1, emptyIcon,
      mkText('🎬', { sz: 22, x: Math.round((stateW - 22) / 2), y: 52 }),
      mkText('No source selected', { sz: 13, bold: true, color: C.text, x: 16, y: 110, maxW: stateW - 32, align: 'CENTER' }),
      mkText('Paste a YouTube link or choose\na local video to begin.', { sz: 11, color: C.textMuted, x: 16, y: 134, maxW: stateW - 32, align: 'CENTER' }),
    );
    append(s1, mkBtn('Get Started', { variant: 'primary', x: Math.round((stateW - 120) / 2), y: 220, w: 120, h: 36 }));
    append(f, s1, mkText('Empty — No source', { sz: 11, bold: true, color: C.textMuted, x: 40, y: stateY + 296 }));

    // State 2: Loading spinner (model warmup)
    const s2X = 40 + stateW + 16;
    const s2 = mkFrame('State/Loading', stateW, 280, { fill: C.elevated, x: s2X, y: stateY });
    s2.cornerRadius = 14;
    s2.strokes = solid(C.border, 0.4);
    s2.strokeWeight = 1;
    const spinner = mkRect(48, 48, { r: 0, g: 0, b: 0 }, { cr: 24, x: Math.round((stateW - 48) / 2), y: 40 });
    spinner.fills = [];
    spinner.strokes = [{ type: 'SOLID', color: C.accent }, { type: 'SOLID', color: C.border }];
    spinner.strokeWeight = 4;
    append(s2, spinner,
      mkText('Loading models…', { sz: 13, bold: true, color: C.text, x: 16, y: 110, maxW: stateW - 32, align: 'CENTER' }),
      mkText('Whisper model initializing.\nFFmpeg backend starting.', { sz: 11, color: C.textMuted, x: 16, y: 134, maxW: stateW - 32, align: 'CENTER' }),
    );
    const warmupBar = mkRect(stateW - 32, 6, C.border, { cr: 3, x: 16, y: 220 });
    const warmupFill = mkRect(Math.round((stateW - 32) * 0.6), 6, C.accent, { cr: 3, x: 16, y: 220 });
    append(s2, warmupBar, warmupFill, mkText('Loading models…', { sz: 10, color: C.textMuted, x: 16, y: 234 }));
    append(f, s2, mkText('Loading — Model warmup (warmup_chip ID)', { sz: 11, bold: true, color: C.textMuted, x: s2X, y: stateY + 296 }));

    // State 3: Failed render
    const s3X = 40 + (stateW + 16) * 2;
    const s3 = mkFrame('State/Error', stateW, 280, { fill: _hex('#1a0a0a'), x: s3X, y: stateY });
    s3.cornerRadius = 14;
    s3.strokes = solid(C.danger, 0.3);
    s3.strokeWeight = 1;
    append(s3,
      mkText('❌', { sz: 22, x: Math.round((stateW - 22) / 2), y: 50 }),
      mkText('Render Failed', { sz: 13, bold: true, color: C.danger, x: 16, y: 96, maxW: stateW - 32, align: 'CENTER' }),
      mkText('Part 3 failed: FFmpeg exit code 1.\nOutput folder may be full.', { sz: 11, color: C.textMuted, x: 16, y: 120, maxW: stateW - 32, align: 'CENTER' }),
    );
    append(s3,
      mkBtn('↺ Retry', { variant: 'primary', x: Math.round((stateW - 100) / 2), y: 190, w: 100, h: 32 }),
      mkBtn('View Logs', { variant: 'ghost', x: Math.round((stateW - 100) / 2), y: 232, w: 100, h: 28 }),
    );
    append(f, s3, mkText('Error — Render failed state', { sz: 11, bold: true, color: C.textMuted, x: s3X, y: stateY + 296 }));

    // State 4: Stuck/stalled warning
    const s4X = 40 + (stateW + 16) * 3;
    const s4 = mkFrame('State/Stuck', stateW, 280, { fill: _hex('#1a1200'), x: s4X, y: stateY });
    s4.cornerRadius = 14;
    s4.strokes = solid(C.warn, 0.35);
    s4.strokeWeight = 1;
    append(s4,
      mkText('⚠', { sz: 22, x: Math.round((stateW - 22) / 2), y: 50 }),
      mkText('Part Stalled', { sz: 13, bold: true, color: C.warn, x: 16, y: 96, maxW: stateW - 32, align: 'CENTER' }),
      mkText('Part 3 has not progressed\nfor over 45 seconds.', { sz: 11, color: C.textMuted, x: 16, y: 120, maxW: stateW - 32, align: 'CENTER' }),
    );
    const stuckPill = mkPill('Stuck · 48s', { bg: _hex('#1a1200'), textColor: C.warn, x: Math.round((stateW - 80) / 2), y: 170, h: 22 });
    append(s4, stuckPill, mkBtn('Force Retry Part', { variant: 'ghost', x: Math.round((stateW - 130) / 2), y: 210, w: 130, h: 28 }));
    append(f, s4, mkText('Stuck — RENDER_MONITOR_STALL_MS = 45000', { sz: 11, bold: true, color: C.textMuted, x: s4X, y: stateY + 296 }));

    // YT download progress state
    const ytY = stateY + 340;
    append(f, mkText('YouTube Download Progress (sidebar)', { sz: 14, bold: true, color: C.text, x: 40, y: ytY }));
    const ytPanel = mkFrame('ytDlProgress', 280, 70, { fill: _hex('#061830'), x: 40, y: ytY + 24 });
    ytPanel.cornerRadius = 10;
    ytPanel.strokes = solid(C.accent, 0.3);
    ytPanel.strokeWeight = 1;
    append(ytPanel,
      mkText('Downloading YouTube video…', { sz: 11, color: C.textDim, x: 10, y: 10 }),
      mkText('42s', { sz: 10, color: C.textMuted, x: 220, y: 10 }),
      mkBtn('✕ Cancel', { variant: 'ghost', x: 196, y: 8, w: 70, h: 22 }),
    );
    const ytTrack = mkRect(260, 3, C.border, { cr: 2, x: 10, y: 40 });
    const ytFill = mkRect(Math.round(260 * 0.42), 3, C.accent, { cr: 2, x: 10, y: 40 });
    append(ytPanel, ytTrack, ytFill, mkText('42% · 24.8 MB/s', { sz: 9, color: C.textMuted, x: 10, y: 52 }));
    append(f, ytPanel);

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 08: Design System / Tokens ────────────────────────────────────────────
  {
    const f = mkFrame('08 · Design System / Tokens', FW, FH, { x: 8 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f);
    drawStatusBar(f);

    const bodyY = TOPBAR_H + 20;
    append(f,
      mkText('08 — Design System / Tokens (app.css :root)', { sz: 20, bold: true, color: C.accentLt, x: 40, y: bodyY }),
      mkText('All values match the real CSS. Use these when building UI components.', { sz: 12, color: C.textMuted, x: 40, y: bodyY + 28 }),
    );

    // Colors
    const colY = bodyY + 60;
    append(f, mkText('Colors', { sz: 14, bold: true, color: C.text, x: 40, y: colY }));
    const colorRows = [
      ['Background', [['--bg', '#0b0f1c', C.bg], ['--sidebar-bg', '#070a14', C.sidebar], ['--card-bg', '#111827', C.card]]],
      ['Borders & Inputs', [['--card-border', '#1e2d45', C.border], ['--input-bg', '#0d1526', C.inputBg], ['--input-border', '#1e3154', C.inputBdr]]],
      ['Text', [['--text', '#e2e8f0', C.text], ['--text-muted', '#7a8fa8', C.textMuted], ['--text-dim', '#94a3b8', C.textDim]]],
      ['Accent', [['--accent', '#3b82f6', C.accent], ['--accent2 (purple)', '#8b5cf6', C.purple], ['--accent-light', '#60a5fa', C.accentLt]]],
      ['States', [['--success', '#10b981', C.success], ['--warn', '#f59e0b', C.warn], ['--danger', '#ef4444', C.danger]]],
    ];
    colorRows.forEach(([groupName, swatches], gi) => {
      const gy = colY + 28 + gi * 48;
      append(f, mkText(groupName, { sz: 10, bold: true, color: C.textMuted, x: 40, y: gy }));
      swatches.forEach(([name, hex_, col], si) => {
        const sx = 40 + si * 200;
        append(f,
          mkRect(32, 32, col, { cr: 8, x: sx, y: gy + 14 }),
          mkText(name, { sz: 9, bold: true, color: C.textDim, x: sx + 40, y: gy + 16 }),
          mkText(hex_, { sz: 9, color: C.textMuted, x: sx + 40, y: gy + 30 }),
        );
      });
    });

    // Typography
    const tyY = colY + 330;
    append(f, mkRect(FW - 80, 1, C.border, { x: 40, y: tyY - 10 }));
    append(f, mkText('Typography', { sz: 14, bold: true, color: C.text, x: 40, y: tyY }));
    const tyRows = [
      ['24px Bold', 24, true, 'Page title / Hero heading'],
      ['18px Bold', 18, true, 'Section heading'],
      ['14px Bold', 14, true, 'Card title / Key label'],
      ['12px Regular', 12, false, 'Body / form fields'],
      ['11px Regular', 11, false, 'Secondary / pill text'],
      ['9px Bold (uppercase)', 9, true, 'Section eyebrow / token label'],
      ['8px Regular', 8, false, 'Micro label / annotation'],
    ];
    tyRows.forEach(([label, sz, bold, usage], i) => {
      const col_ = i % 2 === 0 ? 0 : Math.round(FW / 2) - 40;
      const row_ = Math.floor(i / 2);
      append(f,
        mkText(label, { sz, bold, color: C.text, x: 40 + col_, y: tyY + 24 + row_ * 44 }),
        mkText('→ ' + usage, { sz: 10, color: C.textMuted, x: 40 + col_, y: tyY + 24 + row_ * 44 + sz + 2 }),
      );
    });

    // Border radius / spacing
    const spY = tyY + 228;
    append(f, mkRect(FW - 80, 1, C.border, { x: 40, y: spY - 10 }));
    append(f, mkText('Border Radius & Spacing', { sz: 14, bold: true, color: C.text, x: 40, y: spY }));
    const radii = [['--radius-sm: 10px', 10], ['--radius: 14px', 14], ['--radius-lg: 20px', 20]];
    radii.forEach(([label, r], i) => {
      append(f,
        mkRect(48, 48, C.elevated, { cr: r, stroke: C.border, sw: 1, x: 40 + i * 100, y: spY + 24 }),
        mkText(label, { sz: 9, color: C.textDim, x: 40 + i * 100, y: spY + 80 }),
      );
    });

    // Button variants
    const btnY = spY + 105;
    append(f, mkText('Button Variants', { sz: 14, bold: true, color: C.text, x: 40, y: btnY }));
    append(f,
      mkBtn('Primary', { variant: 'primary', x: 40, y: btnY + 24, w: 120, h: 36 }),
      mkBtn('Secondary', { variant: 'secondary', x: 172, y: btnY + 24, w: 120, h: 36 }),
      mkBtn('Ghost', { variant: 'ghost', x: 304, y: btnY + 24, w: 120, h: 36 }),
    );
    append(f,
      mkText('Primary: gradient accent → white text', { sz: 9, color: C.textMuted, x: 40, y: btnY + 68 }),
      mkText('Secondary: #1e2d45 bg → --text', { sz: 9, color: C.textMuted, x: 172, y: btnY + 68 }),
      mkText('Ghost: transparent → border', { sz: 9, color: C.textMuted, x: 304, y: btnY + 68 }),
    );

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 09: CSS Layout Fix Notes ───────────────────────────────────────────────
  {
    const f = mkFrame('09 · CSS Layout Fix Notes', FW, FH, { x: 9 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f);
    drawStatusBar(f);

    const bodyY2 = TOPBAR_H + 20;
    append(f,
      mkText('09 — CSS Layout Fix Notes', { sz: 20, bold: true, color: C.accentLt, x: 40, y: bodyY2 }),
      mkText('Issues found during static audit of app.css (16,000+ lines). Fixes applied with minimal impact.', { sz: 12, color: C.textMuted, x: 40, y: bodyY2 + 28 }),
    );

    const issues = [
      {
        id: 'FIX-01',
        title: 'Bottom panel occupies row-3 space when runtime is mounted in center',
        status: 'FIXED',
        severity: C.success,
        desc: 'When mountRenderRuntimePanel() runs, abpToolbar + rcBottom move into render_runtime_mount\n(inside mainArea). The appBottomPanel gets class renderCompatWrapper + display:none.\nBUT grid-template-rows still allocates clamp(260px,40vh,420px) for row-3.\nThis wastes 34% of viewport height when render is active.',
        fix: 'Added CSS: .appShell:has(#appBottomPanel.renderCompatWrapper) {\n  grid-template-rows: 42px minmax(0,1fr) 0 28px !important;\n}',
        file: 'backend/static/css/app.css (end of file)',
      },
      {
        id: 'FIX-02',
        title: 'Multiple conflicting abpCollapsed heights across CSS phases',
        status: 'NOTED',
        severity: C.warn,
        desc: 'Phase definitions use 160px (line 1416), 120px (line 3695), 140px (line 4582) for abpCollapsed.\nLast rule wins = 140px. Only toolbar is visible (44px). 96px of dead space below toolbar.',
        fix: 'Acceptable for now — 140px gives visual breathing room. No fix needed unless\ntoolbar collapses look broken at specific viewport heights.',
        file: 'backend/static/css/app.css',
      },
      {
        id: 'FIX-03',
        title: 'renderOutputList relies on mainArea scroll (not internal scroll)',
        status: 'BY DESIGN',
        severity: C.accent,
        desc: 'The clips grid (renderOutputList / .clipsGrid) has no max-height or overflow.\nScrolling happens via mainArea.overflow-y:auto which is correct.\nPartsProgressGrid has max-height:220px + overflow:auto — internal scroll OK.\nevent_log_render has overflow-y:auto — internal scroll OK.',
        fix: 'No fix needed. mainArea scroll is correct behavior for clip gallery.\nDo not add max-height to renderOutputList — it would break at different viewport sizes.',
        file: 'backend/static/css/app.css',
      },
      {
        id: 'FIX-04',
        title: 'rs-main column definitions repeated across phases with conflicting values',
        status: 'NOTED',
        severity: C.warn,
        desc: 'rs-main is defined in Phase I (line 3704: 280px 1fr 360px),\nPhase K (line 4585: minmax(240px,0.85fr) minmax(360px,1.55fr) minmax(260px,0.95fr)),\nand later responsive overrides. Final value depends on cascade order and viewport.',
        fix: 'CSS architecture issue — 16k+ lines with phase-based overrides is high maintenance.\nFor future: consolidate into a single :root-driven grid definition.',
        file: 'backend/static/css/app.css (maintenance risk)',
      },
    ];

    issues.forEach((issue, i) => {
      const issueY = bodyY2 + 60 + i * 180;
      const issueBox = mkFrame('issue/' + issue.id, FW - 80, 168, { fill: C.elevated, x: 40, y: issueY });
      issueBox.cornerRadius = 12;
      issueBox.strokes = solid(issue.severity, 0.3);
      issueBox.strokeWeight = 1;
      const statusColors = { FIXED: C.success, NOTED: C.warn, 'BY DESIGN': C.accent };
      append(issueBox,
        mkPill(issue.id, { bg: C.inputBg, textColor: C.textDim, x: 14, y: 12, h: 22 }),
        mkPill(issue.status, { bg: issue.severity, textColor: C.white, x: 80, y: 12, h: 22 }),
        mkText(issue.title, { sz: 13, bold: true, color: C.text, x: 14, y: 44 }),
        mkText(issue.desc, { sz: 10, color: C.textDim, x: 14, y: 66, maxW: Math.round((FW - 80) / 2) - 28 }),
        mkText('FIX:', { sz: 9, bold: true, color: issue.severity, x: Math.round((FW - 80) / 2) + 14, y: 66 }),
        mkText(issue.fix, { sz: 9, color: C.textDim, x: Math.round((FW - 80) / 2) + 14, y: 82, maxW: Math.round((FW - 80) / 2) - 28 }),
        mkText('→ ' + issue.file, { sz: 9, color: C.accentLt, x: 14, y: 148 }),
      );
      append(f, issueBox);
    });

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  // ── 10: Developer Handoff ──────────────────────────────────────────────────
  {
    const f = mkFrame('10 · Developer Handoff', FW, FH, { x: 10 * (FW + GAP), y: 0 });
    append(f, mkRect(FW, FH, C.bg));
    drawTopbar(f);
    drawStatusBar(f);

    const bodyY3 = TOPBAR_H + 20;
    append(f,
      mkText('10 — Developer Handoff', { sz: 20, bold: true, color: C.accentLt, x: 40, y: bodyY3 }),
      mkText('Component → HTML ID/class mapping. These IDs must NOT be renamed — JS depends on them.', { sz: 12, color: C.textMuted, x: 40, y: bodyY3 + 28 }),
    );

    // Protected IDs table
    const tableY = bodyY3 + 60;
    append(f, mkText('Protected DOM IDs (render pipeline dependencies)', { sz: 14, bold: true, color: C.danger, x: 40, y: tableY }));

    const criticalIDs = [
      ['event_log_render', 'rcLogList', 'Main render log container — JS appends log lines here'],
      ['job_bar', '.progressValue', 'Render progress bar fill element — width set by JS'],
      ['job_percent', '', 'Percentage display text — textContent set by JS'],
      ['job_stage_pill', '.pill.primaryPill', 'Stage indicator pill — text + data-stage set by JS'],
      ['job_title', '', 'Active job title — textContent set by JS'],
      ['job_meta_1', '.abpJobMeta', 'Job metadata line 1'],
      ['job_meta_2', '.abpJobMeta', 'Job metadata line 2'],
      ['rc_active_card', '.rcActiveCard', 'Active render card in bottom panel'],
      ['rc_active_title', '.rcActiveTitle', 'Active render step text'],
      ['rc_active_bar', '.rcActiveProgress span', 'Active card progress'],
      ['rc_part_cards', '.rcQueueGrid', 'Part cards grid container'],
      ['rc_queue_summary', '.rcPanelMeta', 'Queue summary text ("N waiting")'],
      ['rc_active_badge', '.rcPanelBadge', 'Active badge ("Rendering" / "Idle")'],
      ['abp_retry_btn', '', 'Retry button (hidden in compat wrapper)'],
      ['abp_error_block', '', 'Error display block'],
      ['render_active_panel', '.renderActivePanel', 'Main render active view panel'],
      ['render_runtime_mount', '.renderRuntimeMount', 'JS moves toolbar+rcBottom here'],
      ['render_output_panel', '.renderOutputPanel', 'Clip gallery panel after render'],
      ['render_output_list', '.renderOutputList.clipsGrid', 'Clip cards grid'],
      ['render_completion_bar', '.renderCompletionBar', 'Completion banner'],
    ];

    const colWs = [220, 200, FW - 80 - 220 - 200];
    const headers = ['ID', 'CSS Class / Selector', 'Description'];
    headers.forEach((h, ci) => {
      append(f, mkText(h, { sz: 10, bold: true, color: C.accent, x: 40 + colWs.slice(0, ci).reduce((a, b) => a + b, 0), y: tableY + 24 }));
    });
    append(f, mkRect(FW - 80, 1, C.accent, { op: 0.3, x: 40, y: tableY + 38 }));

    criticalIDs.forEach(([id, cls, desc], ri) => {
      const rowY2 = tableY + 44 + ri * 22;
      const rowBg = ri % 2 === 0 ? C.elevated : C.bg;
      append(f, mkRect(FW - 80, 20, rowBg, { op: ri % 2 === 0 ? 0.5 : 0, x: 40, y: rowY2 }));
      append(f,
        mkText(id, { sz: 10, bold: true, color: C.accentLt, x: 44, y: rowY2 + 4 }),
        mkText(cls || '—', { sz: 10, color: C.textDim, x: 44 + colWs[0], y: rowY2 + 4 }),
        mkText(desc, { sz: 10, color: C.textMuted, x: 44 + colWs[0] + colWs[1], y: rowY2 + 4 }),
      );
    });

    // How to run this plugin
    const howY = tableY + 44 + criticalIDs.length * 22 + 20;
    if (howY < FH - STATUS_H - 120) {
      append(f, mkRect(FW - 80, 1, C.border, { x: 40, y: howY - 8 }));
      append(f, mkText('How to use this Figma import', { sz: 14, bold: true, color: C.text, x: 40, y: howY }));
      const steps = [
        '1. Open Figma Desktop or Figma Web',
        '2. Go to Plugins → Development → New Plugin',
        '3. Choose "Run once" (no UI) or create manifest.json with "main": "code.js"',
        '4. Paste this entire file into code.js',
        '5. Run the plugin — page "AI Clip Studio — Static UI Review Import" will be created',
        '6. All 11 frames appear; use Ctrl+Shift+H to fit viewport',
      ];
      steps.forEach((s, i) => {
        append(f, mkText(s, { sz: 11, color: C.textDim, x: 40, y: howY + 24 + i * 20 }));
      });
    }

    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     STEP 7 — Viewport + close
  ───────────────────────────────────────────────────── */
  figma.currentPage.selection = allFrames;
  figma.viewport.scrollAndZoomIntoView(allFrames);
  figma.closePlugin('✅ AI Clip Studio — 11 frames imported successfully!');
})();
