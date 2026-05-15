/**
 * AI Clip Studio - Figma Plugin Template
 *
 * Usage:
 * 1. Paste this file into a Figma plugin `code.js`, or point your plugin manifest to it.
 * 2. Edit CONFIG, TOKENS, COMPONENTS, and SCREENS.
 * 3. Run the plugin in Figma Desktop.
 *
 * MCP adaptation:
 * - Remove the async IIFE wrapper if your MCP runner already wraps code.
 * - Replace `figma.currentPage = page` with `await figma.setCurrentPageAsync(page)`.
 * - Replace `figma.notify(...)` / `console.log(...)` with `return result`.
 */

(async () => {
  const CONFIG = {
    pageName: "AI Clip Studio - Template",
    frameWidth: 1440,
    frameHeight: 900,
    gap: 120,
    columns: 3,
    clearPageBeforeRun: true,
    font: {
      ui: "Inter",
      mono: "JetBrains Mono"
    }
  };

  await loadFonts(CONFIG.font);

  const TOKENS = {
    color: {
      bg: hex("#0A0A0C"),
      chrome: hex("#101014"),
      panel: hex("#16161C"),
      card: hex("#1C1C24"),
      elevated: hex("#24242E"),
      active: hex("#2D2D3A"),
      border: hex("#2A2A35"),
      borderStrong: hex("#3A3A48"),
      text: hex("#F4F4F8"),
      textMuted: hex("#85859A"),
      textSoft: hex("#B8B8C4"),
      primary: hex("#4D7CFF"),
      primarySoft: hex("#1E3A8A"),
      secondary: hex("#A855F7"),
      secondarySoft: hex("#581C87"),
      success: hex("#22C55E"),
      warning: hex("#F59E0B"),
      danger: hex("#EF4444"),
      info: hex("#06B6D4"),
      white: hex("#FFFFFF"),
      black: hex("#000000")
    },
    radius: {
      sm: 6,
      md: 8,
      lg: 12,
      xl: 16,
      pill: 999
    },
    spacing: {
      xs: 4,
      sm: 8,
      md: 12,
      lg: 16,
      xl: 24,
      xxl: 32
    },
    type: {
      display: 28,
      h1: 22,
      h2: 18,
      h3: 15,
      body: 13,
      small: 12,
      micro: 11,
      label: 10
    }
  };

  const SCREENS = [
    {
      id: "cover",
      title: "00 - Cover",
      subtitle: "Design philosophy, product promise, and non-negotiable rules.",
      kind: "cover"
    },
    {
      id: "tokens",
      title: "01 - Design Tokens",
      subtitle: "Color, typography, radius, spacing, and semantic states.",
      kind: "tokens"
    },
    {
      id: "components",
      title: "02 - Components",
      subtitle: "Reusable UI primitives and product-specific components.",
      kind: "components"
    },
    {
      id: "source",
      title: "03 - Source",
      subtitle: "Prepare source session from YouTube or local file.",
      kind: "workspace",
      entity: "SourceSession",
      panels: ["Source input", "Output folder", "Health check", "Preview session"]
    },
    {
      id: "studio",
      title: "04 - Studio",
      subtitle: "Guided production around preview, not a settings dump.",
      kind: "studio",
      entity: "RenderDraft / RenderRequest",
      panels: ["Clip generation", "Subtitles", "Voice", "Camera", "Market + AI"]
    },
    {
      id: "monitor",
      title: "05 - Monitor",
      subtitle: "Progress and recovery. Logs are secondary.",
      kind: "monitor",
      entity: "Job / JobPart",
      panels: ["Stage", "Parts", "Transport", "Recovery"]
    },
    {
      id: "results",
      title: "06 - Results",
      subtitle: "Hero moment: ranked clips, best clip, explanations, export.",
      kind: "results",
      entity: "ResultPackage / OutputClip",
      panels: ["Best clip", "Ranking", "Why selected", "AI summary", "Failed parts"]
    },
    {
      id: "handoff",
      title: "99 - Engineering Handoff",
      subtitle: "Implementation notes, protected contracts, risk checklist.",
      kind: "handoff"
    }
  ];

  const COMPONENT_GROUPS = [
    "Navigation",
    "Workspace Shell",
    "Preview Surface",
    "Forms",
    "Buttons",
    "Status Chips",
    "Progress",
    "Result Cards",
    "AI Indicators",
    "Diagnostics",
    "Errors",
    "Handoff Notes"
  ];

  const page = getOrCreatePage(CONFIG.pageName);
  figma.currentPage = page;
  if (CONFIG.clearPageBeforeRun) {
    [...page.children].forEach((node) => node.remove());
  }

  const frames = [];
  SCREENS.forEach((screen, index) => {
    const frame = createScreen(screen, index);
    placeFrame(frame, index);
    page.appendChild(frame);
    frames.push(frame);
  });

  figma.currentPage.selection = frames;
  figma.viewport.scrollAndZoomIntoView(frames);
  figma.notify(`Generated ${frames.length} template frames on "${CONFIG.pageName}".`);

  function createScreen(screen) {
    const frame = mkFrame(screen.title, CONFIG.frameWidth, CONFIG.frameHeight, {
      fill: TOKENS.color.bg
    });
    append(frame, topBar(screen.title, screen.subtitle));

    if (screen.kind === "cover") drawCover(frame);
    else if (screen.kind === "tokens") drawTokens(frame);
    else if (screen.kind === "components") drawComponents(frame);
    else if (screen.kind === "studio") drawStudio(frame, screen);
    else if (screen.kind === "monitor") drawMonitor(frame, screen);
    else if (screen.kind === "results") drawResults(frame, screen);
    else if (screen.kind === "handoff") drawHandoff(frame);
    else drawWorkspace(frame, screen);

    return frame;
  }

  function drawCover(parent) {
    append(
      parent,
      text("AI Clip Studio Template", 64, 120, {
        size: 42,
        weight: "Bold",
        color: TOKENS.color.text,
        maxWidth: 900
      }),
      text("Premium desktop creator workstation. Workflow reference only; do not copy legacy UI visually.", 64, 178, {
        size: 16,
        color: TOKENS.color.textSoft,
        maxWidth: 900
      })
    );

    const flow = mkFrame("Creator Flow", 1280, 170, { x: 64, y: 280, fill: null });
    ["Import", "Optimize", "Render", "Review", "Reuse"].forEach((label, i) => {
      append(flow, principleCard(label, i * 250, 0));
    });
    append(parent, flow);
    append(parent, noteCard("Rules", [
      "Implemented capabilities only.",
      "No fake cloud, collaboration, analytics, timeline editor, AI chat, or one-click publishing.",
      "Results are the hero experience.",
      "AI must be bounded and explainable."
    ], 64, 520, 620, 220));
  }

  function drawTokens(parent) {
    const keys = Object.keys(TOKENS.color);
    keys.forEach((key, i) => {
      const x = 64 + (i % 5) * 250;
      const y = 130 + Math.floor(i / 5) * 110;
      append(parent, tokenSwatch(key, TOKENS.color[key], x, y));
    });
    append(parent, noteCard("Token intent", [
      "Neutral dark foundation.",
      "Primary accent for action.",
      "Secondary accent for AI/creative assistance.",
      "Semantic status colors stay consistent."
    ], 64, 620, 780, 180));
  }

  function drawComponents(parent) {
    COMPONENT_GROUPS.forEach((name, i) => {
      const x = 64 + (i % 3) * 430;
      const y = 130 + Math.floor(i / 3) * 118;
      append(parent, componentMarker(name, x, y));
    });
  }

  function drawWorkspace(parent, screen) {
    append(parent, navRail(screen.id), workspaceHeader(screen), contentPanel(screen, 370, 170, 560, 540), annotationRail(screen));
  }

  function drawStudio(parent, screen) {
    append(parent, navRail(screen.id), workspaceHeader(screen));
    append(parent, previewPanel(350, 170, 430, 620));
    const controls = mkPanel("Guided Controls", 820, 170, 300, 620);
    screen.panels.forEach((panel, i) => append(controls, rowItem(panel, 18, 58 + i * 96, i === 4 ? TOKENS.color.secondary : TOKENS.color.borderStrong)));
    append(parent, controls, annotationRail(screen));
  }

  function drawMonitor(parent, screen) {
    append(parent, navRail(screen.id), workspaceHeader(screen));
    const progress = mkPanel("Render Confidence", 350, 170, 610, 180);
    append(progress, progressBar(24, 72, 520, 12, 0.68, TOKENS.color.primary));
    append(progress, text("WebSocket live. Polling fallback remains authoritative.", 24, 112, { size: 12, color: TOKENS.color.textSoft, maxWidth: 520 }));
    const parts = mkPanel("Part Progress", 350, 380, 610, 360);
    ["Part 1 completed", "Part 2 rendering", "Part 3 queued", "Part 4 waiting"].forEach((label, i) => {
      append(parts, rowItem(label, 18, 60 + i * 70, i === 1 ? TOKENS.color.primary : i === 0 ? TOKENS.color.success : TOKENS.color.borderStrong));
    });
    append(parent, progress, parts, annotationRail(screen));
  }

  function drawResults(parent, screen) {
    append(parent, navRail(screen.id), workspaceHeader(screen));
    append(parent, previewPanel(330, 160, 430, 650));
    const ranking = mkPanel("Ranked Outputs", 800, 160, 300, 650);
    ["#1 Best clip - 92", "#2 Strong hook - 86", "#3 Review - 79", "Failed part - recover"].forEach((label, i) => {
      append(ranking, rowItem(label, 18, 60 + i * 100, i === 0 ? TOKENS.color.primary : i === 3 ? TOKENS.color.warning : TOKENS.color.borderStrong));
    });
    const explain = mkPanel("Why Selected", 1130, 160, 250, 650);
    ["Ranking reason", "Voice/subtitle summary", "AI explanation", "Failed parts detail"].forEach((label, i) => {
      append(explain, rowItem(label, 16, 58 + i * 112, i === 2 ? TOKENS.color.secondary : TOKENS.color.borderStrong));
    });
    append(parent, ranking, explain);
  }

  function drawHandoff(parent) {
    append(parent, noteCard("Implementation contract", [
      "One parser per entity family.",
      "Feature modules own state.",
      "DOM is not source of truth.",
      "WebSocket accelerates; polling remains fallback.",
      "Optional AI metadata must never crash UI."
    ], 64, 140, 660, 260));
    append(parent, noteCard("MCP conversion notes", [
      "Use await figma.setCurrentPageAsync(page).",
      "Remove figma.notify for MCP.",
      "Return created node IDs from MCP calls.",
      "Work incrementally for large files."
    ], 760, 140, 600, 260));
  }

  function topBar(title, subtitle) {
    const bar = mkFrame("Top Bar", CONFIG.frameWidth, 84, { fill: TOKENS.color.chrome });
    append(
      bar,
      text(title, 32, 22, { size: 20, weight: "Bold", color: TOKENS.color.text }),
      text(subtitle, 32, 50, { size: 12, color: TOKENS.color.textSoft, maxWidth: 980 }),
      pill("TEMPLATE", CONFIG.frameWidth - 150, 28, TOKENS.color.primary)
    );
    return bar;
  }

  function navRail(activeId) {
    const rail = mkFrame("Navigation Rail", 250, 760, { x: 40, y: 110, fill: TOKENS.color.chrome, radius: TOKENS.radius.lg, stroke: TOKENS.color.border });
    ["source", "studio", "monitor", "results", "library", "downloads", "system"].forEach((id, i) => {
      const active = activeId === id;
      append(rail, navItem(id, active, 16, 24 + i * 56));
    });
    return rail;
  }

  function workspaceHeader(screen) {
    return noteCard(screen.entity || "Screen Owner", [
      screen.subtitle,
      "Panels: " + (screen.panels || []).join(", ")
    ], 330, 110, 1030, 82);
  }

  function contentPanel(screen, x, y, w, h) {
    const panel = mkPanel(screen.title + " Content", x, y, w, h);
    (screen.panels || []).forEach((item, i) => {
      append(panel, rowItem(item, 18, 58 + i * 86, TOKENS.color.borderStrong));
    });
    return panel;
  }

  function annotationRail(screen) {
    return noteCard("Engineering Mapping", [
      "Entity: " + (screen.entity || "n/a"),
      "Owner: features/" + screen.id,
      "Optional data degrades safely.",
      "Unsupported features stay out of scope."
    ], 970, 170, 390, 540);
  }

  function principleCard(label, x, y) {
    const card = mkPanel(label, x, y, 220, 150);
    append(card, text("Maps to real workflow", 18, 66, { size: 12, color: TOKENS.color.textSoft, maxWidth: 180 }));
    return card;
  }

  function tokenSwatch(name, color, x, y) {
    const group = mkFrame("Token / " + name, 220, 84, { x, y, fill: TOKENS.color.panel, radius: TOKENS.radius.md, stroke: TOKENS.color.border });
    append(group, rect(18, 18, 48, 48, color, TOKENS.radius.sm), text(name, 82, 24, { size: 12, weight: "Bold" }), text(rgbToHex(color), 82, 46, { size: 11, color: TOKENS.color.textMuted }));
    return group;
  }

  function componentMarker(name, x, y) {
    const item = mkFrame("Component / " + name, 390, 84, { x, y, fill: TOKENS.color.panel, radius: TOKENS.radius.md, stroke: TOKENS.color.border });
    append(item, rect(18, 22, 34, 34, TOKENS.color.active, TOKENS.radius.sm), text(name, 70, 24, { size: 13, weight: "Bold" }), text("Reusable component group", 70, 46, { size: 11, color: TOKENS.color.textMuted }));
    return item;
  }

  function previewPanel(x, y, w, h) {
    const panel = mkPanel("Preview Surface", x, y, w, h);
    append(panel, rect((w - 250) / 2, 60, 250, 445, TOKENS.color.chrome, TOKENS.radius.xl, TOKENS.color.borderStrong));
    append(panel, text("Backend media endpoint", 76, h - 80, { size: 12, color: TOKENS.color.textSoft, maxWidth: w - 120 }));
    return panel;
  }

  function mkPanel(name, x, y, w, h) {
    const panel = mkFrame(name, w, h, { x, y, fill: TOKENS.color.panel, radius: TOKENS.radius.lg, stroke: TOKENS.color.border });
    append(panel, text(name, 18, 24, { size: 15, weight: "Bold", color: TOKENS.color.text }));
    return panel;
  }

  function rowItem(label, x, y, tone) {
    const item = mkFrame("Row / " + label, 280, 54, { x, y, fill: TOKENS.color.card, radius: TOKENS.radius.md, stroke: tone || TOKENS.color.border });
    append(item, rect(12, 14, 4, 26, tone || TOKENS.color.primary, 2), text(label, 28, 18, { size: 12, weight: "Medium", maxWidth: 220 }));
    return item;
  }

  function noteCard(title, lines, x, y, w, h) {
    const card = mkFrame("Note / " + title, w, h, { x, y, fill: TOKENS.color.panel, radius: TOKENS.radius.lg, stroke: TOKENS.color.border });
    append(card, text(title, 18, 22, { size: 16, weight: "Bold", color: TOKENS.color.text }));
    lines.forEach((line, i) => {
      append(card, text(line, 18, 58 + i * 24, { size: 12, color: TOKENS.color.textSoft, maxWidth: w - 36 }));
    });
    return card;
  }

  function navItem(label, active, x, y) {
    const item = mkFrame("Nav Item / " + label, 218, 42, { x, y, fill: active ? TOKENS.color.active : null, radius: TOKENS.radius.md, stroke: active ? TOKENS.color.primary : null });
    append(item, text(label, 16, 13, { size: 12, weight: active ? "Bold" : "Medium", color: active ? TOKENS.color.text : TOKENS.color.textMuted }));
    return item;
  }

  function pill(label, x, y, color) {
    const p = mkFrame("Pill / " + label, 100, 26, { x, y, fill: TOKENS.color.card, radius: TOKENS.radius.pill, stroke: color });
    append(p, text(label, 18, 8, { size: 10, weight: "Bold", color }));
    return p;
  }

  function progressBar(x, y, w, h, value, color) {
    const track = mkFrame("Progress", w, h, { x, y, fill: TOKENS.color.elevated, radius: h / 2 });
    append(track, rect(0, 0, Math.max(1, w * value), h, color, h / 2));
    return track;
  }

  function mkFrame(name, w, h, options = {}) {
    const node = figma.createFrame();
    node.name = name;
    node.resize(w, h);
    node.x = options.x || 0;
    node.y = options.y || 0;
    node.fills = options.fill ? [{ type: "SOLID", color: options.fill }] : [];
    node.cornerRadius = options.radius || 0;
    node.clipsContent = false;
    if (options.stroke) {
      node.strokes = [{ type: "SOLID", color: options.stroke }];
      node.strokeWeight = 1;
    }
    return node;
  }

  function rect(x, y, w, h, color, radius = 0, stroke) {
    const node = figma.createRectangle();
    node.name = "Rect";
    node.resize(w, h);
    node.x = x;
    node.y = y;
    node.cornerRadius = radius;
    node.fills = [{ type: "SOLID", color }];
    if (stroke) {
      node.strokes = [{ type: "SOLID", color: stroke }];
      node.strokeWeight = 1;
    }
    return node;
  }

  function text(value, x, y, options = {}) {
    const node = figma.createText();
    const style = options.weight === "Bold" ? "Bold" : options.weight === "Medium" ? "Medium" : "Regular";
    node.fontName = { family: CONFIG.font.ui, style };
    node.characters = value;
    node.fontSize = options.size || 13;
    node.x = x;
    node.y = y;
    node.fills = [{ type: "SOLID", color: options.color || TOKENS.color.text }];
    node.lineHeight = { unit: "PERCENT", value: 130 };
    node.letterSpacing = { unit: "PIXELS", value: 0 };
    if (options.maxWidth) {
      node.resize(options.maxWidth, 20);
      node.textAutoResize = "HEIGHT";
    }
    return node;
  }

  function append(parent, ...children) {
    children.forEach((child) => {
      if (child) parent.appendChild(child);
    });
  }

  function placeFrame(frame, index) {
    const col = index % CONFIG.columns;
    const row = Math.floor(index / CONFIG.columns);
    frame.x = col * (CONFIG.frameWidth + CONFIG.gap);
    frame.y = row * (CONFIG.frameHeight + CONFIG.gap);
  }

  function getOrCreatePage(name) {
    let page = figma.root.children.find((item) => item.name === name);
    if (!page) {
      page = figma.createPage();
      page.name = name;
    }
    return page;
  }

  async function loadFonts(font) {
    await Promise.all([
      figma.loadFontAsync({ family: font.ui, style: "Regular" }),
      figma.loadFontAsync({ family: font.ui, style: "Medium" }),
      figma.loadFontAsync({ family: font.ui, style: "Bold" })
    ]);
  }

  function hex(value) {
    const raw = value.replace("#", "");
    const parsed = parseInt(raw, 16);
    return {
      r: ((parsed >> 16) & 255) / 255,
      g: ((parsed >> 8) & 255) / 255,
      b: (parsed & 255) / 255
    };
  }

  function rgbToHex(color) {
    const r = Math.round(color.r * 255).toString(16).padStart(2, "0");
    const g = Math.round(color.g * 255).toString(16).padStart(2, "0");
    const b = Math.round(color.b * 255).toString(16).padStart(2, "0");
    return "#" + r + g + b;
  }
})();
