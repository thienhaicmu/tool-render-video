// Premium Creator Workstation V1
// Figma Plugin API generator.
// This is not production frontend code. It creates an implementation-safe
// design artifact that maps visual surfaces to real backend contracts.

const PAGE_MODE = "sections"; // "pages" for paid plans, "sections" for Starter page limits.

const TOKENS = {
  color: {
    bg: "#101214",
    bgRaised: "#15181B",
    surface: "#1B2024",
    surfaceRaised: "#242A30",
    selected: "#2C343A",
    border: "#38414A",
    borderStrong: "#4A5661",
    text: "#F4F7F9",
    muted: "#AAB4BE",
    faint: "#737F89",
    accent: "#76E0C0",
    accentSoft: "#1E5A4D",
    ai: "#B8A6FF",
    aiSoft: "#352D55",
    running: "#79B8FF",
    success: "#74D48F",
    warning: "#F2C66E",
    failed: "#FF7C7C",
    partial: "#F19A5B",
    unsupported: "#85818E"
  },
  space: [4, 8, 12, 16, 20, 24, 32, 40, 48, 64],
  radius: {
    control: 8,
    panel: 10,
    media: 14,
    frame: 22
  },
  type: {
    screenTitle: 28,
    sectionTitle: 18,
    body: 13,
    caption: 11,
    metric: 24
  }
};

const REQUIRED_SCREEN_NAMES = [
  "Cover / Product Principles",
  "Source",
  "Studio",
  "Monitor",
  "Results",
  "Library",
  "Downloads",
  "Publish Advanced",
  "System",
  "States + Errors",
  "Engineering Handoff",
  "Out of Scope"
];

const COMPONENT_GROUPS = [
  "Navigation",
  "Workspace Shell",
  "Media Preview",
  "Source Components",
  "Studio Controls",
  "Subtitle Controls",
  "Voice Controls",
  "AI Controls",
  "Monitor Components",
  "Result Components",
  "Ranking Components",
  "Library Components",
  "Download Components",
  "Publish Components",
  "System Components",
  "Forms",
  "Feedback",
  "Errors",
  "Progress",
  "AI State Indicators",
  "Diagnostics",
  "Status Chips",
  "Output Cards",
  "Result Ranking Cards"
];

const SCREEN_CONTRACTS = {
  Source: {
    owner: "features/source",
    entity: "SourceSession",
    endpoint: "POST /api/render/prepare-source",
    purpose: "Prepare YouTube or local source into a browser-safe preview session.",
    panels: ["Source input", "Output destination", "Source health", "Preview session"]
  },
  Studio: {
    owner: "features/studio",
    entity: "RenderDraft / RenderRequest",
    endpoint: "POST /api/render/process",
    purpose: "Build a valid render draft around stable preview playback.",
    panels: ["Preview anchor", "Clip generation", "Subtitles", "Voice", "Camera", "Market + AI"]
  },
  Monitor: {
    owner: "features/monitor",
    entity: "Job / JobPart",
    endpoint: "GET /api/jobs/{job_id}, WS /api/jobs/{job_id}/ws",
    purpose: "Track local render progress and recovery without logs-first UX.",
    panels: ["Job stage", "Part progress", "Transport", "Recovery", "Diagnostics"]
  },
  Results: {
    owner: "features/results",
    entity: "ResultPackage / OutputClip / AIInsightSummary",
    endpoint: "jobs.result_json, /api/jobs/{job_id}/parts/{part_no}/stream",
    purpose: "Hero review moment for ranked clips, best clip, explanations, and export.",
    panels: ["Best clip preview", "Ranked outputs", "Why selected", "AI explanation", "Failed parts"]
  },
  Library: {
    owner: "features/library",
    entity: "HistoryItem / Job reference",
    endpoint: "GET /api/jobs/history",
    purpose: "Re-enter render and download work by real status.",
    panels: ["Filters", "History list", "Selected package", "Recovery actions"]
  },
  Downloads: {
    owner: "features/downloads",
    entity: "DownloadJob / DownloadItem",
    endpoint: "POST /api/download/process",
    purpose: "Standalone public video download workflow.",
    panels: ["Batch URLs", "Output folder", "Item statuses", "Retry failed"]
  },
  "Publish Advanced": {
    owner: "features/publish-advanced",
    entity: "UploadQueueItem / Account / Scheduler",
    endpoint: "/api/upload/*",
    purpose: "Advanced upload automation only; no guaranteed publishing.",
    panels: ["Accounts", "Videos", "Queue", "Scheduler", "Proxies"]
  },
  System: {
    owner: "features/system",
    entity: "SystemReadiness / DesktopCapabilities",
    endpoint: "/api/warmup/status, /api/render/ai-diagnostics",
    purpose: "Local runtime readiness and desktop adapter state.",
    panels: ["FFmpeg", "yt-dlp", "Whisper", "AI diagnostics", "Desktop adapter"]
  }
};

function hexToRgb(hex) {
  const value = hex.replace("#", "");
  const parsed = parseInt(value, 16);
  return {
    r: ((parsed >> 16) & 255) / 255,
    g: ((parsed >> 8) & 255) / 255,
    b: (parsed & 255) / 255
  };
}

function paint(hex, opacity) {
  return {
    type: "SOLID",
    color: hexToRgb(hex),
    opacity: opacity === undefined ? 1 : opacity
  };
}

async function loadFonts() {
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Medium" });
  await figma.loadFontAsync({ family: "Inter", style: "Semi Bold" });
  await figma.loadFontAsync({ family: "Inter", style: "Bold" });
}

function applyAutoLayout(node, direction, gap, padding) {
  node.layoutMode = direction;
  node.itemSpacing = gap;
  node.paddingTop = padding;
  node.paddingRight = padding;
  node.paddingBottom = padding;
  node.paddingLeft = padding;
  node.primaryAxisSizingMode = "FIXED";
  node.counterAxisSizingMode = "FIXED";
}

function makeFrame(name, width, height, options = {}) {
  const node = figma.createFrame();
  node.name = name;
  node.resize(width, height);
  node.constraints = options.constraints || { horizontal: "MIN", vertical: "MIN" };
  node.fills = [paint(options.fill || TOKENS.color.bg)];
  node.cornerRadius = options.radius === undefined ? 0 : options.radius;
  node.clipsContent = Boolean(options.clips);
  if (options.stroke) {
    node.strokes = [paint(options.stroke)];
    node.strokeWeight = 1;
  }
  if (options.layout) {
    applyAutoLayout(node, options.layout, options.gap || 0, options.padding || 0);
  }
  if (options.shadow) {
    node.effects = [{
      type: "DROP_SHADOW",
      color: { r: 0, g: 0, b: 0, a: 0.18 },
      offset: { x: 0, y: 12 },
      radius: 28,
      spread: 0,
      visible: true,
      blendMode: "NORMAL"
    }];
  }
  return node;
}

function makeComponent(name, width, height) {
  const node = figma.createComponent();
  node.name = name;
  node.resize(width, height);
  node.constraints = { horizontal: "MIN", vertical: "MIN" };
  node.fills = [paint(TOKENS.color.surface)];
  node.strokes = [paint(TOKENS.color.border)];
  node.strokeWeight = 1;
  node.cornerRadius = TOKENS.radius.control;
  applyAutoLayout(node, "HORIZONTAL", 10, 12);
  return node;
}

function makeText(name, value, size, color, style, width) {
  const node = figma.createText();
  node.name = name;
  node.fontName = { family: "Inter", style: style || "Regular" };
  node.characters = value;
  node.fontSize = size;
  node.fills = [paint(color || TOKENS.color.text)];
  node.lineHeight = { unit: "PERCENT", value: size >= 24 ? 112 : 138 };
  node.letterSpacing = { unit: "PIXELS", value: 0 };
  node.resize(width || 240, 10);
  node.textAutoResize = "HEIGHT";
  return node;
}

function makeRect(name, width, height, color, radius, stroke) {
  const node = figma.createRectangle();
  node.name = name;
  node.resize(width, height);
  node.constraints = { horizontal: "MIN", vertical: "MIN" };
  node.fills = [paint(color)];
  node.cornerRadius = radius || 0;
  if (stroke) {
    node.strokes = [paint(stroke)];
    node.strokeWeight = 1;
  }
  return node;
}

function chip(label, color) {
  const node = makeFrame("Status Chip / " + label, 128, 28, {
    fill: TOKENS.color.surfaceRaised,
    stroke: color,
    radius: 14,
    layout: "HORIZONTAL",
    gap: 0,
    padding: 6
  });
  const labelNode = makeText("Label", label, 11, color, "Semi Bold", 116);
  labelNode.textAlignHorizontal = "CENTER";
  node.appendChild(labelNode);
  return node;
}

function annotation(title, lines, width) {
  const node = makeFrame("Annotation / " + title, width || 340, 180, {
    fill: TOKENS.color.bgRaised,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.panel,
    layout: "VERTICAL",
    gap: 8,
    padding: 16
  });
  node.appendChild(makeText("Title", title, 15, TOKENS.color.text, "Semi Bold", width ? width - 32 : 308));
  lines.forEach((line) => node.appendChild(makeText("Note", line, 11, TOKENS.color.muted, "Regular", width ? width - 32 : 308)));
  return node;
}

function addPanel(parent, title, detail, tone) {
  const panel = makeFrame("Panel / " + title, 320, 72, {
    fill: TOKENS.color.surface,
    stroke: tone || TOKENS.color.border,
    radius: TOKENS.radius.control,
    layout: "VERTICAL",
    gap: 4,
    padding: 12
  });
  panel.appendChild(makeText("Title", title, 14, TOKENS.color.text, "Semi Bold", 290));
  panel.appendChild(makeText("Detail", detail, 11, TOKENS.color.muted, "Regular", 290));
  parent.appendChild(panel);
  return panel;
}

function makeNav(active) {
  const nav = makeFrame("Navigation / Rail", 86, 780, {
    fill: "#0E1012",
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.panel,
    layout: "VERTICAL",
    gap: 10,
    padding: 10
  });
  nav.appendChild(makeText("Brand", "CV", 18, TOKENS.color.accent, "Bold", 60));
  ["Source", "Studio", "Monitor", "Results", "Library", "Downloads", "Publish", "System"].forEach((item) => {
    const activeItem = active === item || (active === "Publish Advanced" && item === "Publish");
    const row = makeFrame("Navigation Item / " + item + (activeItem ? " / Active" : ""), 64, 52, {
      fill: activeItem ? TOKENS.color.selected : "#0E1012",
      stroke: activeItem ? TOKENS.color.accent : undefined,
      radius: TOKENS.radius.control,
      layout: "VERTICAL",
      gap: 2,
      padding: 5
    });
    const txt = makeText("Label", item, 9, activeItem ? TOKENS.color.text : TOKENS.color.muted, "Medium", 54);
    txt.textAlignHorizontal = "CENTER";
    row.appendChild(txt);
    nav.appendChild(row);
  });
  return nav;
}

function makePreview(label) {
  const node = makeFrame("Media Preview / Stable 9:16", 410, 610, {
    fill: "#080A0C",
    stroke: TOKENS.color.borderStrong,
    radius: TOKENS.radius.media,
    layout: "VERTICAL",
    gap: 14,
    padding: 24
  });
  const video = makeFrame("Video Canvas / Backend Media Endpoint", 310, 500, {
    fill: TOKENS.color.bgRaised,
    stroke: TOKENS.color.border,
    radius: 16,
    layout: "VERTICAL",
    gap: 12,
    padding: 20
  });
  video.appendChild(makeRect("Subtitle Safe Line", 240, 2, TOKENS.color.accent, 1));
  video.appendChild(makeText("Preview Label", label, 17, TOKENS.color.text, "Semi Bold", 260));
  video.appendChild(makeText("Endpoint Note", "Use media/stream endpoints, not raw local paths.", 11, TOKENS.color.muted, "Regular", 260));
  node.appendChild(video);
  return node;
}

function makeScreenFrame(name, contract, state) {
  const screen = makeFrame(name + " / " + state + " / Desktop / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: name === "Results" ? TOKENS.color.accent : TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "HORIZONTAL",
    gap: 20,
    padding: 24
  });
  screen.appendChild(makeNav(name));

  const content = makeFrame("Workspace Shell / Content", 1280, 820, {
    fill: TOKENS.color.bg,
    layout: "VERTICAL",
    gap: 16,
    padding: 0
  });
  const header = makeFrame("Workspace Header", 1280, 74, {
    fill: TOKENS.color.bg,
    layout: "HORIZONTAL",
    gap: 16,
    padding: 0
  });
  const title = makeFrame("Title Group", 760, 74, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 4, padding: 0 });
  title.appendChild(makeText("Screen Title", name, 28, TOKENS.color.text, "Bold", 720));
  title.appendChild(makeText("Purpose", contract.purpose, 12, TOKENS.color.muted, "Regular", 720));
  header.appendChild(title);
  header.appendChild(chip(state, state === "Failure" ? TOKENS.color.failed : state === "Partial Warning" ? TOKENS.color.partial : TOKENS.color.accent));
  content.appendChild(header);

  const body = makeFrame("Screen Body / " + name, 1280, 730, {
    fill: TOKENS.color.bg,
    layout: "HORIZONTAL",
    gap: 18,
    padding: 0
  });
  const primary = makeFrame("Primary Region / " + name, 830, 730, {
    fill: TOKENS.color.bgRaised,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.panel,
    layout: "VERTICAL",
    gap: 14,
    padding: 20
  });

  if (name === "Studio") {
    const row = makeFrame("Studio Guided Production Layout", 790, 620, { fill: TOKENS.color.bgRaised, layout: "HORIZONTAL", gap: 18, padding: 0 });
    row.appendChild(makePreview("Prepared preview anchor"));
    const controls = makeFrame("Progressive Controls", 340, 610, {
      fill: TOKENS.color.surface,
      stroke: TOKENS.color.border,
      radius: TOKENS.radius.panel,
      layout: "VERTICAL",
      gap: 10,
      padding: 14
    });
    contract.panels.forEach((panel, index) => addPanel(controls, panel, index === 5 ? "bounded AI controls" : "mapped to RenderRequest", index === 5 ? TOKENS.color.ai : TOKENS.color.border));
    row.appendChild(controls);
    primary.appendChild(row);
  } else if (name === "Results") {
    const row = makeFrame("Results Hero Layout", 790, 620, { fill: TOKENS.color.bgRaised, layout: "HORIZONTAL", gap: 18, padding: 0 });
    row.appendChild(makePreview("Best ranked clip"));
    const ranking = makeFrame("Ranked Output List", 340, 610, {
      fill: TOKENS.color.surface,
      stroke: TOKENS.color.border,
      radius: TOKENS.radius.panel,
      layout: "VERTICAL",
      gap: 10,
      padding: 14
    });
    addPanel(ranking, "#1 Best clip", "output_ranking + best_clip + score reason", TOKENS.color.accent);
    addPanel(ranking, "#2 Strong hook", "valid output, lower score", TOKENS.color.border);
    addPanel(ranking, "#3 Review", "quality warning available", TOKENS.color.warning);
    addPanel(ranking, "Failed part", "preserved in recovery panel", TOKENS.color.partial);
    row.appendChild(ranking);
    primary.appendChild(row);
  } else if (name === "Monitor") {
    addPanel(primary, "Overall progress", "stage, percent, queue and transport", TOKENS.color.running);
    addPanel(primary, "Part 1 completed", "JobPart status done", TOKENS.color.success);
    addPanel(primary, "Part 2 running", "WebSocket live, polling fallback", TOKENS.color.running);
    addPanel(primary, "Part 3 queued", "waiting for local render capacity", TOKENS.color.border);
    addPanel(primary, "Recovery", "retry/resume only where backend supports it", TOKENS.color.warning);
  } else {
    contract.panels.forEach((panel, index) => {
      const tones = [TOKENS.color.accent, TOKENS.color.running, TOKENS.color.ai, TOKENS.color.warning, TOKENS.color.success, TOKENS.color.partial];
      addPanel(primary, panel, "Owner: " + contract.owner + " / Entity: " + contract.entity, tones[index % tones.length]);
    });
  }
  body.appendChild(primary);

  const side = makeFrame("Annotation Rail / " + name, 400, 730, {
    fill: TOKENS.color.bg,
    layout: "VERTICAL",
    gap: 14,
    padding: 0
  });
  side.appendChild(annotation("Engineering Contract", [
    "Owner: " + contract.owner,
    "Entity: " + contract.entity,
    "Endpoint: " + contract.endpoint
  ], 390));
  side.appendChild(annotation("State Behavior", [
    "State: " + state,
    "Optional metadata must degrade safely.",
    "No current UI visual reuse."
  ], 390));
  side.appendChild(annotation("Unsupported Here", [
    "No cloud/collaboration/analytics.",
    "No fake timeline or AI chat.",
    "No fake one-click publish."
  ], 390));
  body.appendChild(side);
  content.appendChild(body);
  screen.appendChild(content);
  return screen;
}

function createTokenPage(parent) {
  const frame = makeFrame("02 Design Tokens / Foundation / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 22,
    padding: 36
  });
  frame.appendChild(makeText("Title", "Design Tokens", 34, TOKENS.color.text, "Bold", 900));
  const colorGrid = makeFrame("Color Token Grid", 1320, 220, { fill: TOKENS.color.bg, layout: "HORIZONTAL", gap: 12, padding: 0 });
  Object.keys(TOKENS.color).forEach((key) => {
    const swatch = makeFrame("Token / color / " + key, 92, 138, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 8, padding: 0 });
    swatch.appendChild(makeRect("Swatch", 92, 70, TOKENS.color[key], 8, TOKENS.color.border));
    swatch.appendChild(makeText("Name", key, 10, TOKENS.color.muted, "Medium", 92));
    colorGrid.appendChild(swatch);
  });
  frame.appendChild(colorGrid);
  frame.appendChild(annotation("Token Constraints", [
    "Neutral foundation with restrained accent.",
    "Status semantics are consistent across job, part and result states.",
    "AI accent supports explanation; it does not dominate the product."
  ], 900));
  parent.appendChild(frame);
  return frame;
}

function createComponentLibrary(parent) {
  const frame = makeFrame("03 Components / Component System / V1", 1440, 1280, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 18,
    padding: 36
  });
  frame.appendChild(makeText("Title", "Component System", 34, TOKENS.color.text, "Bold", 900));
  const grid = makeFrame("Component Groups", 1320, 1040, { fill: TOKENS.color.bg, layout: "HORIZONTAL", gap: 14, padding: 0 });
  const columns = [makeFrame("Column 1", 315, 1040, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 10, padding: 0 }), makeFrame("Column 2", 315, 1040, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 10, padding: 0 }), makeFrame("Column 3", 315, 1040, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 10, padding: 0 }), makeFrame("Column 4", 315, 1040, { fill: TOKENS.color.bg, layout: "VERTICAL", gap: 10, padding: 0 })];
  columns.forEach((column) => grid.appendChild(column));
  COMPONENT_GROUPS.forEach((group, index) => {
    const component = makeComponent(group + " / Component Marker", 300, 44);
    component.appendChild(makeRect("Icon Slot", 20, 20, TOKENS.color.selected, 5, TOKENS.color.border));
    component.appendChild(makeText("Name", group, 12, TOKENS.color.text, "Medium", 240));
    columns[index % columns.length].appendChild(component);
  });
  frame.appendChild(grid);
  parent.appendChild(frame);
  return frame;
}

function createCover(parent) {
  const frame = makeFrame("Cover / Product Principles / Desktop / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 26,
    padding: 48
  });
  frame.appendChild(makeText("Title", "Premium Creator Workstation V1", 54, TOKENS.color.text, "Bold", 1100));
  frame.appendChild(makeText("Subtitle", "AI-assisted local rendering intelligence for creator clips. Current UI is workflow reference only.", 18, TOKENS.color.muted, "Regular", 1100));
  const flow = makeFrame("Creator Mental Model", 1260, 148, { fill: TOKENS.color.bg, layout: "HORIZONTAL", gap: 16, padding: 0 });
  ["Import content", "Optimize intelligently", "Render confidently", "Review best results"].forEach((label, index) => {
    const card = makeFrame("Principle / " + label, 300, 148, {
      fill: TOKENS.color.surface,
      stroke: [TOKENS.color.accent, TOKENS.color.ai, TOKENS.color.running, TOKENS.color.success][index],
      radius: TOKENS.radius.panel,
      layout: "VERTICAL",
      gap: 8,
      padding: 18
    });
    card.appendChild(makeText("Label", label, 21, TOKENS.color.text, "Bold", 250));
    card.appendChild(makeText("Description", "Maps to implemented workflow and backend contracts.", 12, TOKENS.color.muted, "Regular", 250));
    flow.appendChild(card);
  });
  frame.appendChild(flow);
  frame.appendChild(annotation("Hard Rules", [
    "No current UI visual reuse.",
    "No unsupported product capabilities.",
    "Results are the hero product moment.",
    "AI is bounded: advisory, passive, explainable, advanced, execution influence."
  ], 900));
  parent.appendChild(frame);
  return frame;
}

function createStates(parent) {
  const frame = makeFrame("States + Errors / Desktop / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 22,
    padding: 40
  });
  frame.appendChild(makeText("Title", "States + Errors", 34, TOKENS.color.text, "Bold", 900));
  const states = ["queued", "running", "completed", "partial", "failed", "interrupted", "unsupported", "unavailable"];
  const colors = [TOKENS.color.faint, TOKENS.color.running, TOKENS.color.success, TOKENS.color.partial, TOKENS.color.failed, TOKENS.color.warning, TOKENS.color.unsupported, TOKENS.color.faint];
  const row = makeFrame("State Chips", 1300, 160, { fill: TOKENS.color.bg, layout: "HORIZONTAL", gap: 12, padding: 0 });
  states.forEach((state, index) => row.appendChild(chip(state, colors[index])));
  frame.appendChild(row);
  frame.appendChild(annotation("Recovery Contract", [
    "Partial success keeps successful outputs primary.",
    "Failed part details stay visible.",
    "Interrupted jobs use supported resume/retry paths.",
    "Missing optional AI metadata never crashes UI."
  ], 900));
  parent.appendChild(frame);
  return frame;
}

function createHandoff(parent) {
  const frame = makeFrame("Engineering Handoff / Desktop / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.border,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 18,
    padding: 40
  });
  frame.appendChild(makeText("Title", "Engineering Handoff", 34, TOKENS.color.text, "Bold", 900));
  Object.keys(SCREEN_CONTRACTS).forEach((name) => {
    const contract = SCREEN_CONTRACTS[name];
    addPanel(frame, name + " -> " + contract.entity, contract.endpoint, TOKENS.color.border);
  });
  frame.appendChild(annotation("Implementation Guardrails", [
    "One parser per entity family.",
    "Feature modules own state.",
    "Shared primitives do not know backend field names.",
    "Desktop behavior goes through adapter boundary."
  ], 900));
  parent.appendChild(frame);
  return frame;
}

function createOutOfScope(parent) {
  const frame = makeFrame("Out of Scope / Unsupported Capability Parking Lot / V1", 1440, 900, {
    fill: TOKENS.color.bg,
    stroke: TOKENS.color.failed,
    radius: TOKENS.radius.frame,
    layout: "VERTICAL",
    gap: 14,
    padding: 40
  });
  frame.appendChild(makeText("Title", "Out of Scope", 34, TOKENS.color.text, "Bold", 900));
  [
    "Cloud sync or cloud rendering",
    "Multi-user collaboration, teams, roles, billing, permissions",
    "Social analytics dashboard or campaign planning",
    "Full nonlinear timeline or arbitrary clip sequencing",
    "AI prompt box for arbitrary video editing",
    "AI rewriting arbitrary FFmpeg commands or inventing timestamps",
    "Official platform API publishing or guaranteed upload success",
    "Guaranteed perfect translation, mastering, or cinematic crop",
    "Mobile-first app and current UI visual reuse"
  ].forEach((item) => addPanel(frame, item, "Unsupported in current implementation.", TOKENS.color.failed));
  parent.appendChild(frame);
  return frame;
}

function createOrGetPage(name) {
  let page = figma.root.children.find((candidate) => candidate.name === name);
  if (!page) {
    page = figma.createPage();
    page.name = name;
  }
  return page;
}

async function cleanPage(page) {
  await figma.setCurrentPageAsync(page);
  for (const child of [...page.children]) {
    child.remove();
  }
}

async function buildWithPages() {
  const pages = {};
  for (const name of [
    "00 Cover + Principles",
    "02 Design Tokens",
    "03 Components",
    "04 Source",
    "05 Studio",
    "06 Monitor",
    "07 Results",
    "08 Library",
    "09 Downloads",
    "10 Publish Advanced",
    "11 System",
    "12 States + Errors",
    "13 Engineering Handoff",
    "99 Out of Scope"
  ]) {
    pages[name] = createOrGetPage(name);
    await cleanPage(pages[name]);
  }
  await figma.setCurrentPageAsync(pages["00 Cover + Principles"]);
  createCover(pages["00 Cover + Principles"]);
  createTokenPage(pages["02 Design Tokens"]);
  createComponentLibrary(pages["03 Components"]);
  Object.keys(SCREEN_CONTRACTS).forEach((name) => {
    const pageName = name === "Publish Advanced" ? "10 Publish Advanced" : "0" + (4 + Object.keys(SCREEN_CONTRACTS).indexOf(name)) + " " + name;
    const screen = makeScreenFrame(name, SCREEN_CONTRACTS[name], "Default");
    pages[pageName].appendChild(screen);
  });
  createStates(pages["12 States + Errors"]);
  createHandoff(pages["13 Engineering Handoff"]);
  createOutOfScope(pages["99 Out of Scope"]);
}

async function buildWithSections() {
  const page = createOrGetPage("Premium Creator Workstation V1");
  await cleanPage(page);
  await figma.setCurrentPageAsync(page);
  const builders = [
    ["00 Cover + Product Principles", createCover],
    ["02 Design Tokens", createTokenPage],
    ["03 Components", createComponentLibrary],
    ...Object.keys(SCREEN_CONTRACTS).map((name) => [name, (parent) => parent.appendChild(makeScreenFrame(name, SCREEN_CONTRACTS[name], "Default"))]),
    ["12 States + Errors", createStates],
    ["13 Engineering Handoff", createHandoff],
    ["99 Out of Scope", createOutOfScope]
  ];
  let x = 80;
  let y = 80;
  builders.forEach(([sectionName, builder], index) => {
    const section = figma.createSection();
    section.name = sectionName;
    section.x = x;
    section.y = y;
    section.resizeWithoutConstraints(1540, sectionName === "03 Components" ? 1420 : 980);
    page.appendChild(section);
    const before = page.children.length;
    builder(page);
    const created = page.children[page.children.length - 1];
    created.x = x + 40;
    created.y = y + 60;
    if (before === page.children.length) {
      throw new Error("Builder did not create a top-level frame for " + sectionName);
    }
    x += 1600;
    if ((index + 1) % 3 === 0) {
      x = 80;
      y += sectionName === "03 Components" ? 1500 : 1040;
    }
  });
}

async function main() {
  await loadFonts();
  if (PAGE_MODE === "pages") {
    await buildWithPages();
  } else {
    await buildWithSections();
  }
  const targetPage = figma.root.children.find((page) => page.name === "Premium Creator Workstation V1") || figma.root.children[0];
  await figma.setCurrentPageAsync(targetPage);
  figma.viewport.scrollAndZoomIntoView(targetPage.children);
  figma.closePlugin("Premium Creator Workstation V1 generated.");
}

main().catch((error) => {
  figma.closePlugin("Generation failed: " + error.message);
});
