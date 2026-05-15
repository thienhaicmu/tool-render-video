/**
 * AI Clip Studio — V2 REDESIGN (CapCut/Adobe-inspired)
 * Paste into code.js of a Figma plugin and Run.
 *
 * Creates page: "AI Clip Studio — V2 Redesign"
 * Builds 21 frames covering:
 *   - Cover & design philosophy
 *   - Design tokens (colors, type, spacing)
 *   - Component library (buttons, inputs, cards, nav, progress)
 *   - App shell + render flow + monitor + output + history + states
 *   - Developer handoff with protected DOM IDs
 *
 * Style direction: Adobe-blue (#4d7cff) + Creative purple (#a855f7)
 *   Deeper neutral base (#0a0a0c), 4-level elevation,
 *   CapCut-signature active border-left bar,
 *   compact density, Inter Display + JetBrains Mono.
 *
 * NOTE: All structure-level DOM IDs from the production build are
 * preserved in frame "20 · Dev Handoff". Visual redesign only —
 * the JS bindings in render-ui.js / editor-view.js / upload-manager.js
 * stay compatible.
 */

(async () => {
  /* ─────────────────────────────────────────────────────
     STEP 1 — Fonts (load all weights up front)
  ───────────────────────────────────────────────────── */
  await Promise.all([
    figma.loadFontAsync({ family: 'Inter', style: 'Regular' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Medium' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Semi Bold' }).catch(() => figma.loadFontAsync({ family: 'Inter', style: 'Bold' })),
    figma.loadFontAsync({ family: 'Inter', style: 'Bold' }),
    figma.loadFontAsync({ family: 'JetBrains Mono', style: 'Regular' }).catch(() => figma.loadFontAsync({ family: 'Inter', style: 'Regular' })),
    figma.loadFontAsync({ family: 'JetBrains Mono', style: 'Bold' }).catch(() => figma.loadFontAsync({ family: 'Inter', style: 'Bold' })),
  ]);

  /* ─────────────────────────────────────────────────────
     STEP 2 — Target page
  ───────────────────────────────────────────────────── */
  const PAGE_NAME = 'AI Clip Studio — V2 Redesign';
  let targetPage = figma.pages.find(p => p.name === PAGE_NAME);
  if (!targetPage) {
    targetPage = figma.createPage();
    targetPage.name = PAGE_NAME;
  }
  figma.currentPage = targetPage;
  // Clean previous run if exists
  for (const child of [...targetPage.children]) child.remove();

  /* ─────────────────────────────────────────────────────
     STEP 3 — Color tokens (CapCut/Adobe-inspired)
     Deeper neutrals + dual accent (Adobe-blue + purple)
  ───────────────────────────────────────────────────── */
  const _hex = h => ({
    r: parseInt(h.slice(1, 3), 16) / 255,
    g: parseInt(h.slice(3, 5), 16) / 255,
    b: parseInt(h.slice(5, 7), 16) / 255,
  });

  const C = {
    // Neutrals — deeper, warmer than original navy
    bg950:     _hex('#08080b'),   // deepest base (chrome edges)
    bg900:     _hex('#0a0a0c'),   // app background
    bg850:     _hex('#101014'),   // panel base
    bg800:     _hex('#16161c'),   // sidebar / topbar
    bg750:     _hex('#1c1c24'),   // card surface
    bg700:     _hex('#24242e'),   // elevated / hover
    bg650:     _hex('#2d2d3a'),   // floating / active
    border:    _hex('#2a2a35'),   // divider
    borderHi:  _hex('#3a3a48'),   // input border
    borderFc:  _hex('#4d7cff'),   // input focus

    // Text scale
    text:      _hex('#f4f4f8'),   // primary
    textHi:    _hex('#ffffff'),   // strong
    textMid:   _hex('#b8b8c4'),   // body secondary
    textMut:   _hex('#85859a'),   // muted (labels)
    textDim:   _hex('#5a5a6e'),   // hint / placeholder

    // Accent system
    primary:   _hex('#4d7cff'),   // Adobe-blue
    primaryHi: _hex('#6b93ff'),
    primaryLo: _hex('#3a63d6'),
    primaryGl: _hex('#1e3a8a'),   // glow / soft bg

    secondary: _hex('#a855f7'),   // Creative purple
    secondHi:  _hex('#c084fc'),
    secondLo:  _hex('#8b3fd9'),
    secondGl:  _hex('#581c87'),

    // Semantic
    success:   _hex('#22c55e'),
    warn:      _hex('#f59e0b'),
    danger:    _hex('#ef4444'),
    info:      _hex('#06b6d4'),

    // Utility
    white:     _hex('#ffffff'),
    black:     _hex('#000000'),
    overlay:   _hex('#000000'),
  };

  /* ─────────────────────────────────────────────────────
     STEP 4 — Design constants
  ───────────────────────────────────────────────────── */
  const FW = 1440;
  const FH = 900;
  const GAP = 120;

  // App chrome dimensions (production-grade)
  const TOPBAR_H = 48;
  const STATUS_H = 24;
  const SIDEBAR_W = 280;
  const SIDEBAR_W_COLL = 64;
  const INSPECTOR_W = 380;
  const BOTTOM_FULL = 320;
  const BOTTOM_COLL = 56;

  // Type scale
  const TY = {
    display:  { sz: 28, bold: true },
    h1:       { sz: 22, bold: true },
    h2:       { sz: 18, bold: true },
    h3:       { sz: 15, bold: true },
    body:     { sz: 13, bold: false },
    bodyB:    { sz: 13, bold: true },
    small:    { sz: 12, bold: false },
    smallB:   { sz: 12, bold: true },
    micro:    { sz: 11, bold: false },
    microB:   { sz: 11, bold: true },
    label:    { sz: 10, bold: true },    // section eyebrows (uppercase)
    tiny:     { sz: 9,  bold: false },
  };

  // Radius scale
  const R = { xs: 4, sm: 6, md: 8, lg: 12, xl: 16, pill: 999 };

  // Spacing scale (4/8 grid)
  const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

  /* ─────────────────────────────────────────────────────
     STEP 5 — Core helpers
  ───────────────────────────────────────────────────── */
  const solid = (c, a = 1) => [{ type: 'SOLID', color: c, opacity: a }];

  function mkRect(w, h, color, opts = {}) {
    const { cr = 0, op = 1, x = 0, y = 0, name = '', stroke, sw = 1, dashed = false } = opts;
    const n = figma.createRectangle();
    n.resize(Math.max(1, w), Math.max(1, h));
    n.fills = color ? solid(color, op) : [];
    if (cr) n.cornerRadius = cr;
    n.x = x; n.y = y;
    if (name) n.name = name;
    if (stroke) {
      n.strokes = solid(stroke);
      n.strokeWeight = sw;
      if (dashed) n.dashPattern = [4, 4];
    }
    return n;
  }

  function mkText(str, opts = {}) {
    const {
      sz = 13, color, bold = false, medium = false, mono = false,
      x = 0, y = 0, name = '', maxW, align = 'LEFT', op = 1,
    } = opts;
    const n = figma.createText();
    const family = mono ? 'JetBrains Mono' : 'Inter';
    let style = 'Regular';
    if (bold) style = 'Bold';
    else if (medium) style = 'Medium';
    n.fontName = { family, style };
    n.textAutoResize = maxW ? 'HEIGHT' : 'WIDTH_AND_HEIGHT';
    if (maxW) n.resize(maxW, 20);
    n.characters = String(str);
    n.fontSize = sz;
    n.fills = solid(color || C.text, op);
    n.x = x; n.y = y;
    if (name) n.name = name;
    if (align !== 'LEFT') n.textAlignHorizontal = align;
    return n;
  }

  function mkFrame(name, w, h, opts = {}) {
    const { fill = C.bg900, x = 0, y = 0, clip = true, cr = 0, stroke, sw = 1, op = 1 } = opts;
    const f = figma.createFrame();
    f.name = name;
    f.resize(Math.max(1, w), Math.max(1, h));
    f.fills = fill ? solid(fill, op) : [];
    f.x = x; f.y = y;
    f.clipsContent = clip;
    if (cr) f.cornerRadius = cr;
    if (stroke) { f.strokes = solid(stroke); f.strokeWeight = sw; }
    return f;
  }

  function append(parent, ...children) {
    children.forEach(c => { if (c) parent.appendChild(c); });
  }

  function mkLine(w, opts = {}) {
    const { x = 0, y = 0, color = C.border, sw = 1 } = opts;
    const n = figma.createLine();
    n.resize(w, 0);
    n.x = x; n.y = y;
    n.strokes = solid(color);
    n.strokeWeight = sw;
    return n;
  }

  function mkVLine(h, opts = {}) {
    const { x = 0, y = 0, color = C.border, sw = 1 } = opts;
    const n = mkRect(sw, h, color, { x, y });
    return n;
  }

  // Estimate text width — rough, used for centering
  const estW = (str, sz) => Math.ceil(String(str).length * sz * 0.56);

  /* ─────────────────────────────────────────────────────
     STEP 6 — Component helpers
  ───────────────────────────────────────────────────── */

  // Pill / Badge — variants for status
  function mkPill(label, opts = {}) {
    const {
      bg = C.bg750, textColor = C.textMid, x = 0, y = 0,
      h = 22, px = 10, cr = R.pill, stroke, sw = 1, sz = 10, bold = true,
    } = opts;
    const w = estW(label, sz) + px * 2;
    const f = mkFrame('pill/' + label, w, h, { fill: bg, x, y, cr });
    f.clipsContent = false;
    if (stroke) { f.strokes = solid(stroke); f.strokeWeight = sw; }
    append(f, mkText(label, { sz, bold, color: textColor, x: px, y: (h - sz) / 2 - 1 }));
    return f;
  }

  // Status pill — semantic color presets
  function mkStatusPill(label, status = 'idle', opts = {}) {
    const presets = {
      idle:        { bg: C.bg750,   txt: C.textMut,   stroke: C.border },
      active:      { bg: C.primaryGl, txt: C.primaryHi, stroke: C.primary },
      success:     { bg: _hex('#0a3622'), txt: C.success, stroke: C.success },
      warn:        { bg: _hex('#3a2a08'), txt: C.warn,    stroke: C.warn },
      danger:      { bg: _hex('#3a1414'), txt: C.danger,  stroke: C.danger },
      rendering:   { bg: C.primaryGl,   txt: C.primaryHi, stroke: C.primary },
      transcribing:{ bg: C.secondGl,    txt: C.secondHi,  stroke: C.secondary },
      pro:         { bg: _hex('#1a1a28'), txt: C.secondHi,  stroke: C.secondary },
    };
    const p = presets[status] || presets.idle;
    return mkPill(label, { bg: p.bg, textColor: p.txt, stroke: p.stroke, sw: 1, ...opts });
  }

  // Button — 4 variants × 3 sizes
  function mkBtn(label, opts = {}) {
    const {
      variant = 'primary', size = 'md', x = 0, y = 0,
      icon = null, fullWidth = false, w: explicitW, h: explicitH,
    } = opts;

    const sizes = {
      sm: { h: 26, px: 10, sz: 11, cr: R.sm },
      md: { h: 34, px: 14, sz: 12, cr: R.md },
      lg: { h: 40, px: 18, sz: 13, cr: R.md },
    };
    const sz = sizes[size] || sizes.md;
    const w = explicitW || (estW(label, sz.sz) + sz.px * 2 + (icon ? 18 : 0));
    const h = explicitH || sz.h;

    const variants = {
      primary:   { bg: C.primary,   txt: C.white,    stroke: null,         sw: 0 },
      secondary: { bg: C.bg700,     txt: C.text,     stroke: C.borderHi,   sw: 1 },
      ghost:     { bg: null,        txt: C.textMid,  stroke: C.border,     sw: 1 },
      danger:    { bg: C.danger,    txt: C.white,    stroke: null,         sw: 0 },
      accentSec: { bg: C.secondary, txt: C.white,    stroke: null,         sw: 0 },
    };
    const v = variants[variant] || variants.primary;

    const f = mkFrame('btn/' + variant + '/' + label, w, h, {
      fill: v.bg, x, y, cr: sz.cr,
    });
    if (v.stroke) { f.strokes = solid(v.stroke); f.strokeWeight = v.sw; }

    let tx = sz.px;
    if (icon) {
      const ic = mkRect(12, 12, v.txt, { cr: 2, x: tx, y: (h - 12) / 2 });
      append(f, ic);
      tx += 18;
    }
    const textW = estW(label, sz.sz);
    if (!icon) tx = Math.max(sz.px, (w - textW) / 2);
    append(f, mkText(label, { sz: sz.sz, bold: true, color: v.txt, x: tx, y: (h - sz.sz) / 2 - 1 }));
    return f;
  }

  // Icon button — square, icon-only
  function mkIconBtn(opts = {}) {
    const { variant = 'ghost', size = 32, x = 0, y = 0, color, glyph } = opts;
    const variants = {
      primary: { bg: C.primary,  ic: C.white,   stroke: null },
      ghost:   { bg: null,       ic: C.textMid, stroke: C.border },
      filled:  { bg: C.bg700,    ic: C.textMid, stroke: C.borderHi },
      active:  { bg: C.primaryGl, ic: C.primaryHi, stroke: C.primary },
    };
    const v = variants[variant] || variants.ghost;
    const f = mkFrame('iconBtn', size, size, { fill: v.bg, x, y, cr: R.sm });
    if (v.stroke) { f.strokes = solid(v.stroke); f.strokeWeight = 1; }
    // Inner icon mark — simplified glyph
    const m = size * 0.5;
    if (glyph === 'play') {
      const tri = mkRect(0, 0, null, { x: 0, y: 0 });
      // simulate triangle with rect
      append(f, mkRect(m * 0.6, m * 0.6, color || v.ic, { cr: 1, x: (size - m * 0.6) / 2, y: (size - m * 0.6) / 2, op: 0.9 }));
    } else if (glyph === 'pause') {
      append(f,
        mkRect(3, m, color || v.ic, { x: size / 2 - 5, y: (size - m) / 2, cr: 1 }),
        mkRect(3, m, color || v.ic, { x: size / 2 + 2, y: (size - m) / 2, cr: 1 }),
      );
    } else if (glyph === 'close') {
      append(f, mkText('×', { sz: 18, color: color || v.ic, x: size / 2 - 5, y: size / 2 - 11 }));
    } else if (glyph === 'down') {
      append(f, mkText('▾', { sz: 10, color: color || v.ic, x: size / 2 - 5, y: size / 2 - 7 }));
    } else if (glyph === 'up') {
      append(f, mkText('▴', { sz: 10, color: color || v.ic, x: size / 2 - 5, y: size / 2 - 7 }));
    } else {
      // default square mark
      append(f, mkRect(size * 0.4, size * 0.4, color || v.ic, { cr: 2, x: (size - size * 0.4) / 2, y: (size - size * 0.4) / 2 }));
    }
    return f;
  }

  // Input field — label + box (with optional value, icon, state)
  function mkInput(label, value, opts = {}) {
    const {
      x = 0, y = 0, w = 240, state = 'idle',
      placeholder = '', hint = '', icon = null, suffix = null,
    } = opts;
    const labelH = label ? 16 : 0;
    const totalH = labelH + 38 + (hint ? 18 : 0);
    const g = mkFrame('input/' + (label || 'unnamed'), w, totalH, { fill: null, x, y });
    g.fills = [];
    g.clipsContent = false;

    if (label) {
      append(g, mkText(label.toUpperCase(), {
        sz: 10, bold: true, color: C.textMut, x: 0, y: 0,
      }));
    }

    const boxColors = {
      idle:    { bg: C.bg850, bdr: C.borderHi,        sw: 1 },
      focus:   { bg: C.bg850, bdr: C.borderFc,        sw: 1.5 },
      filled:  { bg: C.bg850, bdr: C.borderHi,        sw: 1 },
      error:   { bg: C.bg850, bdr: C.danger,          sw: 1 },
      success: { bg: C.bg850, bdr: C.success,         sw: 1 },
    };
    const bc = boxColors[state] || boxColors.idle;
    const box = mkFrame('inputBox', w, 38, { fill: bc.bg, x: 0, y: labelH, cr: R.md });
    box.strokes = solid(bc.bdr); box.strokeWeight = bc.sw;

    let textX = 12;
    if (icon) {
      append(box, mkRect(14, 14, C.textMut, { cr: 3, x: 10, y: 12 }));
      textX = 32;
    }
    const isPlaceholder = !value && placeholder;
    append(box, mkText(value || placeholder, {
      sz: 12, color: isPlaceholder ? C.textDim : C.text,
      x: textX, y: 12, maxW: w - textX - (suffix ? 60 : 12),
    }));
    if (suffix) {
      append(box, mkText(suffix, {
        sz: 11, bold: true, color: C.textMut, x: w - estW(suffix, 11) - 12, y: 12,
      }));
    }
    append(g, box);

    if (hint) {
      const hintCol = state === 'error' ? C.danger : state === 'success' ? C.success : C.textMut;
      append(g, mkText(hint, { sz: 11, color: hintCol, x: 0, y: labelH + 38 + 4 }));
    }
    return g;
  }

  // Select / dropdown field
  function mkSelect(label, value, opts = {}) {
    const g = mkInput(label, value, { ...opts, suffix: '▾' });
    return g;
  }

  // Section header (uppercase eyebrow + thin accent bar)
  function mkSectionHead(label, opts = {}) {
    const { x = 0, y = 0, w = 300, accent = C.primary } = opts;
    const g = mkFrame('sec/' + label, w, 22, { fill: null, x, y });
    g.fills = []; g.clipsContent = false;
    append(g,
      mkRect(2, 12, accent, { cr: 1, x: 0, y: 5 }),
      mkText(label.toUpperCase(), { sz: 10, bold: true, color: accent, x: 8, y: 5 }),
    );
    return g;
  }

  // Card / surface — 3 elevation levels
  function mkCard(w, h, opts = {}) {
    const { elevation = 'flat', x = 0, y = 0, name = 'card' } = opts;
    const styles = {
      flat:        { fill: C.bg850, stroke: C.border,   sw: 1, cr: R.lg },
      elevated:    { fill: C.bg750, stroke: C.borderHi, sw: 1, cr: R.lg },
      interactive: { fill: C.bg750, stroke: C.primary,  sw: 1, cr: R.lg },
      floating:    { fill: C.bg700, stroke: C.borderHi, sw: 1, cr: R.lg },
    };
    const s = styles[elevation] || styles.flat;
    const f = mkFrame(name, w, h, { fill: s.fill, x, y, cr: s.cr });
    f.strokes = solid(s.stroke); f.strokeWeight = s.sw;
    return f;
  }

  // Divider
  function mkDivider(w, opts = {}) {
    return mkLine(w, { ...opts, color: opts.color || C.border });
  }

  // Progress bar — linear
  function mkProgress(w, pct, opts = {}) {
    const { x = 0, y = 0, h = 6, color = C.primary, bg = C.bg700, cr = R.pill } = opts;
    const track = mkRect(w, h, bg, { cr, x, y });
    const fillW = Math.max(2, Math.round(w * Math.min(100, Math.max(0, pct)) / 100));
    const fill = mkRect(fillW, h, color, { cr, x, y, op: 0.95 });
    return [track, fill];
  }

  // Stepper indicator (1 → 2 → 3 → 4)
  function mkStepper(steps, currentIdx, opts = {}) {
    const { x = 0, y = 0, w = 600 } = opts;
    const g = mkFrame('stepper', w, 32, { fill: null, x, y });
    g.fills = []; g.clipsContent = false;
    const stepW = w / steps.length;
    steps.forEach((label, i) => {
      const isActive = i === currentIdx;
      const isDone = i < currentIdx;
      const dotColor = isActive ? C.primary : isDone ? C.success : C.border;
      const txtColor = isActive ? C.text : isDone ? C.textMid : C.textDim;
      const sx = i * stepW;
      const dot = mkFrame('step.dot', 22, 22, { fill: dotColor, x: sx, y: 5, cr: R.pill });
      if (!isActive && !isDone) { dot.strokes = solid(C.borderHi); dot.strokeWeight = 1; dot.fills = solid(C.bg900); }
      append(dot, mkText(isDone ? '✓' : String(i + 1), {
        sz: 10, bold: true, color: isDone ? C.white : isActive ? C.white : C.textMut,
        x: 8 - (isDone ? 2 : 0), y: 5,
      }));
      append(g, dot);
      append(g, mkText(label, { sz: 11, color: txtColor, medium: true, x: sx + 28, y: 8 }));
      if (i < steps.length - 1) {
        const lineColor = isDone ? C.success : C.border;
        append(g, mkRect(stepW - 130, 1, lineColor, { x: sx + 120, y: 15, op: 0.6 }));
      }
    });
    return g;
  }

  // Tab bar — horizontal pills
  function mkTabBar(tabs, activeIdx, opts = {}) {
    const { x = 0, y = 0, w = 400, h = 36, style = 'pill', accent = C.primary } = opts;
    const g = mkFrame('tabbar', w, h, { fill: style === 'underline' ? null : C.bg850, x, y, cr: style === 'underline' ? 0 : R.md });
    if (style === 'underline') g.fills = [];
    g.clipsContent = false;
    const tabW = (w - 4) / tabs.length;
    tabs.forEach((label, i) => {
      const isActive = i === activeIdx;
      const tx = 2 + i * tabW;
      if (style === 'pill') {
        const tabBg = isActive ? C.bg700 : null;
        const tab = mkFrame('tab/' + label, tabW - 4, h - 4, { fill: tabBg, x: tx, y: 2, cr: R.sm });
        if (!isActive) tab.fills = [];
        if (isActive) { tab.strokes = solid(accent, 0.3); tab.strokeWeight = 1; }
        append(tab, mkText(label, {
          sz: 11, bold: isActive, color: isActive ? accent : C.textMut,
          x: (tabW - 4 - estW(label, 11)) / 2, y: (h - 4 - 11) / 2 - 1,
        }));
        append(g, tab);
      } else {
        // underline style
        append(g, mkText(label, {
          sz: 12, bold: isActive, color: isActive ? C.text : C.textMut,
          x: tx + (tabW - estW(label, 12)) / 2, y: 8,
        }));
        if (isActive) {
          append(g, mkRect(28, 2, accent, { cr: 1, x: tx + (tabW - 28) / 2, y: h - 2 }));
        }
      }
    });
    return g;
  }

  // Toggle switch
  function mkToggle(on, opts = {}) {
    const { x = 0, y = 0, w = 36, h = 20 } = opts;
    const bg = on ? C.primary : C.bg700;
    const track = mkFrame('toggle', w, h, { fill: bg, x, y, cr: R.pill });
    if (!on) { track.strokes = solid(C.borderHi); track.strokeWeight = 1; }
    const knob = mkRect(h - 4, h - 4, C.white, { cr: R.pill, x: on ? w - h + 2 : 2, y: 2 });
    append(track, knob);
    return track;
  }

  // Avatar / colored dot
  function mkDot(size, color, opts = {}) {
    const { x = 0, y = 0 } = opts;
    return mkRect(size, size, color, { cr: R.pill, x, y });
  }

  // KPI / Metric tile
  function mkMetric(label, value, opts = {}) {
    const { x = 0, y = 0, w = 140, h = 72, color = C.primary, sub = '' } = opts;
    const c = mkCard(w, h, { elevation: 'flat', x, y, name: 'metric/' + label });
    append(c,
      mkText(label.toUpperCase(), { sz: 10, bold: true, color: C.textMut, x: 12, y: 12 }),
      mkText(value, { sz: 22, bold: true, color, x: 12, y: 28 }),
    );
    if (sub) append(c, mkText(sub, { sz: 10, color: C.textDim, x: 12, y: 54 }));
    return c;
  }


  /* ─────────────────────────────────────────────────────
     STEP 7 — Shared app chrome (topbar / sidebar / inspector / status)
     These are drawn into every screen frame for consistency.
  ───────────────────────────────────────────────────── */

  // ── Topbar ──────────────────────────────────────────
  function drawTopbar(parent, opts = {}) {
    const { activeTab = 'render', subtitle = 'Untitled Project', chip = 'Local AI · Ready' } = opts;
    const tb = mkFrame('Topbar', FW, TOPBAR_H, { fill: C.bg800, x: 0, y: 0 });
    tb.strokes = solid(C.border); tb.strokeWeight = 1;

    // Brand
    const brand = mkFrame('brand', 200, 32, { fill: null, x: 16, y: 8 });
    brand.fills = []; brand.clipsContent = false;
    const badge = mkFrame('badge', 32, 32, { fill: C.primary, x: 0, y: 0, cr: R.md });
    // Gradient simulation: overlay purple at 50% opacity
    const grad = mkRect(32, 32, C.secondary, { cr: R.md, x: 0, y: 0, op: 0.5 });
    append(badge, grad, mkText('AI', { sz: 11, bold: true, color: C.white, x: 9, y: 9 }));
    append(brand, badge);
    append(brand, mkText('Clip Studio', { sz: 14, bold: true, color: C.text, x: 42, y: 2 }));
    append(brand, mkText(subtitle, { sz: 10, color: C.textMut, x: 42, y: 19 }));
    append(tb, brand);

    // Center nav (Render | Download | History)
    const tabs = ['Render', 'Download', 'History'];
    const navX = 320;
    tabs.forEach((t, i) => {
      const isActive = t.toLowerCase() === activeTab;
      const tw = 88; const tx = navX + i * (tw + 4);
      const tabBg = isActive ? C.bg700 : null;
      const tabF = mkFrame('topnav/' + t, tw, 32, { fill: tabBg, x: tx, y: 8, cr: R.md });
      if (!isActive) tabF.fills = [];
      if (isActive) { tabF.strokes = solid(C.primary, 0.3); tabF.strokeWeight = 1; }
      append(tabF, mkText(t, {
        sz: 12, bold: isActive, color: isActive ? C.primaryHi : C.textMid,
        x: (tw - estW(t, 12)) / 2, y: 9,
      }));
      append(tb, tabF);
    });

    // Right side: status chip + action icons
    const rightStart = FW - 280;
    const statusChip = mkFrame('statusChip', 180, 26, { fill: C.bg750, x: rightStart, y: 11, cr: R.pill });
    statusChip.strokes = solid(C.border); statusChip.strokeWeight = 1;
    append(statusChip,
      mkDot(6, C.success, { x: 10, y: 10 }),
      mkText(chip, { sz: 11, color: C.textMid, medium: true, x: 22, y: 6 }),
    );
    append(tb, statusChip);

    // Icon buttons: notifications, help, settings, profile
    const iconSize = 32;
    const iconY = 8;
    const icons = [
      { glyph: 'down', variant: 'ghost' },
      { glyph: 'down', variant: 'ghost' },
      { glyph: 'down', variant: 'ghost' },
    ];
    icons.forEach((ic, i) => {
      const ibx = FW - 60 - (icons.length - 1 - i) * 38;
      append(tb, mkIconBtn({ size: iconSize, x: ibx, y: iconY, variant: ic.variant, glyph: ic.glyph }));
    });
    // Avatar
    const av = mkFrame('avatar', 32, 32, { fill: C.secondary, x: FW - 44, y: 8, cr: R.pill });
    const avg = mkRect(32, 32, C.primary, { cr: R.pill, x: 0, y: 0, op: 0.5 });
    append(av, avg, mkText('U', { sz: 12, bold: true, color: C.white, x: 11, y: 9 }));
    append(tb, av);

    append(parent, tb);
    return tb;
  }

  // ── Status bar (bottom) ─────────────────────────────
  function drawStatusBar(parent, opts = {}) {
    const { gpu = 'CUDA · RTX 4070', ffmpeg = 'FFmpeg 7.1', mem = '4.2 / 16 GB', whisper = 'Whisper loaded' } = opts;
    const sb = mkFrame('StatusBar', FW, STATUS_H, { fill: C.bg800, x: 0, y: FH - STATUS_H });
    sb.strokes = solid(C.border); sb.strokeWeight = 1;

    // Left cluster: ready dot + project state
    append(sb,
      mkDot(6, C.success, { x: 12, y: 9 }),
      mkText('Ready', { sz: 10, bold: true, color: C.textMid, x: 22, y: 6, mono: true }),
      mkText('·', { sz: 10, color: C.textDim, x: 56, y: 6 }),
      mkText(ffmpeg, { sz: 10, color: C.textMut, x: 66, y: 6, mono: true }),
      mkText('·', { sz: 10, color: C.textDim, x: 66 + estW(ffmpeg, 10) + 6, y: 6 }),
      mkText(gpu, { sz: 10, color: C.textMut, x: 66 + estW(ffmpeg, 10) + 18, y: 6, mono: true }),
      mkText('·', { sz: 10, color: C.textDim, x: 66 + estW(ffmpeg, 10) + 18 + estW(gpu, 10) + 6, y: 6 }),
      mkText(whisper, { sz: 10, color: C.textMut, x: 66 + estW(ffmpeg, 10) + 18 + estW(gpu, 10) + 18, y: 6, mono: true }),
    );

    // Right cluster: version + memory
    append(sb,
      mkText(mem, { sz: 10, color: C.textMut, x: FW - 280, y: 6, mono: true }),
      mkText('·', { sz: 10, color: C.textDim, x: FW - 280 + estW(mem, 10) + 6, y: 6 }),
      mkText('AI Clip Studio v3.0 · Electron + FastAPI', { sz: 10, color: C.textMut, x: FW - 220, y: 6, mono: true }),
    );
    append(parent, sb);
    return sb;
  }

  // ── Left Sidebar (Render Setup) ─────────────────────
  function drawSidebar(parent, opts = {}) {
    const {
      collapsed = false,
      sourceMode = 'youtube', // youtube | local
      outputSet = false,
      youtubeUrl = '',
      videoFile = '',
      outputDir = '',
    } = opts;
    const w = collapsed ? SIDEBAR_W_COLL : SIDEBAR_W;
    const sb = mkFrame('Sidebar', w, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: 0, y: TOPBAR_H,
    });
    sb.strokes = solid(C.border); sb.strokeWeight = 1;

    if (collapsed) {
      // Icon rail
      const icons = ['render', 'editor', 'preview', 'monitor', 'export'];
      icons.forEach((label, i) => {
        const isActive = i === 0;
        const btn = mkFrame('rail/' + label, 48, 48, {
          fill: isActive ? C.bg700 : null, x: 8, y: 12 + i * 56, cr: R.md,
        });
        if (!isActive) btn.fills = [];
        if (isActive) {
          btn.strokes = solid(C.primary, 0.3); btn.strokeWeight = 1;
          // CapCut signature left bar
          append(sb, mkRect(2, 32, C.primary, { cr: 1, x: 0, y: 20 + i * 56 }));
        }
        append(btn, mkRect(20, 20, isActive ? C.primaryHi : C.textMut, { cr: 4, x: 14, y: 14 }));
        append(sb, btn);
      });
      append(parent, sb);
      return sb;
    }

    // Expanded mode
    // Header
    append(sb,
      mkText('Render Setup', { sz: 13, bold: true, color: C.text, x: 16, y: 16 }),
      mkText('Source → Plan → Editor → Render → Review', { sz: 11, color: C.textMut, x: 16, y: 36 }),
      mkLine(w, { x: 0, y: 64, color: C.border }),
    );

    // Step 1: Source
    let cy = 80;
    append(sb, mkSectionHead('1 · Source', { x: 16, y: cy, w: w - 32 }));
    cy += 28;
    append(sb, mkSelect('Source Type', sourceMode === 'youtube' ? 'Video URL' : 'Local Video File', { x: 16, y: cy, w: w - 32 }));
    cy += 64;
    if (sourceMode === 'youtube') {
      append(sb, mkInput('Video URL', youtubeUrl, {
        x: 16, y: cy, w: w - 32,
        placeholder: 'YouTube, TikTok, Reels, Facebook…',
        state: youtubeUrl ? 'filled' : 'idle',
      }));
      cy += 58;
      append(sb, mkText('Use a public link, or download first.', { sz: 11, color: C.textMut, x: 16, y: cy, maxW: w - 32 }));
      cy += 24;
    } else {
      append(sb, mkInput('Local Video', videoFile, {
        x: 16, y: cy, w: w - 32,
        placeholder: 'No file selected',
        state: videoFile ? 'filled' : 'idle',
      }));
      cy += 60;
      append(sb, mkBtn('Choose Video', { variant: 'secondary', size: 'sm', x: 16, y: cy, w: 120 }));
      cy += 36;
    }

    // Step 2: Package
    cy += 8;
    append(sb, mkLine(w - 32, { x: 16, y: cy, color: C.border }));
    cy += 16;
    append(sb, mkSectionHead('2 · Package', { x: 16, y: cy, w: w - 32, accent: C.secondary }));
    cy += 28;
    append(sb, mkInput('Output Folder', outputDir, {
      x: 16, y: cy, w: w - 32,
      placeholder: 'D:\\videos\\output',
      state: outputSet ? 'success' : 'idle',
      hint: outputSet ? 'Folder is writable.' : 'Choose where clips, reports, and exports are saved.',
    }));
    cy += 76;
    append(sb, mkBtn('📁 Browse', { variant: 'secondary', size: 'sm', x: 16, y: cy, w: 96 }));

    // Actions footer (anchored bottom)
    const fy = FH - TOPBAR_H - STATUS_H - 132;
    append(sb,
      mkLine(w, { x: 0, y: fy, color: C.border }),
      mkBtn('Open Editor →', { variant: 'primary', size: 'lg', x: 16, y: fy + 16, w: w - 32, h: 44 }),
      mkText('Click to load the video into the editor.', {
        sz: 11, color: C.textMut, x: 16, y: fy + 72, maxW: w - 32,
      }),
      mkBtn('↺ Resume Job', { variant: 'ghost', size: 'sm', x: 16, y: fy + 96, w: 132 }),
    );

    append(parent, sb);
    return sb;
  }

  // ── Right Inspector ─────────────────────────────────
  function drawInspector(parent, opts = {}) {
    const {
      activeTab = 0, // 0=Cut, 1=Subtitle, 2=Text&Voice, 3=Audio, 4=Render
      videoTitle = 'source_video.mp4',
      videoMeta = '1h 24m · 1080p · 60fps',
      bodyDraw = null, // custom body draw function
    } = opts;
    const insp = mkFrame('Inspector', INSPECTOR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: FW - INSPECTOR_W, y: TOPBAR_H,
    });
    insp.strokes = solid(C.border); insp.strokeWeight = 1;

    // Header
    append(insp,
      mkText('Editor', { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
      mkText(videoTitle, { sz: 11, color: C.textMid, x: 16, y: 32, maxW: INSPECTOR_W - 32 }),
      mkText(videoMeta, { sz: 10, color: C.textMut, x: 16, y: 48, mono: true }),
      mkIconBtn({ size: 28, x: INSPECTOR_W - 44, y: 16, variant: 'ghost', glyph: 'close' }),
      mkLine(INSPECTOR_W, { x: 0, y: 76, color: C.border }),
    );

    // Tabs — underline style (Adobe-like)
    const tabs = ['Cut', 'Subtitle', 'Text', 'Audio', 'Render'];
    append(insp, mkTabBar(tabs, activeTab, {
      x: 0, y: 80, w: INSPECTOR_W, h: 40, style: 'underline', accent: C.primary,
    }));
    append(insp, mkLine(INSPECTOR_W, { x: 0, y: 120, color: C.border }));

    // Body — default Cut tab content if no custom drawer
    if (bodyDraw) {
      bodyDraw(insp, INSPECTOR_W, 132);
    } else {
      drawInspectorCutBody(insp, 132);
    }

    // Footer: primary action
    const fy = FH - TOPBAR_H - STATUS_H - 76;
    append(insp,
      mkLine(INSPECTOR_W, { x: 0, y: fy, color: C.border }),
      mkBtn('Start Render', { variant: 'primary', size: 'lg', x: 16, y: fy + 16, w: INSPECTOR_W - 32, h: 44 }),
    );

    append(parent, insp);
    return insp;
  }

  // Default inspector body — Cut tab
  function drawInspectorCutBody(insp, startY) {
    let cy = startY + 8;

    // Trim section
    append(insp, mkSectionHead('Trim', { x: 16, y: cy, w: INSPECTOR_W - 32 }));
    cy += 26;
    const [trimTrack, trimFill] = mkProgress(INSPECTOR_W - 32, 64, { x: 16, y: cy, h: 8, color: C.primary });
    append(insp, trimTrack, trimFill);
    // Trim handles
    append(insp,
      mkRect(4, 14, C.primary, { cr: 2, x: 16, y: cy - 3 }),
      mkRect(4, 14, C.primary, { cr: 2, x: 16 + Math.round((INSPECTOR_W - 32) * 0.64), y: cy - 3 }),
    );
    cy += 24;
    append(insp,
      mkInput('Start', '00:00:12', { x: 16, y: cy, w: (INSPECTOR_W - 40) / 2 }),
      mkInput('End',   '00:34:08', { x: 16 + (INSPECTOR_W - 40) / 2 + 8, y: cy, w: (INSPECTOR_W - 40) / 2 }),
    );
    cy += 70;

    // Quick presets
    append(insp, mkSectionHead('Quick Presets', { x: 16, y: cy, w: INSPECTOR_W - 32, accent: C.secondary }));
    cy += 26;
    const presets = [
      { icon: '📱', name: 'TikTok / Reels', sub: '9:16 · 60s' },
      { icon: '🎙', name: 'Podcast Clip',   sub: '1:1 · 90s' },
      { icon: '💼', name: 'Business Pro',  sub: '16:9 · clean' },
      { icon: '⬆',  name: 'High Quality',   sub: '4K · slow' },
    ];
    presets.forEach((p, i) => {
      const col = i % 2; const row = Math.floor(i / 2);
      const pw = (INSPECTOR_W - 40) / 2;
      const px = 16 + col * (pw + 8);
      const py = cy + row * 60;
      const isActive = i === 0;
      const pBtn = mkCard(pw, 52, {
        elevation: isActive ? 'interactive' : 'flat', x: px, y: py, name: 'preset/' + p.name,
      });
      append(pBtn,
        mkText(p.icon, { sz: 16, x: 10, y: 8 }),
        mkText(p.name, { sz: 11, bold: true, color: isActive ? C.primaryHi : C.text, x: 36, y: 8 }),
        mkText(p.sub, { sz: 10, color: C.textMut, x: 36, y: 24 }),
      );
      append(insp, pBtn);
    });
    cy += 60 * 2 + 8;

    // Output
    append(insp, mkSectionHead('Output', { x: 16, y: cy, w: INSPECTOR_W - 32 }));
    cy += 26;
    append(insp,
      mkSelect('Aspect Ratio', '3:4 Vertical', { x: 16, y: cy, w: (INSPECTOR_W - 40) / 2 }),
      mkSelect('Profile', 'Balanced', { x: 16 + (INSPECTOR_W - 40) / 2 + 8, y: cy, w: (INSPECTOR_W - 40) / 2 }),
    );
    cy += 70;
    append(insp,
      mkSelect('FPS', '60', { x: 16, y: cy, w: (INSPECTOR_W - 40) / 2 }),
      mkSelect('Device', 'Auto (GPU)', { x: 16 + (INSPECTOR_W - 40) / 2 + 8, y: cy, w: (INSPECTOR_W - 40) / 2 }),
    );
    cy += 70;

    // Toggle row
    const togRow = (label, value, on, ty) => {
      append(insp,
        mkText(label, { sz: 12, color: C.text, medium: true, x: 16, y: ty }),
        mkText(value, { sz: 11, color: C.textMut, x: 16, y: ty + 18 }),
        mkToggle(on, { x: INSPECTOR_W - 50, y: ty + 4 }),
      );
    };
    togRow('Motion-aware crop', 'Track speaker face', true, cy);
    cy += 44;
    togRow('Auto subtitles', 'Whisper · pro karaoke', true, cy);
    cy += 44;
    togRow('Cleanup temp files', 'Free disk after render', true, cy);
  }

  // ── Bottom panel (Render Monitor) — collapsed/expanded ──
  function drawBottomCollapsed(parent, opts = {}) {
    const { state = 'idle', text = 'No active render job', y } = opts;
    const py = y != null ? y : FH - STATUS_H - BOTTOM_COLL;
    const bp = mkFrame('BottomPanel/Collapsed', FW, BOTTOM_COLL, { fill: C.bg800, x: 0, y: py });
    bp.strokes = solid(C.border); bp.strokeWeight = 1;
    // Top accent line
    append(bp, mkRect(FW, 1, C.primary, { x: 0, y: 0, op: 0.4 }));

    append(bp,
      mkDot(8, state === 'idle' ? C.textDim : C.primary, { x: 16, y: 24 }),
      mkText(text, { sz: 12, bold: true, color: C.text, x: 32, y: 12 }),
      mkText('Channel — · Source —', { sz: 11, color: C.textMut, x: 32, y: 30, mono: true }),
    );

    // Progress track in middle
    const trackX = 280;
    const trackW = FW - 480;
    const [t1, f1] = mkProgress(trackW, 0, { x: trackX, y: 24, h: 8, color: C.primary });
    append(bp, t1, f1);
    append(bp, mkText('0%', { sz: 13, bold: true, color: C.textDim, x: trackX + trackW + 12, y: 20, mono: true }));

    // Right cluster
    append(bp,
      mkStatusPill('Idle', 'idle', { x: FW - 168, y: 18 }),
      mkIconBtn({ size: 36, x: FW - 52, y: 10, variant: 'ghost', glyph: 'up' }),
    );
    append(parent, bp);
    return bp;
  }

  function drawBottomExpanded(parent, opts = {}) {
    const {
      pct = 67,
      stage = 'rendering',
      partsData = null,
      jobTitle = 'Render — youtube_demo_clip',
      partLabel = 'Part 3 — Rendering 67%',
      partsCount = '3 / 5 done',
      sourceFile = 'source_video.mp4',
    } = opts;

    const py = FH - STATUS_H - BOTTOM_FULL;
    const bp = mkFrame('BottomPanel/Expanded', FW, BOTTOM_FULL, { fill: C.bg800, x: 0, y: py });
    bp.strokes = solid(C.border); bp.strokeWeight = 1;
    // Top accent
    append(bp, mkRect(FW, 1, C.primary, { x: 0, y: 0, op: 0.5 }));

    // ── Toolbar (44px) ──
    const tbH = 48;
    const toolbar = mkFrame('abpToolbar', FW, tbH, { fill: C.bg850, x: 0, y: 1 });
    toolbar.strokes = solid(C.border); toolbar.strokeWeight = 0;
    append(toolbar,
      mkDot(8, C.primary, { x: 16, y: 20 }),
      mkText(jobTitle, { sz: 12, bold: true, color: C.text, x: 30, y: 8, mono: true }),
      mkText(partsCount + '  ·  ' + sourceFile, { sz: 10, color: C.textMut, x: 30, y: 26, mono: true }),
    );
    const trackX = 360;
    const trackW = FW - 660;
    const [tt, tf] = mkProgress(trackW, pct, { x: trackX, y: 20, h: 8, color: C.primary });
    append(toolbar, tt, tf);
    append(toolbar,
      mkText(pct + '%', { sz: 14, bold: true, color: C.primaryHi, x: trackX + trackW + 12, y: 16, mono: true }),
      mkStatusPill(stage.charAt(0).toUpperCase() + stage.slice(1), stage === 'rendering' ? 'rendering' : 'active', { x: FW - 220, y: 14, h: 24 }),
      mkIconBtn({ size: 36, x: FW - 88, y: 6, variant: 'ghost', glyph: 'pause' }),
      mkIconBtn({ size: 36, x: FW - 48, y: 6, variant: 'ghost', glyph: 'down' }),
    );
    append(bp, toolbar);

    // ── Body: Queue (left 65%) + Logs (right 35%) ──
    const bodyY = tbH + 1;
    const bodyH = BOTTOM_FULL - bodyY;
    const qW = Math.round(FW * 0.62);

    // Queue panel
    const qPanel = mkFrame('rcQueuePanel', qW, bodyH, { fill: C.bg850, x: 0, y: bodyY });
    append(qPanel,
      mkText('Render Queue', { sz: 12, bold: true, color: C.text, x: 16, y: 14 }),
      mkPill(partsCount, { bg: C.bg700, textColor: C.textMid, x: 130, y: 10, h: 22 }),
      mkStatusPill('Rendering', 'rendering', { x: 200, y: 10 }),
      mkBtn('Open in Editor', { variant: 'ghost', size: 'sm', x: qW - 140, y: 10 }),
      mkLine(qW, { x: 0, y: 42, color: C.border }),
    );

    // Active card
    const activeCard = mkCard(qW - 24, 72, { elevation: 'interactive', x: 12, y: 52, name: 'rcActiveCard' });
    append(activeCard,
      mkText(partLabel, { sz: 12, bold: true, color: C.text, x: 14, y: 10 }),
      mkText('cutting → transcribing → rendering → done', {
        sz: 10, color: C.textMut, x: 14, y: 28, mono: true,
      }),
    );
    const [at, af] = mkProgress(qW - 56, pct, { x: 14, y: 50, h: 4, color: C.primary });
    append(activeCard, at, af);
    append(qPanel, activeCard);

    // Parts grid
    const parts = partsData || [
      [1, 'done', 100], [2, 'done', 100], [3, 'rendering', pct],
      [4, 'waiting', 0], [5, 'waiting', 0],
    ];
    const partsY = 138;
    parts.forEach(([no, stg, p], i) => {
      const col = i % 5; const row = Math.floor(i / 5);
      const card = mkPartCardV2(no, stg, p, {
        x: 12 + col * 118, y: partsY + row * 76,
      });
      append(qPanel, card);
    });
    append(bp, qPanel);

    // Log panel
    const logW = FW - qW;
    const logPanel = mkFrame('rcLogPanel', logW, bodyH, { fill: C.bg900, x: qW, y: bodyY });
    logPanel.strokes = solid(C.border); logPanel.strokeWeight = 1;
    append(logPanel,
      mkText('Live Log', { sz: 12, bold: true, color: C.text, x: 14, y: 14 }),
      mkPill('event_log_render', { bg: C.bg750, textColor: C.textDim, x: 80, y: 12, h: 20, sz: 9 }),
      mkBtn('Auto', { variant: 'ghost', size: 'sm', x: logW - 144, y: 10 }),
      mkBtn('Copy', { variant: 'ghost', size: 'sm', x: logW - 90, y: 10 }),
      mkBtn('Clear', { variant: 'ghost', size: 'sm', x: logW - 50, y: 10, w: 44 }),
      mkLine(logW, { x: 0, y: 42, color: C.border }),
    );
    // Log entries
    const logs = [
      ['08:42:12', '[system]', 'Job started · 5 parts queued', C.textMid],
      ['08:42:14', '[ffmpeg]', 'Part 1: scene detection complete', C.textMut],
      ['08:42:38', '[whisper]', 'Part 1: transcription done (24s)', C.textMut],
      ['08:43:02', '[ffmpeg]', 'Part 1: render → part_01.mp4', C.success],
      ['08:43:05', '[ffmpeg]', 'Part 2: scene detection complete', C.textMut],
      ['08:43:31', '[whisper]', 'Part 2: transcription started', C.textMut],
      ['08:44:01', '[ffmpeg]', 'Part 2: render → part_02.mp4', C.success],
      ['08:44:08', '[ffmpeg]', 'Part 3: cutting started', C.primaryHi],
      ['08:44:12', '[ffmpeg]', 'Part 3: 1080×1920 · motion crop', C.textMut],
      ['08:44:22', '[ffmpeg]', 'Part 3: rendering · ' + pct + '%', C.primaryHi],
    ];
    logs.forEach(([ts, tag, msg, col], i) => {
      const ly = 52 + i * 22;
      append(logPanel,
        mkText(ts, { sz: 10, color: C.textDim, x: 14, y: ly, mono: true }),
        mkText(tag, { sz: 10, bold: true, color: C.primary, x: 70, y: ly, mono: true }),
        mkText(msg, { sz: 10, color: col, x: 138, y: ly, mono: true, maxW: logW - 154 }),
      );
    });
    append(bp, logPanel);
    append(parent, bp);
    return bp;
  }

  // Part card v2 — compact, used inside queue grid
  function mkPartCardV2(no, stage, pct, opts = {}) {
    const { x = 0, y = 0 } = opts;
    const stageColors = {
      done:         C.success,
      rendering:    C.primary,
      transcribing: C.secondary,
      cutting:      C.warn,
      waiting:      C.textDim,
      failed:       C.danger,
    };
    const c = stageColors[stage] || C.textMut;
    const f = mkCard(108, 68, { elevation: 'flat', x, y, name: 'part/' + no });
    if (stage === 'rendering') {
      f.strokes = solid(c); f.strokeWeight = 1;
    } else {
      f.strokes = solid(c, 0.3); f.strokeWeight = 1;
    }
    append(f,
      mkText('Part ' + no, { sz: 11, bold: true, color: C.text, x: 10, y: 8 }),
      mkText(pct + '%', { sz: 10, color: C.textMut, x: 78, y: 9, mono: true }),
    );
    const [t, fl] = mkProgress(88, pct, { x: 10, y: 28, h: 4, color: c });
    append(f, t, fl);
    append(f, mkText(stage, { sz: 10, color: c, medium: true, x: 10, y: 40 }));
    return f;
  }

  // Clip output card (output gallery)
  function mkClipCardV2(rank, opts = {}) {
    const {
      x = 0, y = 0, score = 8.4, durationSec = 84,
      aspect = '9:16', status = 'done', title = 'Hook clip',
      thumbColor = C.bg700,
    } = opts;
    const sColor = score >= 8 ? C.success : score >= 6 ? C.warn : C.danger;
    const cardW = 200; const thumbH = aspect === '9:16' ? 240 : aspect === '1:1' ? 180 : 140;
    const cardH = thumbH + 96;
    const f = mkCard(cardW, cardH, {
      elevation: status === 'done' && score >= 8 ? 'interactive' : 'flat',
      x, y, name: 'clip/#' + rank,
    });
    f.clipsContent = true;
    if (status === 'done' && score >= 8) {
      f.strokes = solid(C.success, 0.7); f.strokeWeight = 1;
    }

    // Thumbnail area
    const thumb = mkFrame('thumb', cardW, thumbH, { fill: thumbColor, x: 0, y: 0 });
    // Faux gradient
    append(thumb, mkRect(cardW, thumbH, C.secondary, { x: 0, y: 0, op: 0.08 }));
    append(thumb, mkRect(cardW, thumbH, C.primary, { x: 0, y: thumbH / 2, op: 0.05, h: thumbH / 2 }));

    // Rank badge
    const rankB = mkFrame('rankBadge', 36, 22, { fill: C.bg950, x: 8, y: 8, cr: R.sm });
    rankB.fills = solid(C.bg950, 0.85);
    append(rankB, mkText('#' + rank, { sz: 11, bold: true, color: C.primaryHi, x: 8, y: 4, mono: true }));
    append(thumb, rankB);

    // Score badge (top-right)
    const scoreB = mkFrame('scoreBadge', 44, 22, { fill: sColor, x: cardW - 52, y: 8, cr: R.sm });
    scoreB.fills = solid(sColor, 0.18);
    scoreB.strokes = solid(sColor, 0.6); scoreB.strokeWeight = 1;
    append(scoreB, mkText('★ ' + score.toFixed(1), { sz: 10, bold: true, color: sColor, x: 6, y: 5 }));
    append(thumb, scoreB);

    // Duration (bottom-right)
    const mins = Math.floor(durationSec / 60);
    const secs = durationSec % 60;
    const dur = mkFrame('dur', 52, 20, { fill: C.bg950, x: cardW - 60, y: thumbH - 28, cr: R.sm });
    dur.fills = solid(C.bg950, 0.85);
    append(dur, mkText(`${mins}:${secs.toString().padStart(2, '0')}`, {
      sz: 10, bold: true, color: C.white, x: 10, y: 4, mono: true,
    }));
    append(thumb, dur);

    // Aspect (bottom-left)
    const asp = mkFrame('aspBadge', 40, 18, { fill: C.bg950, x: 8, y: thumbH - 26, cr: R.xs });
    asp.fills = solid(C.bg950, 0.7);
    append(asp, mkText(aspect, { sz: 9, bold: true, color: C.textMid, x: 6, y: 3 }));
    append(thumb, asp);

    // Play overlay (faint)
    const play = mkFrame('play', 44, 44, { fill: C.white, x: (cardW - 44) / 2, y: (thumbH - 44) / 2, cr: R.pill });
    play.fills = solid(C.white, 0.15);
    play.strokes = solid(C.white, 0.4); play.strokeWeight = 1.5;
    append(play, mkText('▶', { sz: 14, color: C.white, x: 16, y: 13 }));
    append(thumb, play);
    append(f, thumb);

    // Info section
    const info = mkFrame('info', cardW, 96, { fill: null, x: 0, y: thumbH });
    info.fills = [];
    append(info,
      mkText(title, { sz: 12, bold: true, color: C.text, x: 12, y: 10, maxW: cardW - 24 }),
      mkText('Part ' + rank, { sz: 10, color: C.textMut, x: 12, y: 30 }),
      mkStatusPill(status, status === 'done' ? 'success' : 'idle', { x: cardW - 72, y: 30 }),
    );
    // Action buttons
    append(info,
      mkBtn('Preview', { variant: 'ghost', size: 'sm', x: 12, y: 60, w: 80 }),
      mkBtn('Download', { variant: 'secondary', size: 'sm', x: 100, y: 60, w: 88 }),
    );
    append(f, info);
    return f;
  }

  // Center preview stage (editor video preview)
  function drawCenterPreview(parent, opts = {}) {
    const {
      x = SIDEBAR_W, y = TOPBAR_H, w = FW - SIDEBAR_W - INSPECTOR_W, h = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL,
      mode = 'editor', // editor | render-home | render-active
    } = opts;

    const stage = mkFrame('CenterStage', w, h, { fill: C.bg900, x, y });
    append(parent, stage);
    return stage;
  }


  /* ─────────────────────────────────────────────────────
     STEP 8 — Frame Builder
     Each frame is a 1440×900 desktop screen.
     Frames are placed in a grid: 4 columns × N rows.
  ───────────────────────────────────────────────────── */
  const allFrames = [];
  const COLS = 4;
  const placeFrame = (frame, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    frame.x = col * (FW + GAP);
    frame.y = row * (FH + GAP);
  };

  // Helper: page-title block (re-used across all frames)
  function drawPageTitle(parent, num, title, subtitle, opts = {}) {
    const { y = TOPBAR_H + 24, accent = C.primary } = opts;
    append(parent,
      mkPill('Frame ' + num, { bg: C.bg700, textColor: accent, x: 40, y, h: 24, sz: 11, stroke: accent, sw: 1 }),
      mkText(title, { sz: 22, bold: true, color: C.text, x: 40, y: y + 32 }),
    );
    if (subtitle) {
      append(parent, mkText(subtitle, { sz: 12, color: C.textMut, x: 40, y: y + 62, maxW: FW - 80 }));
    }
  }

  /* ─────────────────────────────────────────────────────
     FRAME 00 · Cover & Index
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('00 · Cover & Index', FW, FH, { fill: C.bg950 });

    // Hero left
    // Background glow
    const glow1 = mkRect(600, 600, C.primary, { cr: 300, x: -100, y: 200, op: 0.12 });
    const glow2 = mkRect(500, 500, C.secondary, { cr: 250, x: 700, y: -100, op: 0.1 });
    append(f, glow1, glow2);

    // Brand mark large
    const brandLg = mkFrame('brandLg', 88, 88, { fill: C.primary, x: 80, y: 200, cr: R.lg });
    const brandLgG = mkRect(88, 88, C.secondary, { cr: R.lg, x: 0, y: 0, op: 0.55 });
    append(brandLg, brandLgG, mkText('AI', { sz: 32, bold: true, color: C.white, x: 22, y: 22 }));
    append(f, brandLg);

    append(f,
      mkText('AI Clip Studio', { sz: 56, bold: true, color: C.textHi, x: 80, y: 310 }),
      mkText('V2 — Visual Redesign', { sz: 22, color: C.primaryHi, medium: true, x: 80, y: 380 }),
      mkText('CapCut/Adobe-inspired · Production-grade desktop creator workspace.', {
        sz: 14, color: C.textMid, x: 80, y: 414, maxW: 600,
      }),
      mkText('21 frames · Design tokens · Component library · Full screen flows · Dev handoff.', {
        sz: 12, color: C.textMut, x: 80, y: 442, maxW: 600,
      }),
    );

    // Spec pills
    const specs = [
      ['1440 × 900', 'Base canvas'],
      ['Inter + JetBrains Mono', 'Type system'],
      ['Adobe-blue + Purple', 'Accent system'],
      ['4 / 8 grid', 'Spacing'],
    ];
    specs.forEach((s, i) => {
      const sx = 80 + i * 240;
      const sy = 510;
      append(f,
        mkText(s[0], { sz: 16, bold: true, color: C.text, x: sx, y: sy, mono: true }),
        mkText(s[1], { sz: 11, color: C.textMut, x: sx, y: sy + 24 }),
      );
    });

    // Right side: Frame index
    const idxX = 800; const idxY = 100;
    append(f,
      mkText('Frame Index', { sz: 14, bold: true, color: C.text, x: idxX, y: idxY }),
      mkLine(560, { x: idxX, y: idxY + 24, color: C.border }),
    );
    const frames = [
      ['00', 'Cover & Index', 'this frame'],
      ['01', 'Tokens · Colors', 'palette + usage'],
      ['02', 'Tokens · Typography', 'type scale'],
      ['03', 'Tokens · Spacing & Radius', '4/8 grid'],
      ['04', 'Components · Buttons & Inputs', 'all states'],
      ['05', 'Components · Cards & Surfaces', 'elevation'],
      ['06', 'Components · Navigation', 'topbar/sidebar/tabs'],
      ['07', 'Components · Progress & Status', 'bars + pills'],
      ['08', 'Shell · App Architecture', 'grid + zones'],
      ['09', 'Render · Source Setup', 'sidebar interaction'],
      ['10', 'Render · Editor Active', 'hero screen'],
      ['11', 'Inspector · Cut tab', 'trim + presets'],
      ['12', 'Inspector · Subtitle tab', 'styling'],
      ['13', 'Inspector · Render tab', 'output options'],
      ['14', 'Monitor · Active expanded', 'rendering live'],
      ['15', 'Monitor · Collapsed/Idle', 'minimized'],
      ['16', 'Output · Clip Gallery', 'post-render'],
      ['17', 'Download Manager', 'source inbox'],
      ['18', 'History View', 'past jobs'],
      ['19', 'States · Empty/Loading/Error', 'edge cases'],
      ['20', 'Developer Handoff', 'protected IDs'],
    ];
    frames.forEach((row, i) => {
      const ry = idxY + 36 + i * 26;
      const rowF = mkFrame('idx/' + row[0], 560, 24, { fill: i % 2 === 0 ? C.bg850 : null, x: idxX, y: ry, cr: R.xs });
      if (i % 2 !== 0) rowF.fills = [];
      append(rowF,
        mkText(row[0], { sz: 11, bold: true, color: C.primaryHi, x: 10, y: 6, mono: true }),
        mkText(row[1], { sz: 11, color: C.text, x: 50, y: 6 }),
        mkText(row[2], { sz: 10, color: C.textMut, x: 320, y: 7 }),
      );
      append(f, rowF);
    });

    // Footer
    append(f,
      mkLine(FW - 160, { x: 80, y: FH - 80, color: C.border }),
      mkText('Open in Figma · Use Ctrl+Shift+H to fit all frames to viewport · Read frame 20 for dev handoff before implementing.', {
        sz: 11, color: C.textMut, x: 80, y: FH - 60,
      }),
    );

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 01 · Tokens · Colors
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('01 · Tokens · Colors', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '01', 'Color System', 'Adobe-blue primary + Creative purple secondary. Deeper neutrals with 4-level surface elevation for clear depth hierarchy.');

    const bodyY = TOPBAR_H + 130;

    // Color groups
    const groups = [
      ['Neutrals · Surface', [
        ['--bg-950', '#08080b', C.bg950, 'deepest chrome'],
        ['--bg-900', '#0a0a0c', C.bg900, 'app background'],
        ['--bg-850', '#101014', C.bg850, 'panel base'],
        ['--bg-800', '#16161c', C.bg800, 'sidebar / topbar'],
        ['--bg-750', '#1c1c24', C.bg750, 'card surface'],
        ['--bg-700', '#24242e', C.bg700, 'elevated / hover'],
        ['--bg-650', '#2d2d3a', C.bg650, 'floating / active'],
      ]],
      ['Neutrals · Borders & Text', [
        ['--border',    '#2a2a35', C.border,   'dividers'],
        ['--border-hi', '#3a3a48', C.borderHi, 'input border'],
        ['--text',      '#f4f4f8', C.text,     'primary'],
        ['--text-mid',  '#b8b8c4', C.textMid,  'body 2°'],
        ['--text-mut',  '#85859a', C.textMut,  'muted labels'],
        ['--text-dim',  '#5a5a6e', C.textDim,  'hint/placeholder'],
      ]],
      ['Primary · Adobe-blue', [
        ['--primary',     '#4d7cff', C.primary,   'main accent'],
        ['--primary-hi',  '#6b93ff', C.primaryHi, 'hover'],
        ['--primary-lo',  '#3a63d6', C.primaryLo, 'pressed'],
        ['--primary-gl',  '#1e3a8a', C.primaryGl, 'glow bg'],
      ]],
      ['Secondary · Creative purple', [
        ['--secondary',    '#a855f7', C.secondary, 'creative accent'],
        ['--secondary-hi', '#c084fc', C.secondHi,  'hover'],
        ['--secondary-lo', '#8b3fd9', C.secondLo,  'pressed'],
        ['--secondary-gl', '#581c87', C.secondGl,  'glow bg'],
      ]],
      ['Semantic', [
        ['--success', '#22c55e', C.success, 'done / ok'],
        ['--warn',    '#f59e0b', C.warn,    'caution'],
        ['--danger',  '#ef4444', C.danger,  'error / fail'],
        ['--info',    '#06b6d4', C.info,    'info'],
      ]],
    ];

    let gy = bodyY;
    groups.forEach(([groupName, swatches]) => {
      append(f,
        mkSectionHead(groupName, { x: 40, y: gy, w: FW - 80 }),
      );
      gy += 28;
      swatches.forEach((sw, si) => {
        const col = si % 4; const row = Math.floor(si / 4);
        const sx = 40 + col * 340;
        const sy = gy + row * 92;
        // Swatch tile
        const tile = mkCard(320, 80, { elevation: 'flat', x: sx, y: sy, name: 'sw/' + sw[0] });
        // Color block
        const block = mkRect(80, 64, sw[2], { cr: R.sm, x: 8, y: 8 });
        if (sw[1] === '#08080b' || sw[1] === '#0a0a0c') {
          block.strokes = solid(C.borderHi); block.strokeWeight = 1;
        }
        append(tile, block);
        // Info
        append(tile,
          mkText(sw[0], { sz: 12, bold: true, color: C.text, x: 100, y: 10, mono: true }),
          mkText(sw[1], { sz: 11, color: C.primaryHi, x: 100, y: 30, mono: true }),
          mkText(sw[3], { sz: 10, color: C.textMut, x: 100, y: 52, maxW: 210 }),
        );
        append(f, tile);
      });
      const rows = Math.ceil(swatches.length / 4);
      gy += rows * 92 + 16;
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 02 · Tokens · Typography
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('02 · Tokens · Typography', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '02', 'Type System', 'Inter for UI text, JetBrains Mono for timecodes / logs / IDs. Compact density like Adobe — 13px body, tight line-height.');

    const bodyY = TOPBAR_H + 130;

    // Type scale showcase (left column)
    const scale = [
      ['Display', 28, true,  'Display 28', 'page hero / dialog'],
      ['H1',      22, true,  'H1 Heading 22', 'page title'],
      ['H2',      18, true,  'H2 Section 18', 'section title'],
      ['H3',      15, true,  'H3 Card Title 15', 'card / panel title'],
      ['Body+',   13, true,  'Body Bold 13', 'emphasis · button'],
      ['Body',    13, false, 'Body Regular 13', 'paragraph · field value'],
      ['Small',   12, false, 'Small 12', 'meta · helper'],
      ['Micro',   11, false, 'Micro 11', 'pill · timestamp'],
      ['Label',   10, true,  'LABEL · UPPER 10', 'section eyebrow'],
    ];
    append(f, mkSectionHead('Type Scale', { x: 40, y: bodyY, w: 800 }));
    let ty = bodyY + 32;
    scale.forEach(([name, sz, bold, sample, usage]) => {
      const rowF = mkFrame('ty/' + name, 800, Math.max(sz + 24, 44), { fill: null, x: 40, y: ty });
      rowF.fills = []; rowF.clipsContent = false;
      append(rowF,
        mkText(name, { sz: 11, bold: true, color: C.textMut, x: 0, y: 6, mono: true }),
        mkText(sample, { sz, bold, color: C.text, x: 100, y: 0 }),
        mkText(usage, { sz: 11, color: C.textDim, x: 100, y: sz + 4 }),
      );
      append(f, rowF);
      ty += Math.max(sz + 24, 44) + 8;
    });

    // Mono font section
    append(f, mkSectionHead('JetBrains Mono · Numeric & Code', { x: 40, y: ty + 12, w: 800, accent: C.secondary }));
    ty += 44;
    const monoSamples = [
      ['00:01:23.450', 12, 'timecode'],
      ['Part 03 · 67%', 12, 'progress meta'],
      ['render_job_2025_05_15_abc123', 11, 'job id'],
      ['1080×1920 · 60fps · h264', 11, 'video spec'],
    ];
    monoSamples.forEach(([sample, sz, usage]) => {
      append(f,
        mkText(sample, { sz, color: C.text, mono: true, x: 40, y: ty + 12 }),
        mkText(usage, { sz: 11, color: C.textDim, x: 280, y: ty + 14 }),
      );
      ty += 28;
    });

    // Right column: Hierarchy preview (real-world example)
    const rx = 880;
    let ry = bodyY;
    append(f, mkSectionHead('Hierarchy in context', { x: rx, y: ry, w: FW - rx - 40, accent: C.secondary }));
    ry += 32;
    const previewCard = mkCard(FW - rx - 40, 480, { elevation: 'flat', x: rx, y: ry });
    append(previewCard,
      mkText('Editor', { sz: 13, bold: true, color: C.text, x: 20, y: 18 }),
      mkText('source_video.mp4', { sz: 11, color: C.textMid, x: 20, y: 36 }),
      mkText('1h 24m · 1080p · 60fps', { sz: 10, color: C.textMut, x: 20, y: 52, mono: true }),
      mkLine(FW - rx - 40, { x: 0, y: 80 }),
    );
    append(previewCard, mkSectionHead('Trim', { x: 20, y: 96, w: FW - rx - 80 }));
    const [tt, tf] = mkProgress(FW - rx - 80, 64, { x: 20, y: 130, h: 8 });
    append(previewCard, tt, tf);
    append(previewCard,
      mkInput('Start', '00:00:12', { x: 20, y: 152, w: 200 }),
      mkInput('End',   '00:34:08', { x: 232, y: 152, w: 200 }),
    );
    append(previewCard,
      mkSectionHead('Output', { x: 20, y: 230, w: 200 }),
      mkSelect('Aspect Ratio', '3:4 Vertical', { x: 20, y: 264, w: 200 }),
      mkSelect('Profile', 'Balanced', { x: 232, y: 264, w: 200 }),
    );
    append(previewCard,
      mkText('Motion-aware crop', { sz: 12, color: C.text, medium: true, x: 20, y: 358 }),
      mkText('Track speaker face automatically', { sz: 11, color: C.textMut, x: 20, y: 376 }),
      mkToggle(true, { x: FW - rx - 86, y: 362 }),
    );
    append(previewCard,
      mkBtn('Start Render', { variant: 'primary', size: 'lg', x: 20, y: 424, w: FW - rx - 80, h: 40 }),
    );
    append(f, previewCard);

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 03 · Tokens · Spacing & Radius
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('03 · Tokens · Spacing & Radius', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '03', 'Spacing & Radius', '4/8 base grid for spacing. Three radius levels. Consistent rhythm across all components.');

    const bodyY = TOPBAR_H + 130;

    // Spacing scale (left)
    append(f, mkSectionHead('Spacing scale · 4/8 base', { x: 40, y: bodyY, w: 640 }));
    const spaces = [
      ['xs',  4,  'inline icon gap'],
      ['sm',  8,  'tight cluster'],
      ['md', 12,  'form row spacing'],
      ['lg', 16,  'card padding'],
      ['xl', 24,  'section gap'],
      ['xxl',32,  'page rhythm'],
    ];
    let sy = bodyY + 36;
    spaces.forEach(([name, val, usage]) => {
      const rowF = mkFrame('sp/' + name, 640, 36, { fill: C.bg850, x: 40, y: sy, cr: R.sm });
      append(rowF,
        mkText(name, { sz: 11, bold: true, color: C.primaryHi, x: 12, y: 12, mono: true }),
        mkText(val + 'px', { sz: 11, color: C.text, x: 60, y: 12, mono: true }),
        mkRect(val, 14, C.primary, { cr: 2, x: 130, y: 11, op: 0.7 }),
        mkText(usage, { sz: 11, color: C.textMut, x: 300, y: 12 }),
      );
      append(f, rowF);
      sy += 44;
    });

    // Radius scale (right)
    append(f, mkSectionHead('Radius', { x: 720, y: bodyY, w: FW - 760, accent: C.secondary }));
    const radii = [
      ['xs',  R.xs,  'micro pill / tag'],
      ['sm',  R.sm,  'button / chip'],
      ['md',  R.md,  'input / small card'],
      ['lg',  R.lg,  'card / panel'],
      ['xl',  R.xl,  'modal / hero'],
      ['pill',R.pill,'status pill / avatar'],
    ];
    let ry = bodyY + 36;
    radii.forEach(([name, val, usage], i) => {
      const col = i % 3; const row = Math.floor(i / 3);
      const rx = 720 + col * 220;
      const rry = ry + row * 140;
      const tile = mkCard(200, 124, { elevation: 'flat', x: rx, y: rry });
      const block = mkRect(64, 64, C.primary, { cr: val, x: 16, y: 16, op: 0.85 });
      append(tile, block,
        mkText(name, { sz: 11, bold: true, color: C.primaryHi, x: 92, y: 20, mono: true }),
        mkText(val + 'px', { sz: 11, color: C.text, x: 92, y: 38, mono: true }),
        mkText(usage, { sz: 10, color: C.textMut, x: 16, y: 92, maxW: 168 }),
      );
      append(f, tile);
    });

    // Grid system bottom band
    const gridY = FH - STATUS_H - 200;
    append(f,
      mkLine(FW - 80, { x: 40, y: gridY - 16, color: C.border }),
      mkSectionHead('Grid system · 12-column · 24px gutter', { x: 40, y: gridY, w: FW - 80 }),
    );
    const gridX = 40; const gridW = FW - 80;
    const colW = (gridW - 11 * 24) / 12;
    for (let i = 0; i < 12; i++) {
      const cx = gridX + i * (colW + 24);
      append(f, mkRect(colW, 88, C.primary, { x: cx, y: gridY + 38, op: 0.08, cr: R.sm }));
      append(f, mkText(String(i + 1), { sz: 11, bold: true, color: C.textDim, x: cx + colW / 2 - 4, y: gridY + 78, mono: true }));
    }

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 04 · Components · Buttons & Inputs
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('04 · Components · Buttons & Inputs', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '04', 'Buttons & Inputs', 'Five button variants × three sizes. Inputs with idle / focus / filled / error / success states.');

    const bodyY = TOPBAR_H + 130;

    // Buttons matrix
    append(f, mkSectionHead('Buttons · variants × sizes', { x: 40, y: bodyY, w: 800 }));
    const variants = ['primary', 'secondary', 'ghost', 'danger', 'accentSec'];
    const sizes = ['sm', 'md', 'lg'];
    const colW = 140;
    // Header row
    sizes.forEach((sz, i) => {
      append(f, mkText(sz.toUpperCase(), {
        sz: 10, bold: true, color: C.textMut, x: 200 + i * colW, y: bodyY + 36, mono: true,
      }));
    });
    variants.forEach((v, vi) => {
      const ry = bodyY + 60 + vi * 52;
      append(f, mkText(v, { sz: 11, bold: true, color: C.text, x: 40, y: ry + 12 }));
      sizes.forEach((sz, si) => {
        const bx = 200 + si * colW;
        append(f, mkBtn(v === 'accentSec' ? 'AI Enhance' : v === 'danger' ? 'Delete' : 'Render', {
          variant: v, size: sz, x: bx, y: ry,
        }));
      });
    });

    // Icon buttons
    append(f, mkSectionHead('Icon Buttons', { x: 40, y: bodyY + 360, w: 600, accent: C.secondary }));
    const iconRow = bodyY + 396;
    const ibStates = [
      ['ghost', 'play'], ['active', 'pause'], ['filled', 'close'],
      ['primary', 'down'], ['ghost', 'up'], ['ghost', 'play'],
    ];
    ibStates.forEach((s, i) => {
      append(f, mkIconBtn({ variant: s[0], glyph: s[1], size: 36, x: 40 + i * 52, y: iconRow }));
    });

    // Inputs (right column)
    append(f, mkSectionHead('Input states', { x: 760, y: bodyY, w: 640 }));
    let iy = bodyY + 36;
    const inputs = [
      ['Project Name', 'Untitled Project', 'filled', '', 'Identifies the render job.'],
      ['Video URL', '', 'idle', 'YouTube, TikTok, Reels…', 'Paste any public video link.'],
      ['Output Folder', 'D:\\videos\\output', 'success', '', 'Folder is writable.'],
      ['API Key', 'sk_...XXXX', 'error', '', 'Invalid token. Check Settings.'],
      ['Search', '', 'focus', 'Type to search…', 'Press / to focus from anywhere.'],
    ];
    inputs.forEach((inp) => {
      append(f, mkInput(inp[0], inp[1], {
        x: 760, y: iy, w: 320, state: inp[2], placeholder: inp[3], hint: inp[4],
      }));
      iy += 84;
    });

    // Right of inputs: Toggles + Select
    append(f, mkSectionHead('Toggle & Select', { x: 1120, y: bodyY, w: 280, accent: C.secondary }));
    append(f,
      mkText('Motion-aware crop', { sz: 12, color: C.text, medium: true, x: 1120, y: bodyY + 40 }),
      mkText('On', { sz: 11, color: C.success, x: 1120, y: bodyY + 58 }),
      mkToggle(true, { x: 1120 + 200, y: bodyY + 44 }),
      mkText('Verbose logs', { sz: 12, color: C.text, medium: true, x: 1120, y: bodyY + 88 }),
      mkText('Off', { sz: 11, color: C.textMut, x: 1120, y: bodyY + 106 }),
      mkToggle(false, { x: 1120 + 200, y: bodyY + 92 }),
      mkSelect('FPS', '60 fps', { x: 1120, y: bodyY + 140, w: 260 }),
      mkSelect('Encoder', 'h264 · NVENC', { x: 1120, y: bodyY + 220, w: 260 }),
      mkSelect('Aspect Ratio', '3:4 Vertical', { x: 1120, y: bodyY + 300, w: 260 }),
    );

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 05 · Components · Cards & Surfaces
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('05 · Components · Cards & Surfaces', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '05', 'Cards & Surfaces', 'Four elevation levels. Use flat for content, elevated for groups, interactive for selectable, floating for popovers.');

    const bodyY = TOPBAR_H + 130;

    // 4 elevation samples
    append(f, mkSectionHead('Elevation levels', { x: 40, y: bodyY, w: FW - 80 }));
    const elevations = [
      ['flat',        'bg-850 · 1px border',     'content groups'],
      ['elevated',    'bg-750 · stronger border', 'cards / panels'],
      ['interactive', 'bg-750 · primary border', 'selectable items'],
      ['floating',    'bg-700 · hover surface',  'popovers / modals'],
    ];
    elevations.forEach((el, i) => {
      const cx = 40 + i * 340;
      const cy = bodyY + 36;
      const card = mkCard(320, 160, { elevation: el[0], x: cx, y: cy });
      append(card,
        mkText(el[0], { sz: 14, bold: true, color: C.text, x: 16, y: 16 }),
        mkText(el[1], { sz: 11, color: C.primaryHi, x: 16, y: 38, mono: true }),
        mkText(el[2], { sz: 11, color: C.textMut, x: 16, y: 60 }),
        mkBtn('Action', { variant: 'ghost', size: 'sm', x: 16, y: 110 }),
      );
      append(f, card);
    });

    // Metric tile examples
    append(f, mkSectionHead('Metric tiles · KPI', { x: 40, y: bodyY + 240, w: FW - 80, accent: C.secondary }));
    const metrics = [
      ['Active Jobs', '3', C.primaryHi, '2 rendering'],
      ['Completed Today', '24', C.success, '↑ 12% vs yesterday'],
      ['Avg Render Time', '2:14', C.text, 'per part'],
      ['Disk Free', '128 GB', C.warn, '4 jobs left'],
      ['GPU Usage', '78%', C.secondHi, 'CUDA · RTX 4070'],
      ['Queue Depth', '5', C.text, '~12 min ETA'],
    ];
    metrics.forEach((m, i) => {
      const col = i % 6;
      const mx = 40 + col * 220;
      append(f, mkMetric(m[0], m[1], { x: mx, y: bodyY + 280, w: 200, h: 84, color: m[2], sub: m[3] }));
    });

    // Clip cards (output gallery preview)
    append(f, mkSectionHead('Clip output cards · aspect-aware', { x: 40, y: bodyY + 400, w: FW - 80 }));
    const clips = [
      { rank: 1, score: 9.2, dur: 84,  aspect: '9:16', title: 'Hook · what made it work', status: 'done' },
      { rank: 2, score: 8.4, dur: 96,  aspect: '9:16', title: 'Insight 2 · proof points', status: 'done' },
      { rank: 3, score: 7.1, dur: 64,  aspect: '1:1',  title: 'Quote moment',             status: 'done' },
      { rank: 4, score: 6.8, dur: 120, aspect: '9:16', title: 'Setup beat',               status: 'done' },
      { rank: 5, score: 5.4, dur: 48,  aspect: '16:9', title: 'B-roll · skipped',         status: 'idle' },
    ];
    clips.forEach((cl, i) => {
      append(f, mkClipCardV2(cl.rank, {
        x: 40 + i * 220, y: bodyY + 440,
        score: cl.score, durationSec: cl.dur, aspect: cl.aspect,
        title: cl.title, status: cl.status,
      }));
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 06 · Components · Navigation
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('06 · Components · Navigation', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { activeTab: 'render' });
    drawStatusBar(f);
    drawPageTitle(f, '06', 'Navigation', 'Topbar, sidebar (expanded + collapsed icon rail), tab bars (pill + underline), and stepper.');

    const bodyY = TOPBAR_H + 130;

    // Topbar variants (reference: shown at top of every screen)
    append(f, mkSectionHead('Topbar · 48px · Brand + center tabs + status chip + actions', { x: 40, y: bodyY, w: FW - 80 }));
    append(f, mkText('See the active topbar above. Tab states: idle / active. Status chip shows AI runtime.', {
      sz: 11, color: C.textMut, x: 40, y: bodyY + 28,
    }));

    // Sidebar variants
    append(f, mkSectionHead('Sidebar · expanded 280px / collapsed 64px', { x: 40, y: bodyY + 60, w: FW - 80, accent: C.secondary }));

    // Mini expanded sidebar mock
    const sbW = 240;
    const sbH = 320;
    const sbExp = mkCard(sbW, sbH, { elevation: 'flat', x: 40, y: bodyY + 96 });
    append(sbExp,
      mkText('Expanded · 280px', { sz: 11, bold: true, color: C.textMut, x: 14, y: 12 }),
      mkText('Render Setup', { sz: 13, bold: true, color: C.text, x: 14, y: 32 }),
      mkLine(sbW, { x: 0, y: 60 }),
      mkSectionHead('1 · Source', { x: 14, y: 76, w: sbW - 28 }),
      mkInput('Video URL', '', { x: 14, y: 110, w: sbW - 28, placeholder: 'Paste a link…' }),
      mkSectionHead('2 · Package', { x: 14, y: 188, w: sbW - 28, accent: C.secondary }),
      mkInput('Output Folder', 'D:\\videos\\out', { x: 14, y: 220, w: sbW - 28, state: 'success' }),
    );
    append(f, sbExp);

    // Collapsed icon rail
    const sbColl = mkCard(80, sbH, { elevation: 'flat', x: 320, y: bodyY + 96 });
    append(sbColl, mkText('Collapsed · 64px', { sz: 11, bold: true, color: C.textMut, x: 8, y: 12 }));
    const railIcons = ['render', 'editor', 'preview', 'monitor', 'export'];
    railIcons.forEach((label, i) => {
      const isActive = i === 0;
      const btn = mkFrame('rail/' + label, 48, 44, {
        fill: isActive ? C.bg700 : null, x: 16, y: 40 + i * 52, cr: R.md,
      });
      if (!isActive) btn.fills = [];
      if (isActive) { btn.strokes = solid(C.primary, 0.3); btn.strokeWeight = 1; }
      if (isActive) append(sbColl, mkRect(2, 28, C.primary, { cr: 1, x: 0, y: 48 + i * 52 }));
      append(btn, mkRect(18, 18, isActive ? C.primaryHi : C.textMut, { cr: 4, x: 15, y: 13 }));
      append(sbColl, btn);
    });
    append(f, sbColl);

    // Tab bars: pill + underline
    append(f, mkSectionHead('Tab bars · pill + underline', { x: 440, y: bodyY + 60, w: FW - 480 }));
    append(f, mkText('Pill (background-filled)', { sz: 11, color: C.textMut, x: 440, y: bodyY + 96 }));
    append(f, mkTabBar(['Cut', 'Subtitle', 'Text', 'Audio', 'Render'], 0, {
      x: 440, y: bodyY + 116, w: 520, h: 36, style: 'pill', accent: C.primary,
    }));
    append(f, mkText('Underline (Adobe / Figma style)', { sz: 11, color: C.textMut, x: 440, y: bodyY + 170 }));
    append(f, mkTabBar(['Cut', 'Subtitle', 'Text', 'Audio', 'Render'], 2, {
      x: 440, y: bodyY + 190, w: 520, h: 40, style: 'underline', accent: C.primary,
    }));

    // Stepper
    append(f, mkSectionHead('Stepper · render flow indicator', { x: 440, y: bodyY + 260, w: FW - 480, accent: C.secondary }));
    append(f, mkStepper(['Source', 'Plan', 'Editor', 'Render', 'Review'], 2, {
      x: 440, y: bodyY + 296, w: 880,
    }));

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 07 · Components · Progress & Status
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('07 · Components · Progress & Status', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '07', 'Progress & Status', 'Linear bars by stage, status pills with semantic colors, part cards for render queue.');

    const bodyY = TOPBAR_H + 130;

    // Progress bars
    append(f, mkSectionHead('Progress bars · by stage', { x: 40, y: bodyY, w: 700 }));
    const bars = [
      ['Idle',         0,   C.textDim,   'before job starts'],
      ['Cutting',      18,  C.warn,      'ffmpeg scene detection'],
      ['Transcribing', 42,  C.secondary, 'whisper STT'],
      ['Rendering',    67,  C.primary,   'final encode'],
      ['Done',         100, C.success,   'output written'],
      ['Failed',       45,  C.danger,    'error state'],
    ];
    let by = bodyY + 36;
    bars.forEach((b, i) => {
      const rowF = mkFrame('bar/' + b[0], 700, 36, { fill: null, x: 40, y: by });
      rowF.fills = []; rowF.clipsContent = false;
      append(rowF,
        mkText(b[0], { sz: 12, bold: true, color: b[2], x: 0, y: 8, medium: true }),
        mkText(b[3], { sz: 10, color: C.textMut, x: 0, y: 24 }),
      );
      const [t, fl] = mkProgress(380, b[1], { x: 200, y: 14, h: 8, color: b[2] });
      append(rowF, t, fl);
      append(rowF, mkText(b[1] + '%', {
        sz: 12, bold: true, color: b[2], x: 600, y: 11, mono: true,
      }));
      append(f, rowF);
      by += 48;
    });

    // Status pills
    append(f, mkSectionHead('Status pills · semantic', { x: 40, y: by + 16, w: 700, accent: C.secondary }));
    const pills = [
      ['Idle',         'idle'],
      ['Active',       'active'],
      ['Success',      'success'],
      ['Warn',         'warn'],
      ['Danger',       'danger'],
      ['Rendering',    'rendering'],
      ['Transcribing', 'transcribing'],
      ['Pro',          'pro'],
    ];
    pills.forEach((p, i) => {
      const col = i % 4; const row = Math.floor(i / 4);
      append(f, mkStatusPill(p[0], p[1], { x: 40 + col * 180, y: by + 56 + row * 40, h: 26 }));
    });

    // Part cards (queue mini)
    append(f, mkSectionHead('Part cards · render queue', { x: 760, y: bodyY, w: FW - 800 }));
    const parts = [
      [1, 'done', 100],
      [2, 'done', 100],
      [3, 'rendering', 67],
      [4, 'transcribing', 28],
      [5, 'cutting', 12],
      [6, 'waiting', 0],
      [7, 'waiting', 0],
      [8, 'failed', 45],
    ];
    parts.forEach((p, i) => {
      const col = i % 4; const row = Math.floor(i / 4);
      append(f, mkPartCardV2(p[0], p[1], p[2], {
        x: 760 + col * 130, y: bodyY + 36 + row * 80,
      }));
    });

    // Circular progress mock + stepper indicator inline
    append(f, mkSectionHead('Job-level summary · radial + stepper', { x: 760, y: bodyY + 220, w: FW - 800 }));
    // Faux radial: ring with gap
    const cx = 800; const cy = bodyY + 264;
    const ringBg = mkRect(120, 120, C.bg700, { cr: 60, x: cx - 60, y: cy });
    const ringFg = mkRect(120, 120, C.primary, { cr: 60, x: cx - 60, y: cy, op: 0.18 });
    ringFg.strokes = solid(C.primary); ringFg.strokeWeight = 8;
    const inner = mkRect(80, 80, C.bg900, { cr: 40, x: cx - 40, y: cy + 20 });
    append(f, ringBg, ringFg, inner);
    append(f,
      mkText('67%', { sz: 22, bold: true, color: C.primaryHi, x: cx - 24, y: cy + 38, mono: true }),
      mkText('Part 3 of 5', { sz: 11, color: C.textMut, x: cx - 32, y: cy + 64 }),
    );

    // Inline summary
    append(f,
      mkText('Job · render_2025_05_15', { sz: 12, bold: true, color: C.text, x: cx + 100, y: cy + 16, mono: true }),
      mkText('Started 08:42 · ETA ~6 min', { sz: 11, color: C.textMut, x: cx + 100, y: cy + 36 }),
      mkStatusPill('Rendering', 'rendering', { x: cx + 100, y: cy + 60 }),
      mkStatusPill('GPU', 'pro', { x: cx + 180, y: cy + 60 }),
      mkBtn('View Logs', { variant: 'ghost', size: 'sm', x: cx + 100, y: cy + 100 }),
      mkBtn('Pause', { variant: 'secondary', size: 'sm', x: cx + 180, y: cy + 100 }),
    );

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 08 · Shell · App Architecture
     Annotated layout grid showing all 5 zones.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('08 · Shell · App Architecture', FW, FH, { fill: C.bg900 });

    // Draw all chrome zones
    drawTopbar(f);
    drawSidebar(f);
    drawInspector(f);
    drawBottomCollapsed(f, { text: 'No active render · click to expand' });
    drawStatusBar(f);

    // Center stage placeholder (workspace)
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });
    // Grid backdrop
    append(stage, mkRect(stageW, stageH, C.primary, { x: 0, y: 0, op: 0.02 }));
    append(stage,
      mkText('Center Workspace', { sz: 22, bold: true, color: C.text, x: 32, y: 32 }),
      mkText('Editor preview · render output · clip gallery', { sz: 13, color: C.textMut, x: 32, y: 60 }),
    );

    // Annotated zones with dashed borders + labels
    const annotate = (x, y, w, h, label, sub, color) => {
      const r = mkRect(w, h, color, { x, y, op: 0, stroke: color, sw: 2, dashed: true });
      append(f, r);
      const pillW = estW(label, 11) + 24;
      const tag = mkFrame('zoneTag/' + label, pillW, 22, { fill: color, x: x + 8, y: y + 8, cr: R.sm });
      tag.fills = solid(color, 0.9);
      append(tag, mkText(label, { sz: 11, bold: true, color: C.white, x: 10, y: 5 }));
      append(f, tag);
      if (sub) {
        append(f, mkText(sub, { sz: 10, color, x: x + 8, y: y + 36, mono: true }));
      }
    };

    annotate(0, 0, FW, TOPBAR_H, 'Topbar 48px', '#topbar · brand + nav + status', C.primary);
    annotate(0, TOPBAR_H, SIDEBAR_W, FH - TOPBAR_H - STATUS_H, 'Sidebar 280px', '.sidebar · Render Setup', C.secondary);
    annotate(stageX, stageY, stageW, stageH, 'Center 780×688', '.mainArea · workspace', C.info);
    annotate(FW - INSPECTOR_W, TOPBAR_H, INSPECTOR_W, FH - TOPBAR_H - STATUS_H, 'Inspector 380px', '#appInspector', C.warn);
    annotate(0, FH - STATUS_H - BOTTOM_COLL, FW, BOTTOM_COLL, 'Bottom 56px (coll.)', '#appBottomPanel', C.success);
    annotate(0, FH - STATUS_H, FW, STATUS_H, 'Status 24px', '#statusSystem', C.text);

    // Legend (overlay top-left, semi-transparent over center)
    const legend = mkCard(320, 200, { elevation: 'floating', x: stageX + stageW - 360, y: stageY + 20 });
    legend.opacity = 0.96;
    append(legend,
      mkText('Layout Grid', { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
      mkText('Desktop 1440 × 900', { sz: 11, color: C.textMut, x: 16, y: 34, mono: true }),
      mkLine(320, { x: 0, y: 60 }),
    );
    const legendItems = [
      ['Topbar',    '48px',  C.primary],
      ['Sidebar',   '280px (collapses to 64)', C.secondary],
      ['Center',    'flex',  C.info],
      ['Inspector', '380px', C.warn],
      ['Bottom',    '56 / 320px', C.success],
      ['Status',    '24px',  C.text],
    ];
    legendItems.forEach((l, i) => {
      const ly = 72 + i * 20;
      append(legend,
        mkRect(10, 10, l[2], { cr: 2, x: 16, y: ly + 3 }),
        mkText(l[0], { sz: 11, color: C.text, x: 32, y: ly, medium: true }),
        mkText(l[1], { sz: 11, color: C.textMut, x: 140, y: ly, mono: true }),
      );
    });
    append(f, legend);

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 09 · Render · Source Setup
     Sidebar interaction · user pasting URL · onboarding state.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('09 · Render · Source Setup', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'New project · setup' });
    drawSidebar(f, {
      youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      outputDir: 'D:\\videos\\output\\creator_x',
      outputSet: true,
    });
    drawStatusBar(f);

    // Center: onboarding state
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Stepper across top
    append(stage, mkStepper(['Source', 'Plan', 'Editor', 'Render', 'Review'], 0, {
      x: 32, y: 24, w: stageW - 64,
    }));

    // Big hero card center
    const heroW = 640;
    const hero = mkCard(heroW, 420, { elevation: 'elevated', x: (stageW - heroW) / 2, y: 90 });
    // Subtle gradient hint
    append(hero, mkRect(heroW, 100, C.primary, { x: 0, y: 0, op: 0.06, cr: R.lg }));

    append(hero,
      mkText('Welcome back, Creator', { sz: 22, bold: true, color: C.text, x: 32, y: 28 }),
      mkText('Paste a video URL on the left, choose an output folder,', { sz: 13, color: C.textMid, x: 32, y: 62 }),
      mkText('then hit "Open Editor" to start cutting.', { sz: 13, color: C.textMid, x: 32, y: 80 }),
      mkLine(heroW - 64, { x: 32, y: 116 }),
    );

    // 3 quick start tiles
    const tiles = [
      { title: 'From YouTube',   sub: 'Paste any public URL', icon: '🔗', accent: C.primary },
      { title: 'From Local File', sub: 'Open a .mp4 / .mov', icon: '📁', accent: C.secondary },
      { title: 'Resume Job',     sub: 'Continue last render', icon: '↺', accent: C.warn },
    ];
    tiles.forEach((t, i) => {
      const tx = 32 + i * 200;
      const tile = mkCard(184, 140, {
        elevation: i === 0 ? 'interactive' : 'flat',
        x: tx, y: 140, name: 'tile/' + t.title,
      });
      append(tile,
        mkText(t.icon, { sz: 22, x: 16, y: 16 }),
        mkText(t.title, { sz: 13, bold: true, color: i === 0 ? C.primaryHi : C.text, x: 16, y: 56 }),
        mkText(t.sub, { sz: 11, color: C.textMut, x: 16, y: 78, maxW: 152 }),
      );
      if (i === 0) {
        append(tile, mkRect(2, 24, t.accent, { cr: 1, x: 0, y: 16 }));
      }
      append(hero, tile);
    });

    // Tips block
    append(hero,
      mkSectionHead('Tips', { x: 32, y: 304, w: heroW - 64, accent: C.secondary }),
      mkDot(4, C.primary, { x: 36, y: 340 }),
      mkText('YouTube / TikTok / Reels / Facebook supported.', { sz: 12, color: C.textMid, x: 48, y: 332 }),
      mkDot(4, C.primary, { x: 36, y: 362 }),
      mkText('Output folder must be writable. SSD recommended.', { sz: 12, color: C.textMid, x: 48, y: 354 }),
      mkDot(4, C.primary, { x: 36, y: 384 }),
      mkText('You can change all settings later in the Inspector.', { sz: 12, color: C.textMid, x: 48, y: 376 }),
    );
    append(stage, hero);
    append(f, stage);

    // Inspector — empty state
    const insp = mkFrame('Inspector', INSPECTOR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: FW - INSPECTOR_W, y: TOPBAR_H,
    });
    insp.strokes = solid(C.border); insp.strokeWeight = 1;
    append(insp,
      mkText('Editor', { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
      mkText('No video loaded', { sz: 11, color: C.textDim, x: 16, y: 32 }),
      mkLine(INSPECTOR_W, { x: 0, y: 56 }),
      mkText('🎬', { sz: 36, x: INSPECTOR_W / 2 - 18, y: 200 }),
      mkText('Open a video to start editing', { sz: 13, color: C.textMid, x: 50, y: 260, maxW: INSPECTOR_W - 100, align: 'CENTER' }),
      mkText('Trim, subtitles, presets, and render options will appear here once your video is loaded.', { sz: 11, color: C.textMut, x: 30, y: 290, maxW: INSPECTOR_W - 60 }),
    );
    append(f, insp);
    drawBottomCollapsed(f, { text: 'No active render · click to expand' });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 10 · Render · Editor Active (HERO SHOT)
     The defining screen — video loaded, full inspector, video preview.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('10 · Render · Editor Active', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042.mp4' });
    drawSidebar(f, {
      youtubeUrl: '',
      videoFile: 'D:\\downloads\\podcast_ep_042.mp4',
      sourceMode: 'local',
      outputDir: 'D:\\videos\\output\\creator_x',
      outputSet: true,
    });
    drawStatusBar(f);
    drawBottomCollapsed(f, { text: 'No active render · click to expand' });

    // Center: Video preview + toolbar
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Top breadcrumb / stepper
    append(stage,
      mkStepper(['Source', 'Plan', 'Editor', 'Render', 'Review'], 2, {
        x: 24, y: 16, w: stageW - 48,
      }),
    );

    // Preview area
    const pvX = 32; const pvY = 70;
    const pvW = stageW - 64;
    const pvH = stageH - 230;
    const preview = mkFrame('VideoPreview', pvW, pvH, { fill: C.bg950, x: pvX, y: pvY, cr: R.lg });
    preview.strokes = solid(C.border); preview.strokeWeight = 1;

    // Faux video frame
    append(preview, mkRect(pvW, pvH, C.bg700, { x: 0, y: 0, op: 0.4 }));
    // Vignette
    append(preview, mkRect(pvW, pvH * 0.4, C.bg950, { x: 0, y: 0, op: 0.6 }));
    append(preview, mkRect(pvW, pvH * 0.3, C.bg950, { x: 0, y: pvH * 0.7, op: 0.5 }));

    // Crop guide overlay (3:4 vertical mask)
    const cropW = pvH * 0.75;
    const cropX = (pvW - cropW) / 2;
    append(preview,
      mkRect(cropX, pvH, C.bg950, { x: 0, y: 0, op: 0.55 }),
      mkRect(pvW - cropX - cropW, pvH, C.bg950, { x: cropX + cropW, y: 0, op: 0.55 }),
      mkRect(cropW, pvH, null, { x: cropX, y: 0, stroke: C.primary, sw: 1.5, dashed: true }),
    );
    // 3:4 label
    const cropLabel = mkFrame('cropLabel', 64, 20, { fill: C.primary, x: cropX + 8, y: 8, cr: R.xs });
    append(cropLabel, mkText('3:4 · 1080×1440', { sz: 9, bold: true, color: C.white, x: 6, y: 4, mono: true }));
    append(preview, cropLabel);

    // Title overlay sample (animated text)
    const overlay = mkFrame('titleOverlay', cropW * 0.85, 50, { fill: null, x: cropX + cropW * 0.075, y: pvH * 0.18 });
    overlay.fills = [];
    append(overlay, mkText('THE ONE INSIGHT', {
      sz: 18, bold: true, color: C.white, x: 0, y: 0,
    }));
    append(overlay, mkText('that changed how I work', {
      sz: 13, color: C.primaryHi, x: 0, y: 22,
    }));
    append(preview, overlay);

    // Speaker silhouette (faux)
    const speakerY = pvH * 0.55;
    append(preview,
      mkRect(120, 120, C.bg700, { cr: R.pill, x: cropX + cropW / 2 - 60, y: speakerY }),
      mkRect(180, 80, C.bg700, { x: cropX + cropW / 2 - 90, y: speakerY + 80, cr: R.lg }),
    );

    // Subtitle preview
    const subY = pvH - 90;
    const subBg = mkFrame('subPreview', cropW * 0.9, 42, { fill: C.bg950, x: cropX + cropW * 0.05, y: subY, cr: R.sm });
    subBg.fills = solid(C.bg950, 0.75);
    append(subBg, mkText('And the moment I realized that...', {
      sz: 14, bold: true, color: C.white, x: 16, y: 12, align: 'LEFT',
    }));
    append(preview, subBg);

    // Floating toolbar (bottom of preview)
    const tbY = pvH - 44;
    const tb = mkFrame('previewToolbar', pvW - 24, 32, { fill: C.bg700, x: 12, y: tbY, cr: R.md });
    tb.fills = solid(C.bg700, 0.92);
    tb.strokes = solid(C.borderHi); tb.strokeWeight = 1;
    append(tb,
      mkIconBtn({ size: 28, x: 4, y: 2, variant: 'ghost', glyph: 'play' }),
      mkText('00:12.450', { sz: 11, color: C.text, x: 38, y: 8, mono: true }),
      mkText('/  34:08', { sz: 11, color: C.textMut, x: 100, y: 8, mono: true }),
    );
    // Scrub track
    const [st, sf] = mkProgress(pvW - 380, 18, { x: 152, y: 14, h: 4, color: C.primary });
    append(tb, st, sf);
    // Right cluster
    const trX = pvW - 220;
    append(tb,
      mkIconBtn({ size: 28, x: trX, y: 2, variant: 'ghost', glyph: 'down' }),
      mkText('1.0×', { sz: 11, bold: true, color: C.textMid, x: trX + 32, y: 8, mono: true }),
      mkIconBtn({ size: 28, x: trX + 60, y: 2, variant: 'ghost', glyph: 'up' }),
      mkIconBtn({ size: 28, x: trX + 100, y: 2, variant: 'ghost', glyph: 'play' }),
      mkIconBtn({ size: 28, x: trX + 132, y: 2, variant: 'active', glyph: 'play' }),
      mkText('Fit', { sz: 11, color: C.textMid, x: trX + 166, y: 8 }),
    );
    append(preview, tb);
    append(stage, preview);

    // Mini-timeline strip below preview
    const tlY = pvY + pvH + 12;
    const tl = mkFrame('miniTimeline', pvW, 88, { fill: C.bg850, x: pvX, y: tlY, cr: R.lg });
    tl.strokes = solid(C.border); tl.strokeWeight = 1;
    append(tl,
      mkText('TIMELINE', { sz: 10, bold: true, color: C.textMut, x: 12, y: 10 }),
      mkText('5 clips · 4 min 24 sec total selection', { sz: 11, color: C.textDim, x: 80, y: 10 }),
      mkBtn('Auto-detect Highlights', { variant: 'accentSec', size: 'sm', x: pvW - 200, y: 6 }),
    );
    // Clip blocks on timeline
    const clipWidths = [180, 140, 220, 100, 160];
    const clipColors = [C.primary, C.secondary, C.primary, C.warn, C.primary];
    let tx = 12;
    clipWidths.forEach((w, i) => {
      const clip = mkRect(w - 4, 40, clipColors[i], { cr: R.sm, x: tx, y: 36, op: 0.35 });
      const clipBdr = mkRect(w - 4, 40, null, { x: tx, y: 36, stroke: clipColors[i], sw: 1, cr: R.sm });
      append(tl, clip, clipBdr,
        mkText('clip ' + (i + 1), { sz: 9, bold: true, color: C.white, x: tx + 6, y: 50, mono: true }),
      );
      tx += w;
    });
    append(stage, tl);
    append(f, stage);

    // Right inspector — Cut tab active
    drawInspector(f, { activeTab: 0, videoTitle: 'podcast_ep_042.mp4', videoMeta: '1h 24m · 1080p · 60fps' });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 11 · Inspector · Cut tab (detail focus)
     Zoom into the inspector — shows trim, presets, output options.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('11 · Inspector · Cut tab', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042.mp4' });
    drawSidebar(f, { collapsed: true });  // Show collapsed mode for variety
    drawStatusBar(f);
    drawBottomCollapsed(f, { text: 'No active render' });

    // Center: dim preview to focus attention on inspector
    const stageX = SIDEBAR_W_COLL;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W_COLL - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });
    // Faded preview (just an outline)
    const fpv = mkCard(stageW - 64, stageH - 64, { elevation: 'flat', x: 32, y: 32 });
    fpv.opacity = 0.4;
    append(fpv,
      mkText('Video Preview', { sz: 14, color: C.textDim, x: 32, y: 32 }),
      mkText('(faded — focus on inspector →)', { sz: 11, color: C.textDim, x: 32, y: 56 }),
    );
    append(stage, fpv);

    // Spotlight callout pointing to inspector
    append(stage,
      mkText('CUT TAB · INSPECTOR DETAIL', { sz: 11, bold: true, color: C.primaryHi, x: stageW - 280, y: 20 }),
      mkText('Compact trim controls + preset chips + output options.', {
        sz: 11, color: C.textMid, x: stageW - 280, y: 38, maxW: 260,
      }),
    );
    append(f, stage);

    // Detailed inspector — Cut tab fully drawn (already in default drawInspector)
    drawInspector(f, { activeTab: 0, videoTitle: 'podcast_ep_042.mp4', videoMeta: '1h 24m · 1080p · 60fps' });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 12 · Inspector · Subtitle tab
     Custom body — subtitle styling, font, position, karaoke.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('12 · Inspector · Subtitle tab', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042.mp4' });
    drawSidebar(f, { collapsed: true });
    drawStatusBar(f);
    drawBottomCollapsed(f, { text: 'No active render' });

    // Center: live subtitle preview (mini)
    const stageX = SIDEBAR_W_COLL;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W_COLL - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Sample preview with subtitle being styled
    const previewW = stageW - 200;
    const previewH = stageH - 200;
    const pv = mkFrame('SubtitlePreview', previewW, previewH, { fill: C.bg950, x: 100, y: 100, cr: R.lg });
    pv.strokes = solid(C.border); pv.strokeWeight = 1;
    // 3:4 mask
    const cropW = previewH * 0.75;
    const cropX = (previewW - cropW) / 2;
    append(pv,
      mkRect(cropX, previewH, C.bg950, { x: 0, y: 0, op: 0.5 }),
      mkRect(previewW - cropX - cropW, previewH, C.bg950, { x: cropX + cropW, y: 0, op: 0.5 }),
      mkRect(cropW, previewH, C.bg700, { x: cropX, y: 0, op: 0.3, cr: R.sm }),
    );

    // Karaoke-style subtitle in center
    const subY = previewH * 0.7;
    const w1 = 100, w2 = 120, w3 = 90, w4 = 70;
    const totalSubW = w1 + w2 + w3 + w4 + 48;
    let sx = cropX + (cropW - totalSubW) / 2;
    const words = [
      ['And', w1, C.white],
      ['THE', w2, C.warn],       // highlighted
      ['moment', w3, C.white],
      ['I…', w4, C.white],
    ];
    words.forEach(([word, ww, col], i) => {
      const wBg = mkFrame('word', ww, 32, { fill: col === C.warn ? C.warn : null, x: sx, y: subY, cr: R.sm });
      if (col === C.warn) {
        wBg.fills = solid(C.warn, 0.25);
        wBg.strokes = solid(C.warn); wBg.strokeWeight = 1;
      } else {
        wBg.fills = [];
      }
      append(wBg, mkText(word, {
        sz: 18, bold: true, color: col === C.warn ? C.warn : C.white,
        x: 8, y: 6,
      }));
      append(pv, wBg);
      sx += ww + 12;
    });

    // Label
    append(stage,
      mkText('LIVE SUBTITLE PREVIEW', { sz: 11, bold: true, color: C.primaryHi, x: 100, y: 64, mono: true }),
      mkText('Karaoke style · Bold · Warn-yellow highlight on active word', { sz: 11, color: C.textMut, x: 100, y: 80 }),
    );
    append(stage, pv);
    append(f, stage);

    // Inspector — Subtitle tab body
    const bodyDraw = (insp, insW, startY) => {
      let cy = startY + 8;
      // Style section
      append(insp, mkSectionHead('Style', { x: 16, y: cy, w: insW - 32 }));
      cy += 26;
      append(insp,
        mkSelect('Font', 'Inter Display · Bold', { x: 16, y: cy, w: insW - 32 }),
      );
      cy += 70;
      append(insp,
        mkInput('Size', '38px', { x: 16, y: cy, w: (insW - 40) / 2 }),
        mkInput('Stroke', '3px', { x: 16 + (insW - 40) / 2 + 8, y: cy, w: (insW - 40) / 2 }),
      );
      cy += 70;
      // Color row
      append(insp, mkText('Colors', { sz: 11, bold: true, color: C.textMut, x: 16, y: cy }));
      cy += 18;
      const colors = [C.white, C.warn, C.primary, C.secondary, C.success, C.danger];
      colors.forEach((col, i) => {
        const sel = i === 0;
        const sw = mkFrame('color/' + i, 36, 36, { fill: col, x: 16 + i * 44, y: cy, cr: R.sm });
        if (sel) { sw.strokes = solid(C.text); sw.strokeWeight = 2; }
        append(insp, sw);
      });
      cy += 50;

      // Karaoke
      append(insp, mkSectionHead('Karaoke', { x: 16, y: cy, w: insW - 32, accent: C.secondary }));
      cy += 26;
      append(insp,
        mkText('Word-by-word highlight', { sz: 12, color: C.text, medium: true, x: 16, y: cy }),
        mkText('Animate active word color', { sz: 11, color: C.textMut, x: 16, y: cy + 18 }),
        mkToggle(true, { x: insW - 50, y: cy + 4 }),
      );
      cy += 44;
      append(insp,
        mkText('Pop-in animation', { sz: 12, color: C.text, medium: true, x: 16, y: cy }),
        mkText('Scale on word start', { sz: 11, color: C.textMut, x: 16, y: cy + 18 }),
        mkToggle(true, { x: insW - 50, y: cy + 4 }),
      );
      cy += 44;

      // Position
      append(insp, mkSectionHead('Position', { x: 16, y: cy, w: insW - 32 }));
      cy += 26;
      const positions = ['Top', 'Center', 'Lower 1/3', 'Bottom'];
      positions.forEach((p, i) => {
        const col = i % 2; const row = Math.floor(i / 2);
        const isSel = i === 2;
        const px = 16 + col * ((insW - 40) / 2 + 8);
        const py = cy + row * 40;
        const pBtn = mkCard((insW - 40) / 2, 32, {
          elevation: isSel ? 'interactive' : 'flat',
          x: px, y: py, name: 'pos/' + p,
        });
        append(pBtn, mkText(p, {
          sz: 12, bold: isSel, color: isSel ? C.primaryHi : C.text,
          x: 10, y: 8,
        }));
        append(insp, pBtn);
      });
      cy += 86;

      // Background
      append(insp, mkSectionHead('Background', { x: 16, y: cy, w: insW - 32, accent: C.secondary }));
      cy += 26;
      append(insp,
        mkSelect('Box style', 'Rounded · semi-dark', { x: 16, y: cy, w: insW - 32 }),
      );
      cy += 70;
      append(insp,
        mkInput('Opacity', '0.75', { x: 16, y: cy, w: (insW - 40) / 2 }),
        mkInput('Padding', '12px',  { x: 16 + (insW - 40) / 2 + 8, y: cy, w: (insW - 40) / 2 }),
      );
    };
    drawInspector(f, {
      activeTab: 1,
      videoTitle: 'podcast_ep_042.mp4',
      videoMeta: '1h 24m · 1080p · 60fps',
      bodyDraw,
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 13 · Inspector · Render tab
     Output options · format · device · post-actions
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('13 · Inspector · Render tab', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042.mp4' });
    drawSidebar(f, { collapsed: true });
    drawStatusBar(f);
    drawBottomCollapsed(f, { text: 'No active render' });

    // Center: summary card preview
    const stageX = SIDEBAR_W_COLL;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W_COLL - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Render summary preview
    append(stage,
      mkText('RENDER SUMMARY', { sz: 11, bold: true, color: C.primaryHi, x: 32, y: 24, mono: true }),
      mkText('Review your settings before kicking off the job.', { sz: 11, color: C.textMut, x: 32, y: 40 }),
    );
    const summary = mkCard(stageW - 64, stageH - 96, { elevation: 'elevated', x: 32, y: 72 });

    // Two-column summary
    const col1 = [
      ['Source',       'podcast_ep_042.mp4'],
      ['Duration',     '1h 24m 12s'],
      ['Selection',    '5 clips · 4m 24s'],
      ['Output Folder', 'D:\\videos\\output\\creator_x'],
    ];
    const col2 = [
      ['Aspect',   '3:4 Vertical (1080×1440)'],
      ['FPS',      '60'],
      ['Profile',  'Balanced · h264 NVENC'],
      ['Device',   'GPU · RTX 4070'],
    ];
    let cy = 32;
    append(summary, mkSectionHead('Job', { x: 32, y: cy, w: 400 }));
    cy += 28;
    col1.forEach((row, i) => {
      append(summary,
        mkText(row[0].toUpperCase(), { sz: 10, bold: true, color: C.textMut, x: 32, y: cy + i * 38, mono: true }),
        mkText(row[1], { sz: 13, color: C.text, x: 32, y: cy + i * 38 + 14 }),
      );
    });

    append(summary, mkSectionHead('Output spec', { x: 480, y: 32, w: 400, accent: C.secondary }));
    col2.forEach((row, i) => {
      append(summary,
        mkText(row[0].toUpperCase(), { sz: 10, bold: true, color: C.textMut, x: 480, y: 60 + i * 38, mono: true }),
        mkText(row[1], { sz: 13, color: C.text, x: 480, y: 60 + i * 38 + 14 }),
      );
    });

    // Post-render
    cy = 240;
    append(summary, mkSectionHead('Post-render actions', { x: 32, y: cy, w: stageW - 128 }));
    cy += 28;
    const postActions = [
      ['Open output folder', true],
      ['Show clip gallery',  true],
      ['Cleanup temp files', true],
      ['Email me when done', false],
    ];
    postActions.forEach((p, i) => {
      const col = i % 2;
      const px = 32 + col * 440;
      const py = cy + Math.floor(i / 2) * 44;
      append(summary,
        mkText(p[0], { sz: 12, color: C.text, medium: true, x: px, y: py + 4 }),
        mkToggle(p[1], { x: px + 200, y: py }),
      );
    });
    append(stage, summary);
    append(f, stage);

    // Inspector — Render tab body
    const bodyDraw = (insp, insW, startY) => {
      let cy = startY + 8;
      append(insp, mkSectionHead('Output', { x: 16, y: cy, w: insW - 32 }));
      cy += 26;
      append(insp,
        mkSelect('Aspect Ratio', '3:4 Vertical', { x: 16, y: cy, w: insW - 32 }),
      );
      cy += 70;
      append(insp,
        mkSelect('Resolution', '1080×1440', { x: 16, y: cy, w: (insW - 40) / 2 }),
        mkSelect('FPS', '60', { x: 16 + (insW - 40) / 2 + 8, y: cy, w: (insW - 40) / 2 }),
      );
      cy += 70;

      // Encoder section
      append(insp, mkSectionHead('Encoder', { x: 16, y: cy, w: insW - 32, accent: C.secondary }));
      cy += 26;
      append(insp,
        mkSelect('Codec', 'h264 · NVENC', { x: 16, y: cy, w: insW - 32 }),
      );
      cy += 70;
      append(insp,
        mkSelect('Profile', 'Balanced', { x: 16, y: cy, w: (insW - 40) / 2 }),
        mkSelect('Bitrate', '12 Mbps', { x: 16 + (insW - 40) / 2 + 8, y: cy, w: (insW - 40) / 2 }),
      );
      cy += 70;

      // Device
      append(insp, mkSectionHead('Device', { x: 16, y: cy, w: insW - 32 }));
      cy += 26;
      const devices = [['Auto', true], ['GPU', false], ['CPU', false]];
      devices.forEach((d, i) => {
        const dw = (insW - 40) / 3;
        const dx = 16 + i * (dw + 4);
        const dBtn = mkCard(dw - 4, 36, {
          elevation: d[1] ? 'interactive' : 'flat',
          x: dx, y: cy, name: 'dev/' + d[0],
        });
        append(dBtn, mkText(d[0], {
          sz: 12, bold: d[1], color: d[1] ? C.primaryHi : C.text,
          x: (dw - 4 - estW(d[0], 12)) / 2, y: 10,
        }));
        append(insp, dBtn);
      });
      cy += 56;

      // Toggles
      append(insp,
        mkText('Cleanup temp', { sz: 12, color: C.text, medium: true, x: 16, y: cy }),
        mkText('Free disk after success', { sz: 11, color: C.textMut, x: 16, y: cy + 18 }),
        mkToggle(true, { x: insW - 50, y: cy + 4 }),
      );
      cy += 44;
      append(insp,
        mkText('Open folder', { sz: 12, color: C.text, medium: true, x: 16, y: cy }),
        mkText('Show in Explorer when done', { sz: 11, color: C.textMut, x: 16, y: cy + 18 }),
        mkToggle(true, { x: insW - 50, y: cy + 4 }),
      );
      cy += 44;
      append(insp,
        mkText('Verbose logs', { sz: 12, color: C.text, medium: true, x: 16, y: cy }),
        mkText('FFmpeg + Whisper full output', { sz: 11, color: C.textMut, x: 16, y: cy + 18 }),
        mkToggle(false, { x: insW - 50, y: cy + 4 }),
      );
    };
    drawInspector(f, {
      activeTab: 4,
      videoTitle: 'podcast_ep_042.mp4',
      videoMeta: '1h 24m · 1080p · 60fps',
      bodyDraw,
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 14 · Monitor · Active (Expanded)
     Full bottom panel during active render — queue + logs.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('14 · Monitor · Active (Expanded)', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042.mp4', chip: 'Rendering · Part 3/5' });
    drawSidebar(f, { collapsed: true });
    drawStatusBar(f, {
      mem: '8.4 / 16 GB',
      gpu: 'CUDA · RTX 4070 · 78%',
      ffmpeg: 'FFmpeg 7.1 · NVENC',
    });

    // Center: shrunken preview (because monitor takes 320px)
    const stageX = SIDEBAR_W_COLL;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W_COLL - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_FULL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Preview shrinks but stays visible
    const pv = mkCard(stageW - 64, stageH - 64, { elevation: 'flat', x: 32, y: 32 });
    append(pv,
      mkRect(stageW - 64, stageH - 64, C.bg700, { x: 0, y: 0, op: 0.3, cr: R.lg }),
      mkText('Preview · Rendering preview disabled', { sz: 13, bold: true, color: C.textMut, x: 24, y: 20 }),
      mkText('Click "Resume Preview" to enable.', { sz: 11, color: C.textDim, x: 24, y: 42 }),
    );
    // Live render thumbnail (faux)
    const thumbW = 280; const thumbH = 200;
    const thumb = mkCard(thumbW, thumbH, { elevation: 'elevated', x: (stageW - thumbW) / 2, y: (stageH - thumbH) / 2 - 20 });
    append(thumb,
      mkRect(thumbW, thumbH, C.bg950, { x: 0, y: 0, cr: R.lg }),
      mkRect(thumbW, thumbH * 0.5, C.primary, { x: 0, y: thumbH * 0.5, op: 0.1 }),
      mkText('FRAME 4,847 / 7,234', { sz: 11, bold: true, color: C.primaryHi, x: 16, y: 16, mono: true }),
      mkText('Part 3 · Rendering', { sz: 11, color: C.textMid, x: 16, y: 34 }),
      mkText('1080×1440 · 60 fps', { sz: 10, color: C.textDim, x: 16, y: thumbH - 24, mono: true }),
      mkPill('LIVE', { bg: C.danger, textColor: C.white, x: thumbW - 56, y: 16, sz: 10 }),
    );
    append(pv, thumb);
    append(stage, pv);
    append(f, stage);

    // Inspector — read-only during render
    const bodyDraw = (insp, insW, startY) => {
      let cy = startY + 8;
      append(insp,
        mkPill('LOCKED · render in progress', {
          bg: C.bg700, textColor: C.warn, stroke: C.warn, sw: 1,
          x: 16, y: cy, h: 22, sz: 10,
        }),
      );
      cy += 36;
      append(insp, mkSectionHead('Active Job', { x: 16, y: cy, w: insW - 32 }));
      cy += 28;
      const facts = [
        ['Started',  '08:42:12'],
        ['Elapsed',  '04:18'],
        ['ETA',      '~ 06:24'],
        ['Encoder',  'h264 NVENC'],
        ['Output',   '1080×1440 · 60 fps'],
        ['Profile',  'Balanced'],
      ];
      facts.forEach((row, i) => {
        append(insp,
          mkText(row[0].toUpperCase(), { sz: 10, bold: true, color: C.textMut, x: 16, y: cy + i * 36, mono: true }),
          mkText(row[1], { sz: 12, color: C.text, x: 16, y: cy + i * 36 + 14, mono: true }),
        );
      });
      cy += facts.length * 36 + 12;
      append(insp, mkSectionHead('Live Counters', { x: 16, y: cy, w: insW - 32, accent: C.secondary }));
      cy += 28;
      const counters = [
        ['Frames',    '4,847 / 7,234'],
        ['FPS',       '142.6'],
        ['Bitrate',   '11.8 Mbps'],
        ['Size so far', '38.4 MB'],
      ];
      counters.forEach((row, i) => {
        append(insp,
          mkText(row[0], { sz: 11, color: C.textMid, x: 16, y: cy + i * 28 }),
          mkText(row[1], { sz: 11, bold: true, color: C.primaryHi, x: insW - 130, y: cy + i * 28, mono: true }),
        );
      });
    };
    // Override footer for monitor mode
    drawInspector(f, {
      activeTab: 4,
      videoTitle: 'podcast_ep_042.mp4',
      videoMeta: '1h 24m · 1080p · 60fps',
      bodyDraw,
    });

    drawBottomExpanded(f, {
      pct: 67, stage: 'rendering',
      jobTitle: 'Render — podcast_ep_042 · job_abc123',
      partLabel: 'Part 3 — Rendering 67% · 142.6 fps',
      partsCount: '3 / 5 done',
      sourceFile: 'podcast_ep_042.mp4',
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 15 · Monitor · Collapsed / Idle
     Bottom panel minimized to 56px toolbar.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('15 · Monitor · Collapsed / Idle', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawSidebar(f);
    drawStatusBar(f);

    // Center: idle state with last job summary
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Hero: last job done
    append(stage,
      mkPill('✓ Last job completed', {
        bg: C.bg750, textColor: C.success, stroke: C.success, sw: 1,
        x: 32, y: 32, h: 26, sz: 11,
      }),
      mkText('podcast_ep_042 · 5 clips ready', { sz: 22, bold: true, color: C.text, x: 32, y: 76 }),
      mkText('Average score 8.4 · 4 min 24 sec total · 184 MB', { sz: 13, color: C.textMid, x: 32, y: 110, mono: true }),
    );

    // KPI strip
    const metrics = [
      ['Clips',      '5',     C.primaryHi],
      ['Best score', '9.2',   C.success],
      ['Total time', '12:18', C.text],
      ['Saved to',   'D:\\…\\creator_x', C.textMut],
    ];
    metrics.forEach((m, i) => {
      append(stage, mkMetric(m[0], m[1], {
        x: 32 + i * 200, y: 156, w: 184, h: 80, color: m[2],
      }));
    });

    // Action row
    append(stage,
      mkBtn('Open Clip Gallery', { variant: 'primary', size: 'lg', x: 32, y: 260, w: 200 }),
      mkBtn('Show in Explorer', { variant: 'secondary', size: 'lg', x: 244, y: 260, w: 180 }),
      mkBtn('Render Again', { variant: 'ghost', size: 'lg', x: 436, y: 260, w: 140 }),
    );

    // Below: recent jobs strip (mini)
    append(stage,
      mkLine(stageW - 64, { x: 32, y: 340 }),
      mkSectionHead('Recent jobs', { x: 32, y: 360, w: stageW - 64 }),
    );
    const recent = [
      ['podcast_ep_042',    '5 clips', '8.4', '12 min ago',  C.success],
      ['interview_anna',    '3 clips', '7.2', '2 hr ago',    C.success],
      ['conference_keynote', 'Failed', '—',   '4 hr ago',    C.danger],
      ['short_test',        '1 clip',  '6.1', 'Yesterday',   C.textMid],
    ];
    recent.forEach((r, i) => {
      const ry = 396 + i * 56;
      const row = mkCard(stageW - 64, 48, { elevation: 'flat', x: 32, y: ry });
      append(row,
        mkRect(3, 28, r[4], { cr: 1, x: 0, y: 10 }),
        mkText(r[0], { sz: 12, bold: true, color: C.text, x: 16, y: 8, mono: true }),
        mkText(r[1], { sz: 11, color: C.textMid, x: 16, y: 26 }),
        mkText('Score', { sz: 10, color: C.textMut, x: 280, y: 8, mono: true }),
        mkText(r[2], { sz: 13, bold: true, color: r[4], x: 280, y: 22, mono: true }),
        mkText(r[3], { sz: 11, color: C.textMut, x: stageW - 240, y: 16 }),
        mkBtn('Open', { variant: 'ghost', size: 'sm', x: stageW - 144, y: 12 }),
      );
      append(stage, row);
    });
    append(f, stage);

    // Inspector — idle state
    const insp = mkFrame('Inspector', INSPECTOR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: FW - INSPECTOR_W, y: TOPBAR_H,
    });
    insp.strokes = solid(C.border); insp.strokeWeight = 1;
    append(insp,
      mkText('Inspector', { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
      mkText('No active editor session', { sz: 11, color: C.textDim, x: 16, y: 32 }),
      mkLine(INSPECTOR_W, { x: 0, y: 56 }),
      mkText('Pick a recent job, or start a new render with the Setup panel on the left.', {
        sz: 12, color: C.textMid, x: 24, y: 240, maxW: INSPECTOR_W - 48,
      }),
    );
    append(f, insp);

    // Collapsed bottom panel (showing toolbar only)
    drawBottomCollapsed(f, { text: 'Idle · last job done at 08:54' });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 16 · Output · Clip Gallery
     Post-render review — all clips with scores, preview, actions.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('16 · Output · Clip Gallery', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { subtitle: 'creator_x · podcast_ep_042 · review' });
    drawSidebar(f, { collapsed: true });
    drawStatusBar(f);
    drawBottomCollapsed(f, { text: 'Render complete · 5 clips ready', state: 'active' });

    const stageX = SIDEBAR_W_COLL;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W_COLL - INSPECTOR_W;
    const stageH = FH - TOPBAR_H - STATUS_H - BOTTOM_COLL;
    const stage = mkFrame('CenterStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Header
    append(stage,
      mkText('Clip Gallery', { sz: 22, bold: true, color: C.text, x: 32, y: 24 }),
      mkText('5 clips · sorted by AI score · podcast_ep_042', { sz: 12, color: C.textMut, x: 32, y: 54 }),
    );

    // Filters
    append(stage,
      mkPill('All · 5', { bg: C.primaryGl, textColor: C.primaryHi, stroke: C.primary, sw: 1, x: 32, y: 84, h: 28, sz: 11 }),
      mkPill('★ Top picks · 2', { bg: C.bg750, textColor: C.textMid, stroke: C.border, sw: 1, x: 130, y: 84, h: 28, sz: 11 }),
      mkPill('9:16 · 4', { bg: C.bg750, textColor: C.textMid, stroke: C.border, sw: 1, x: 260, y: 84, h: 28, sz: 11 }),
      mkPill('1:1 · 1', { bg: C.bg750, textColor: C.textMid, stroke: C.border, sw: 1, x: 348, y: 84, h: 28, sz: 11 }),
      mkBtn('Download All', { variant: 'primary', size: 'sm', x: stageW - 280, y: 80 }),
      mkBtn('Open Folder', { variant: 'secondary', size: 'sm', x: stageW - 148, y: 80 }),
    );

    // Clip grid
    const clips = [
      { rank: 1, score: 9.2, dur: 84,  aspect: '9:16', title: 'Hook · "the one insight"', status: 'done' },
      { rank: 2, score: 8.4, dur: 96,  aspect: '9:16', title: 'Insight 2 · proof points', status: 'done' },
      { rank: 3, score: 7.1, dur: 64,  aspect: '1:1',  title: 'Quote moment',             status: 'done' },
      { rank: 4, score: 6.8, dur: 120, aspect: '9:16', title: 'Setup beat',               status: 'done' },
      { rank: 5, score: 5.4, dur: 48,  aspect: '9:16', title: 'B-roll · short',           status: 'done' },
    ];
    const gridY = 132;
    clips.forEach((cl, i) => {
      append(stage, mkClipCardV2(cl.rank, {
        x: 32 + i * 212, y: gridY,
        score: cl.score, durationSec: cl.dur, aspect: cl.aspect,
        title: cl.title, status: cl.status,
      }));
    });

    // Summary card (bottom area)
    const sumY = gridY + 380 + 16;
    const sum = mkCard(stageW - 64, stageH - sumY - 32, { elevation: 'flat', x: 32, y: sumY });
    append(sum,
      mkText('Job Summary', { sz: 13, bold: true, color: C.text, x: 20, y: 18 }),
      mkText('Average score 8.4 · 5 clips · 4m 24s total · 184 MB', { sz: 11, color: C.textMid, x: 20, y: 38, mono: true }),
    );
    // Mini bars showing score distribution
    const distX = 360;
    const distLabels = ['1·9.2', '2·8.4', '3·7.1', '4·6.8', '5·5.4'];
    const distValues = [9.2, 8.4, 7.1, 6.8, 5.4];
    distValues.forEach((v, i) => {
      const bx = distX + i * 48;
      const bh = v * 6;
      const col = v >= 8 ? C.success : v >= 6 ? C.warn : C.danger;
      append(sum,
        mkRect(28, bh, col, { cr: R.xs, x: bx, y: 56 - bh, op: 0.7 }),
        mkText(distLabels[i], { sz: 9, color: C.textMut, x: bx - 4, y: 60, mono: true }),
      );
    });
    append(sum,
      mkBtn('Export Report (PDF)', { variant: 'ghost', size: 'sm', x: stageW - 240, y: 16 }),
      mkBtn('Re-rank with AI', { variant: 'accentSec', size: 'sm', x: stageW - 240, y: 50 }),
    );
    append(stage, sum);
    append(f, stage);

    // Inspector — selected clip detail
    const bodyDraw = (insp, insW, startY) => {
      let cy = startY + 8;
      append(insp,
        mkPill('SELECTED CLIP', { bg: C.primaryGl, textColor: C.primaryHi, stroke: C.primary, sw: 1, x: 16, y: cy, h: 22, sz: 10 }),
      );
      cy += 36;
      // Mini preview
      const mp = mkCard(insW - 32, 200, { elevation: 'elevated', x: 16, y: cy });
      append(mp,
        mkRect(insW - 32, 200, C.bg950, { x: 0, y: 0, cr: R.lg }),
        mkText('#1', { sz: 28, bold: true, color: C.primaryHi, x: 16, y: 16, mono: true }),
        mkText('1:24', { sz: 11, bold: true, color: C.white, x: insW - 64, y: 168, mono: true }),
      );
      append(insp, mp);
      cy += 216;
      append(insp,
        mkText('Hook · "the one insight"', { sz: 14, bold: true, color: C.text, x: 16, y: cy, maxW: insW - 32 }),
        mkPill('★ 9.2', { bg: C.success, textColor: C.bg950, x: 16, y: cy + 30, sz: 11 }),
        mkPill('9:16', { bg: C.bg700, textColor: C.textMid, x: 70, y: cy + 30, sz: 11 }),
        mkPill('done', { bg: C.success, textColor: C.bg950, x: 120, y: cy + 30, sz: 11 }),
      );
      cy += 76;
      append(insp, mkSectionHead('AI Insights', { x: 16, y: cy, w: insW - 32, accent: C.secondary }));
      cy += 28;
      const insights = [
        ['Hook strength', 'Excellent · "What changed everything"'],
        ['Pacing', '142 wpm · optimal range'],
        ['Visual interest', 'Speaker close-up · high'],
        ['Emotion arc', '↗ rising → peak at 0:48'],
      ];
      insights.forEach((ins, i) => {
        append(insp,
          mkText(ins[0].toUpperCase(), { sz: 10, bold: true, color: C.textMut, x: 16, y: cy + i * 38, mono: true }),
          mkText(ins[1], { sz: 11, color: C.text, x: 16, y: cy + i * 38 + 14, maxW: insW - 32 }),
        );
      });
    };
    // Override footer for output view
    const insp = mkFrame('Inspector', INSPECTOR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: FW - INSPECTOR_W, y: TOPBAR_H,
    });
    insp.strokes = solid(C.border); insp.strokeWeight = 1;
    append(insp,
      mkText('Clip Detail', { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
      mkText('podcast_ep_042 · clip 1', { sz: 11, color: C.textMid, x: 16, y: 32 }),
      mkLine(INSPECTOR_W, { x: 0, y: 56 }),
    );
    bodyDraw(insp, INSPECTOR_W, 60);

    const fy = FH - TOPBAR_H - STATUS_H - 76;
    append(insp,
      mkLine(INSPECTOR_W, { x: 0, y: fy }),
      mkBtn('Download Clip', { variant: 'primary', size: 'lg', x: 16, y: fy + 16, w: INSPECTOR_W - 32, h: 44 }),
    );
    append(f, insp);

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     FRAME 17 · Download Manager
     Source inbox — paste links, see download progress.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('17 · Download Manager', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { activeTab: 'download', subtitle: 'Source inbox' });
    drawStatusBar(f);

    // For Download view: simpler 2-pane layout (no inspector)
    const sb = mkFrame('DownloadSidebar', SIDEBAR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: 0, y: TOPBAR_H,
    });
    sb.strokes = solid(C.border); sb.strokeWeight = 1;
    append(sb,
      mkText('Download Inbox', { sz: 13, bold: true, color: C.text, x: 16, y: 16 }),
      mkText('Add links to fetch sources', { sz: 11, color: C.textMut, x: 16, y: 36 }),
      mkLine(SIDEBAR_W, { x: 0, y: 64 }),
      mkSectionHead('1 · Paste Links', { x: 16, y: 80, w: SIDEBAR_W - 32 }),
    );
    // Big textarea
    const ta = mkCard(SIDEBAR_W - 32, 140, { elevation: 'flat', x: 16, y: 112 });
    append(ta,
      mkText('https://www.youtube.com/watch?v=...', { sz: 11, color: C.text, x: 12, y: 12, mono: true }),
      mkText('https://www.tiktok.com/@...', { sz: 11, color: C.text, x: 12, y: 32, mono: true }),
      mkText('https://www.facebook.com/reel/...', { sz: 11, color: C.text, x: 12, y: 52, mono: true }),
      mkText('|', { sz: 12, color: C.primary, x: 12, y: 72 }),
    );
    append(sb, ta);
    append(sb,
      mkSelect('Quality', '1080p / Best', { x: 16, y: 268, w: SIDEBAR_W - 32 }),
      mkSelect('Save to', 'D:\\downloads', { x: 16, y: 332, w: SIDEBAR_W - 32 }),
    );
    // Action
    const fy = FH - TOPBAR_H - STATUS_H - 124;
    append(sb,
      mkLine(SIDEBAR_W, { x: 0, y: fy }),
      mkBtn('↓ Start Download', { variant: 'primary', size: 'lg', x: 16, y: fy + 16, w: SIDEBAR_W - 32, h: 44 }),
      mkText('3 links queued · ~ 320 MB', { sz: 11, color: C.textMut, x: 16, y: fy + 72 }),
    );
    append(f, sb);

    // Main: download queue
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W;
    const stageH = FH - TOPBAR_H - STATUS_H;
    const stage = mkFrame('DownloadStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    append(stage,
      mkText('Download Queue', { sz: 22, bold: true, color: C.text, x: 32, y: 24 }),
      mkText('3 active · 2 completed · 1 failed today', { sz: 12, color: C.textMut, x: 32, y: 54 }),
      mkBtn('Pause All', { variant: 'ghost', size: 'sm', x: stageW - 280, y: 32 }),
      mkBtn('Clear Completed', { variant: 'secondary', size: 'sm', x: stageW - 184, y: 32 }),
    );

    // Tab bar for filter
    append(stage, mkTabBar(['All · 6', 'Active · 3', 'Completed · 2', 'Failed · 1'], 0, {
      x: 32, y: 90, w: 500, h: 36, style: 'pill',
    }));

    // Download rows
    const dls = [
      { url: 'youtube.com/watch?v=abc123', title: 'Podcast Episode 042 · Tech Talk', pct: 78, size: '420 MB / 540 MB', state: 'active', stage: 'Downloading', speed: '12.4 MB/s' },
      { url: 'tiktok.com/@creator/video/...', title: 'Short clip · viral hook', pct: 42, size: '8 MB / 19 MB', state: 'active', stage: 'Downloading', speed: '2.8 MB/s' },
      { url: 'facebook.com/reel/...', title: 'Reel · cooking tutorial', pct: 12, size: '4 MB / 32 MB', state: 'active', stage: 'Queued', speed: '0 MB/s' },
      { url: 'youtube.com/watch?v=xyz789', title: 'Interview with Anna · 90 min', pct: 100, size: '1.2 GB', state: 'done', stage: 'Complete', speed: '—' },
      { url: 'youtube.com/watch?v=def456', title: 'Conference Keynote · Day 2', pct: 100, size: '2.4 GB', state: 'done', stage: 'Complete', speed: '—' },
      { url: 'tiktok.com/@x/video/...', title: 'Short test', pct: 0, size: '—', state: 'failed', stage: 'Failed · 403', speed: '—' },
    ];
    dls.forEach((d, i) => {
      const ry = 144 + i * 78;
      const row = mkCard(stageW - 64, 70, { elevation: 'flat', x: 32, y: ry });
      const accent = d.state === 'done' ? C.success : d.state === 'failed' ? C.danger : C.primary;
      append(row, mkRect(3, 50, accent, { cr: 1, x: 0, y: 10 }));
      append(row,
        mkText(d.title, { sz: 13, bold: true, color: C.text, x: 16, y: 10, maxW: 360 }),
        mkText(d.url, { sz: 10, color: C.textMut, x: 16, y: 30, mono: true, maxW: 360 }),
        mkText(d.size + ' · ' + d.speed, { sz: 10, color: C.textDim, x: 16, y: 46, mono: true }),
      );
      // Progress
      const trackX = 420;
      const [t, fl] = mkProgress(280, d.pct, { x: trackX, y: 28, h: 6, color: accent });
      append(row, t, fl);
      append(row,
        mkText(d.pct + '%', { sz: 12, bold: true, color: accent, x: trackX + 290, y: 24, mono: true }),
        mkStatusPill(d.stage, d.state === 'done' ? 'success' : d.state === 'failed' ? 'danger' : 'active', {
          x: trackX, y: 42,
        }),
      );
      // Right actions
      if (d.state === 'done') {
        append(row,
          mkBtn('Use in Editor', { variant: 'primary', size: 'sm', x: stageW - 252, y: 20 }),
          mkBtn('Show', { variant: 'ghost', size: 'sm', x: stageW - 132, y: 20, w: 60 }),
          mkIconBtn({ size: 28, x: stageW - 60, y: 20, variant: 'ghost', glyph: 'close' }),
        );
      } else if (d.state === 'failed') {
        append(row,
          mkBtn('Retry', { variant: 'secondary', size: 'sm', x: stageW - 200, y: 20 }),
          mkIconBtn({ size: 28, x: stageW - 60, y: 20, variant: 'ghost', glyph: 'close' }),
        );
      } else {
        append(row,
          mkIconBtn({ size: 28, x: stageW - 140, y: 20, variant: 'ghost', glyph: 'pause' }),
          mkIconBtn({ size: 28, x: stageW - 100, y: 20, variant: 'ghost', glyph: 'close' }),
        );
      }
      append(stage, row);
    });
    append(f, stage);

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 18 · History View
     Past jobs list with deep filters.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('18 · History View', FW, FH, { fill: C.bg900 });
    drawTopbar(f, { activeTab: 'history', subtitle: 'Past render jobs' });
    drawStatusBar(f);

    // Left filter rail
    const sb = mkFrame('HistorySidebar', SIDEBAR_W, FH - TOPBAR_H - STATUS_H, {
      fill: C.bg800, x: 0, y: TOPBAR_H,
    });
    sb.strokes = solid(C.border); sb.strokeWeight = 1;
    append(sb,
      mkText('History', { sz: 13, bold: true, color: C.text, x: 16, y: 16 }),
      mkText('42 jobs · last 30 days', { sz: 11, color: C.textMut, x: 16, y: 36 }),
      mkLine(SIDEBAR_W, { x: 0, y: 64 }),
      mkInput('Search', '', {
        x: 16, y: 80, w: SIDEBAR_W - 32, placeholder: 'Search by name, URL, channel…',
      }),
      mkSectionHead('Filter by status', { x: 16, y: 158, w: SIDEBAR_W - 32 }),
    );
    const filters = [
      ['All',       '42', C.text,     true],
      ['Completed', '38', C.success,  false],
      ['Failed',    '3',  C.danger,   false],
      ['Cancelled', '1',  C.textMut,  false],
    ];
    filters.forEach((fl, i) => {
      const fy = 188 + i * 38;
      const isSel = fl[3];
      const row = mkFrame('filter/' + fl[0], SIDEBAR_W - 32, 32, {
        fill: isSel ? C.bg700 : null, x: 16, y: fy, cr: R.sm,
      });
      if (!isSel) row.fills = [];
      if (isSel) { row.strokes = solid(C.primary, 0.3); row.strokeWeight = 1; }
      append(row,
        mkText(fl[0], { sz: 12, bold: isSel, color: isSel ? C.primaryHi : C.textMid, x: 12, y: 8 }),
        mkText(fl[1], { sz: 11, color: C.textMut, x: SIDEBAR_W - 60, y: 9, mono: true }),
      );
      append(sb, row);
    });
    append(sb,
      mkSectionHead('Filter by channel', { x: 16, y: 352, w: SIDEBAR_W - 32, accent: C.secondary }),
    );
    const channels = ['creator_x · 24', 'tech_anna · 12', 'cookbook · 6'];
    channels.forEach((c, i) => {
      append(sb,
        mkDot(8, [C.primary, C.secondary, C.warn][i], { x: 18, y: 392 + i * 32 }),
        mkText(c, { sz: 12, color: C.textMid, x: 36, y: 388 + i * 32 }),
      );
    });
    append(f, sb);

    // Main: jobs list
    const stageX = SIDEBAR_W;
    const stageY = TOPBAR_H;
    const stageW = FW - SIDEBAR_W;
    const stageH = FH - TOPBAR_H - STATUS_H;
    const stage = mkFrame('HistoryStage', stageW, stageH, { fill: C.bg900, x: stageX, y: stageY });

    // Header
    append(stage,
      mkText('All jobs', { sz: 22, bold: true, color: C.text, x: 32, y: 24 }),
      mkText('Showing 42 of 42 · sorted by date', { sz: 12, color: C.textMut, x: 32, y: 54 }),
      mkSelect('Sort', 'Newest first', { x: stageW - 280, y: 20, w: 240 }),
    );

    // Table header
    const colsHd = ['JOB', 'CHANNEL', 'SOURCE', 'CLIPS', 'SCORE', 'DURATION', 'DATE', ''];
    const colsX  = [60, 320, 460, 660, 720, 800, 900, stageW - 92];
    append(stage,
      mkLine(stageW - 64, { x: 32, y: 110 }),
    );
    colsHd.forEach((c, i) => {
      append(stage, mkText(c, { sz: 10, bold: true, color: C.textMut, x: colsX[i], y: 124, mono: true }));
    });
    append(stage, mkLine(stageW - 64, { x: 32, y: 144 }));

    // Rows
    const jobs = [
      ['podcast_ep_042',    'creator_x',   'youtube.com',     '5', '8.4', '12:18', '12 min ago',  'done'],
      ['interview_anna',    'tech_anna',   'youtube.com',     '3', '7.2', '8:22',  '2 hr ago',    'done'],
      ['conference_kn',     'creator_x',   'facebook.com',    '0', '—',   '—',     '4 hr ago',    'failed'],
      ['short_test',        'creator_x',   'tiktok.com',      '1', '6.1', '0:48',  'Yesterday',   'done'],
      ['recipe_walkthrough', 'cookbook',    'youtube.com',     '4', '8.9', '14:02', '2 days ago',  'done'],
      ['vlog_morning',      'creator_x',   'youtube.com',     '6', '7.8', '18:45', '3 days ago',  'done'],
      ['tutorial_part1',    'tech_anna',   'local file',      '3', '7.4', '10:12', '4 days ago',  'done'],
      ['speedrun_demo',     'tech_anna',   'tiktok.com',      '0', '—',   '—',     '5 days ago',  'cancelled'],
      ['live_replay',       'creator_x',   'youtube.com',     '8', '8.1', '22:30', '1 week ago',  'done'],
      ['quick_test',        'creator_x',   'local file',      '2', '6.7', '5:40',  '1 week ago',  'done'],
    ];
    jobs.forEach((j, i) => {
      const ry = 156 + i * 48;
      const row = mkFrame('row/' + j[0], stageW - 64, 44, {
        fill: i % 2 === 0 ? C.bg850 : null, x: 32, y: ry, cr: R.sm,
      });
      if (i % 2 !== 0) row.fills = [];
      const stCol = j[7] === 'done' ? C.success : j[7] === 'failed' ? C.danger : C.textMut;
      append(row,
        mkDot(8, stCol, { x: 14, y: 18 }),
        mkText(j[0], { sz: 12, bold: true, color: C.text, x: 28, y: 14, mono: true }),
        mkText(j[1], { sz: 11, color: C.textMid, x: colsX[1] - 32, y: 14 }),
        mkText(j[2], { sz: 11, color: C.textMut, x: colsX[2] - 32, y: 14, mono: true }),
        mkText(j[3], { sz: 12, bold: true, color: C.text, x: colsX[3] - 32, y: 13, mono: true }),
        mkText(j[4], { sz: 12, bold: true, color: j[4] === '—' ? C.textDim : stCol, x: colsX[4] - 32, y: 13, mono: true }),
        mkText(j[5], { sz: 11, color: C.textMid, x: colsX[5] - 32, y: 14, mono: true }),
        mkText(j[6], { sz: 11, color: C.textMut, x: colsX[6] - 32, y: 14 }),
        mkBtn('Open', { variant: 'ghost', size: 'sm', x: colsX[7] - 32, y: 8 }),
      );
      append(stage, row);
    });
    append(f, stage);

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     FRAME 19 · States · Empty / Loading / Error
     All edge cases in one frame for spec coverage.
  ───────────────────────────────────────────────────── */
  {
    const f = mkFrame('19 · States · Empty / Loading / Error', FW, FH, { fill: C.bg900 });
    drawTopbar(f);
    drawStatusBar(f);
    drawPageTitle(f, '19', 'States · Empty / Loading / Error', 'Edge cases for every major surface. Designers and engineers should match these visuals on first contact.');

    const bodyY = TOPBAR_H + 130;
    const cellW = (FW - 80 - 48) / 3;
    const cellH = 280;

    // EMPTY states
    append(f, mkSectionHead('Empty', { x: 40, y: bodyY, w: FW - 80 }));
    const emptyStates = [
      {
        title: 'No video loaded',
        sub: 'Paste a URL or choose a file to begin.',
        icon: '🎬',
        cta: 'Open Editor',
      },
      {
        title: 'No downloads yet',
        sub: 'Add links to the inbox to start fetching sources.',
        icon: '📥',
        cta: 'Add Links',
      },
      {
        title: 'No history',
        sub: 'Past render jobs will appear here after your first export.',
        icon: '📜',
        cta: null,
      },
    ];
    emptyStates.forEach((s, i) => {
      const cx = 40 + i * (cellW + 24);
      const cy = bodyY + 36;
      const card = mkCard(cellW, cellH, { elevation: 'flat', x: cx, y: cy });
      append(card,
        mkText(s.icon, { sz: 36, x: cellW / 2 - 18, y: 60 }),
        mkText(s.title, { sz: 14, bold: true, color: C.text, x: 24, y: 120, maxW: cellW - 48, align: 'CENTER' }),
        mkText(s.sub, { sz: 11, color: C.textMut, x: 24, y: 146, maxW: cellW - 48, align: 'CENTER' }),
      );
      if (s.cta) {
        append(card, mkBtn(s.cta, { variant: 'primary', size: 'md', x: (cellW - 120) / 2, y: 200, w: 120 }));
      }
      append(f, card);
    });

    // LOADING states
    append(f, mkSectionHead('Loading', { x: 40, y: bodyY + 340, w: FW - 80, accent: C.secondary }));
    const loadingStates = [
      { title: 'Preparing render…',  sub: 'cutting → transcribing', pct: 18,  color: C.warn },
      { title: 'Encoding part 3…',   sub: '142 fps · 11.8 Mbps',     pct: 67,  color: C.primary },
      { title: 'Finalizing output…', sub: 'writing files to disk',   pct: 96,  color: C.success },
    ];
    loadingStates.forEach((s, i) => {
      const cx = 40 + i * (cellW + 24);
      const cy = bodyY + 376;
      const card = mkCard(cellW, 180, { elevation: 'flat', x: cx, y: cy });
      // Spinning indicator faux: ring + dot
      const ring = mkRect(40, 40, null, { cr: 20, x: 24, y: 22, stroke: C.border, sw: 3 });
      const arc = mkRect(40, 40, null, { cr: 20, x: 24, y: 22, stroke: s.color, sw: 3 });
      arc.strokes = solid(s.color);
      append(card, ring, arc,
        mkText(s.title, { sz: 13, bold: true, color: C.text, x: 80, y: 24 }),
        mkText(s.sub, { sz: 11, color: C.textMut, x: 80, y: 44, mono: true }),
      );
      const [t, fl] = mkProgress(cellW - 48, s.pct, { x: 24, y: 86, h: 8, color: s.color });
      append(card, t, fl,
        mkText(s.pct + '%', { sz: 13, bold: true, color: s.color, x: 24, y: 108, mono: true }),
        mkText('ETA · ' + (s.pct < 30 ? '~10 min' : s.pct < 80 ? '~5 min' : '~30s'), {
          sz: 11, color: C.textMut, x: cellW - 100, y: 110,
        }),
        mkBtn('View Logs', { variant: 'ghost', size: 'sm', x: 24, y: 134 }),
        mkBtn('Pause', { variant: 'secondary', size: 'sm', x: 110, y: 134 }),
      );
      append(f, card);
    });

    placeFrame(f, allFrames.length);
    targetPage.appendChild(f);
    allFrames.push(f);
  }

  /* ─────────────────────────────────────────────────────
     ALSO add a second states frame for ERROR? 
     We'll cram error states into frame 19 by reducing the
     loading section if needed. For now we add a sub-section.
  ───────────────────────────────────────────────────── */


  /* ─────────────────────────────────────────────────────
     FRAME 20 · Developer Handoff
     The most important frame for implementation.
     Lists protected DOM IDs, JS bindings, CSS variables.
     Maps Figma tokens → CSS custom properties → real selectors.
  ───────────────────────────────────────────────────── */
  {
    // This frame is taller than others — 1440 × 1600 to fit all the handoff data
    const handoffH = 1600;
    const f = mkFrame('20 · Developer Handoff', FW, handoffH, { fill: C.bg900 });

    // Header
    append(f,
      mkRect(FW, 80, C.bg800, { x: 0, y: 0 }),
      mkLine(FW, { x: 0, y: 80 }),
      mkPill('CRITICAL · READ BEFORE IMPLEMENTING', {
        bg: C.danger, textColor: C.white, x: 40, y: 28, h: 26, sz: 11, stroke: C.danger,
      }),
      mkText('Developer Handoff', { sz: 22, bold: true, color: C.text, x: 40, y: 58, name: 'handoffTitle' }),
    );

    let cy = 116;

    // Section 1: How to read this Figma
    append(f, mkSectionHead('How to read this Figma', { x: 40, y: cy, w: FW - 80 }));
    cy += 36;
    const intro = [
      '· This is a VISUAL redesign. Layout structure (left nav / center / inspector / bottom / status) is unchanged.',
      '· All DOM IDs and JS bindings from the production build are preserved (listed below).',
      '· Color tokens map directly to existing CSS custom properties — only their VALUES change.',
      '· No JS rewrite required. Only HTML class additions (optional) and CSS overrides.',
      '· Recommended implementation path: ship a new "app-v2.css" alongside "app.css", toggle via body class.',
    ];
    intro.forEach((line, i) => {
      append(f, mkText(line, { sz: 12, color: C.textMid, x: 40, y: cy + i * 22, maxW: FW - 80 }));
    });
    cy += intro.length * 22 + 24;

    // Section 2: Token → CSS variable mapping
    append(f, mkSectionHead('CSS variable mapping · update :root in app.css', { x: 40, y: cy, w: FW - 80, accent: C.secondary }));
    cy += 36;
    const tokenTable = [
      ['--bg',          'old: #0b1220',  'new: #0a0a0c',  'app background'],
      ['--bg-elev',     'old: #111827',  'new: #1c1c24',  'card surface'],
      ['--bg-elev-2',   'old: #1f2937',  'new: #24242e',  'hover / elevated'],
      ['--bd',          'old: #1f2937',  'new: #2a2a35',  'border / divider'],
      ['--bd-hi',       'old: #374151',  'new: #3a3a48',  'input border'],
      ['--text',        'old: #e5e7eb',  'new: #f4f4f8',  'primary text'],
      ['--text-mut',    'old: #9ca3af',  'new: #85859a',  'muted label'],
      ['--text-dim',    'old: #6b7280',  'new: #5a5a6e',  'placeholder'],
      ['--accent',      'old: #3b82f6',  'new: #4d7cff',  'primary accent (Adobe-blue)'],
      ['--accent-hi',   'old: #60a5fa',  'new: #6b93ff',  'accent hover'],
      ['--accent-glow', 'old: #1e3a8a',  'new: #1e3a8a',  'soft accent bg (unchanged)'],
      ['--secondary',   '— (NEW)',       'new: #a855f7',  'creative purple accent'],
      ['--secondary-hi', '— (NEW)',      'new: #c084fc',  'purple hover'],
      ['--success',     'old: #10b981',  'new: #22c55e',  'success / done'],
      ['--warn',        'old: #f59e0b',  'new: #f59e0b',  'caution (unchanged)'],
      ['--danger',      'old: #ef4444',  'new: #ef4444',  'error (unchanged)'],
    ];
    // Headers
    const colWX = [60, 240, 440, 700];
    const colHd = ['CSS VAR', 'CURRENT', 'NEW', 'USAGE'];
    colHd.forEach((c, i) => {
      append(f, mkText(c, { sz: 10, bold: true, color: C.textMut, x: 40 + colWX[i] - 60 + 0, y: cy, mono: true }));
    });
    append(f, mkLine(FW - 80, { x: 40, y: cy + 18 }));
    cy += 24;
    tokenTable.forEach((row, i) => {
      const isAlt = i % 2 === 0;
      const rowBg = mkRect(FW - 80, 22, C.bg850, { x: 40, y: cy + i * 24, op: isAlt ? 1 : 0 });
      append(f, rowBg);
      append(f,
        mkText(row[0], { sz: 11, bold: true, color: C.primaryHi, x: 40 + colWX[0] - 60 + 12, y: cy + i * 24 + 4, mono: true }),
        mkText(row[1], { sz: 11, color: C.danger, x: 40 + colWX[1] - 60 + 12, y: cy + i * 24 + 4, mono: true }),
        mkText(row[2], { sz: 11, color: C.success, x: 40 + colWX[2] - 60 + 12, y: cy + i * 24 + 4, mono: true }),
        mkText(row[3], { sz: 11, color: C.textMid, x: 40 + colWX[3] - 60 + 12, y: cy + i * 24 + 4 }),
      );
    });
    cy += tokenTable.length * 24 + 28;

    // Section 3: Protected DOM IDs
    append(f, mkSectionHead('Protected DOM IDs · DO NOT RENAME', { x: 40, y: cy, w: FW - 80 }));
    cy += 36;
    append(f,
      mkText('These IDs are bound by JS. Renaming them will break render pipeline, websocket, upload manager, or editor.',
        { sz: 12, color: C.textMid, x: 40, y: cy, maxW: FW - 80 }),
    );
    cy += 28;

    // 3-column grid of protected IDs (grouped)
    const idGroups = [
      {
        title: 'Render pipeline',
        bound_by: 'render-ui.js · render-engine.js',
        ids: [
          'event_log_render',
          'job_bar',
          'job_percent',
          'job_stage_pill',
          'render_active_panel',
          'render_runtime_mount',
          'render_output_panel',
          'render_output_list',
          'rc_active_card',
          'rc_active_title',
          'rc_active_bar',
          'rc_part_cards',
          'rc_queue_summary',
          'rc_active_badge',
          'abp_retry_btn',
          'abp_error_block',
          'render_completion_bar',
          'appBottomPanel',
        ],
      },
      {
        title: 'Editor & Inspector',
        bound_by: 'editor-view.js · editor-modal.js',
        ids: [
          'view_editor',
          'appInspector',
          'evDivider',
          'evBatchBody',
          'evBatchMode',
          'evBatchUrls',
          'evBatchStatus',
          'evOutputPreset',
          'evPresetHint',
          'evPresetSummary',
          'evReframeStrategy',
          'evSourceQualityMode',
          'evSubPreviewImg',
          'evSubStaticText',
          'evTitleOverlayText',
          'evAddTitleOverlay',
          'mvAnalyzeBtn',
          'mvHookCard',
          'aiux_strategy_panel',
        ],
      },
      {
        title: 'Upload & Misc',
        bound_by: 'upload-manager.js · nav.js · partials-loader.js',
        ids: [
          'upload_manager_workspace',
          'upload_account_form_modal',
          'upload_video_library',
          'auto_plan_modal',
          'batch_assign_modal',
          'audit_log_list',
          'abpSetupPanel',
          'abpSetupToggle',
          'statusSystem',
          'toastRoot',
          'warmup_chip',
          'warmup_panel',
        ],
      },
    ];
    const gcolW = (FW - 80 - 32) / 3;
    idGroups.forEach((g, i) => {
      const gx = 40 + i * (gcolW + 16);
      const groupCard = mkCard(gcolW, 520, { elevation: 'flat', x: gx, y: cy });
      append(groupCard,
        mkText(g.title, { sz: 13, bold: true, color: C.text, x: 16, y: 14 }),
        mkText(g.bound_by, { sz: 10, color: C.textMut, x: 16, y: 32, mono: true }),
        mkLine(gcolW, { x: 0, y: 56 }),
      );
      g.ids.forEach((id, idx) => {
        append(groupCard,
          mkText('#' + id, {
            sz: 11, color: C.primaryHi, x: 16, y: 68 + idx * 22, mono: true,
          }),
        );
      });
      append(f, groupCard);
    });
    cy += 540;

    // Section 4: onclick handler contract
    append(f, mkSectionHead('Inline onclick handlers · function names must match', { x: 40, y: cy, w: FW - 80, accent: C.secondary }));
    cy += 36;
    append(f, mkText('48 onclick handlers in index.html call into global JS. Keep these function names callable.', {
      sz: 12, color: C.textMid, x: 40, y: cy,
    }));
    cy += 24;
    const handlers = [
      'evAddTextLayer', 'evApplyPreset', 'evApplyStylePreset', 'evImproveNarrationText',
      'evPickBgmFile', 'evReopenEditor', 'evResetTrim', 'evSeekClick', 'evSetLayerX',
      'evSetTrimIn', 'evSetTrimOut', 'evSetVolume', 'evToggleGuides', 'evToggleInspGroup',
      'evTogglePlay', 'backToEditorFromCompletion', 'browseLocalVideo', 'cancelEditorView',
      'cancelYtDownload', 'clearDownloadLinks', 'closeCenterPreview', 'closeClipPreview',
      'copyRenderDiagnostics', 'copyRenderLogs', 'filterRenderLogs', 'focusBottomPanel',
      'focusRenderLogPanel', 'mvAnalyzeMarket', 'mvCompareUse', 'openCsPreviewFolder',
    ];
    const handlersW = (FW - 80 - 24) / 4;
    handlers.forEach((h, i) => {
      const col = i % 4; const row = Math.floor(i / 4);
      append(f, mkText(h + '()', {
        sz: 11, color: C.primaryHi, x: 40 + col * (handlersW + 8), y: cy + row * 22, mono: true,
      }));
    });
    cy += Math.ceil(handlers.length / 4) * 22 + 28;

    // Section 5: Implementation plan (numbered)
    append(f, mkSectionHead('Recommended implementation plan', { x: 40, y: cy, w: FW - 80 }));
    cy += 36;
    const planSteps = [
      ['1', 'Audit phase', 'Pull this file + run existing app side-by-side. Confirm no missing IDs.'],
      ['2', 'Tokens swap',   'Update :root in css/app.css with new color values from Section 2. Keep variable NAMES the same. Test app immediately — should look refreshed without layout change.'],
      ['3', 'Add new tokens', 'Add --secondary, --secondary-hi, --secondary-glow to :root. Use in places where purple accent is desired (AI features, batch ops).'],
      ['4', 'Patch FIX-01 from Figma audit',  'Add :has() selector to suppress row-3 height when #appBottomPanel.renderCompatWrapper is present. Reclaim ~280-440px of vertical space.'],
      ['5', 'Component polish', 'Update padding/radius on .card, .btn, .input, .pill to match Figma. Use minimum-diff CSS edits.'],
      ['6', 'Typography',     'Add JetBrains Mono fallback in @font-face. Apply to timecodes, IDs, log lines (selectors already exist).'],
      ['7', 'Icon system',    'Replace ad-hoc icons with Phosphor/Lucide 1.5px outlined. NO change to icon container structure.'],
      ['8', 'Verification',   'Run end-to-end render job. Verify: upload → editor → render → output → history. Test in collapsed + expanded bottom panel modes.'],
      ['9', 'Rollback ready', 'Keep app.css backup. If anything breaks, restore from backup. The redesign is CSS-only — JS is untouched.'],
    ];
    planSteps.forEach((step, i) => {
      const sy = cy + i * 56;
      append(f,
        mkFrame('plan/' + step[0], 32, 32, { fill: C.primary, x: 40, y: sy, cr: R.pill }),
        mkText(step[0], { sz: 13, bold: true, color: C.white, x: 50, y: sy + 8 }),
        mkText(step[1], { sz: 13, bold: true, color: C.text, x: 88, y: sy + 2 }),
        mkText(step[2], { sz: 11, color: C.textMid, x: 88, y: sy + 22, maxW: FW - 160 }),
      );
    });
    cy += planSteps.length * 56 + 24;

    // Section 6: Risk checklist
    append(f, mkSectionHead('Risk checklist · verify before shipping', { x: 40, y: cy, w: FW - 80, accent: C.danger }));
    cy += 36;
    const risks = [
      ['Render queue updates correctly when job starts',  'rc_active_card, rc_part_cards updated by render-ui.js'],
      ['Live log streams without overflow clipping',       'event_log_render scroll bound to bottom on append'],
      ['Bottom panel expand/collapse animation smooth',   'No grid-template-rows jank when toggling abpCollapsed'],
      ['Inspector tabs switch without losing form state', 'evReframeStrategy, evOutputPreset values preserve'],
      ['Sidebar collapse mode keeps icon rail active state', 'rail/render highlighted when on Render tab'],
      ['Status bar updates GPU/FFmpeg/Whisper indicators', 'statusSystem polling endpoint unchanged'],
      ['Toast notifications appear in correct z-index',    'toastRoot must stay above modals'],
      ['Modal stack works: editor → batch → completion',   'No modal-on-modal z-index conflict'],
    ];
    risks.forEach((r, i) => {
      const ry = cy + i * 28;
      append(f,
        mkFrame('chk/' + i, 16, 16, { fill: null, x: 40, y: ry + 2, cr: R.xs }),
      );
      const cb = mkRect(16, 16, null, { x: 40, y: ry + 2, cr: R.xs, stroke: C.borderHi, sw: 1.5 });
      append(f, cb,
        mkText(r[0], { sz: 12, color: C.text, medium: true, x: 64, y: ry }),
        mkText(r[1], { sz: 10, color: C.textMut, x: 64, y: ry + 14, mono: true }),
      );
    });

    // Place this taller frame
    const idx = allFrames.length;
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    f.x = col * (FW + GAP);
    f.y = row * (FH + GAP);
    targetPage.appendChild(f);
    allFrames.push(f);
  }


  /* ─────────────────────────────────────────────────────
     STEP 9 — Finalize · select all frames and fit viewport
  ───────────────────────────────────────────────────── */
  figma.currentPage.selection = allFrames;
  figma.viewport.scrollAndZoomIntoView(allFrames);

  figma.notify(
    `AI Clip Studio V2 — ${allFrames.length} frames created on "${PAGE_NAME}".`,
    { timeout: 5000 },
  );

  console.log(`✅ V2 Redesign generated: ${allFrames.length} frames`);
  console.log(`   Page: "${PAGE_NAME}"`);
  console.log(`   Tokens: Adobe-blue (#4d7cff) + Creative purple (#a855f7)`);
  console.log(`   Read frame 20 (Developer Handoff) before implementing.`);

})().catch(err => {
  console.error('Figma plugin error:', err);
  figma.notify('Error: ' + err.message, { error: true });
});
