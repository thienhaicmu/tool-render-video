const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const BACKEND_URL = 'http://127.0.0.1:8000';
const HEALTH_URL = `${BACKEND_URL}/health`;
const VITE_DEV_URL = 'http://localhost:5173';
const isDev = process.env.ELECTRON_DEV === '1';
const DEV_ROOT = path.resolve(__dirname, '..');
const APP_ROOT = app.isPackaged ? process.resourcesPath : DEV_ROOT;
const BACKEND_DIR = path.join(APP_ROOT, 'backend');
const BACKEND_REQ_FILE = path.join(BACKEND_DIR, 'requirements.txt');
const BACKEND_EXE_PACKAGED = path.join(APP_ROOT, 'backend-bin', 'render-backend.exe');
const FFMPEG_BIN_PACKAGED = path.join(APP_ROOT, 'ffmpeg-bin', 'ffmpeg.exe');
const FFPROBE_BIN_PACKAGED = path.join(APP_ROOT, 'ffmpeg-bin', 'ffprobe.exe');
const USER_DATA_ROOT = app.getPath('userData');
const DATA_DIR = app.isPackaged
  ? path.join(USER_DATA_ROOT, 'data')
  : path.join(DEV_ROOT, 'data');
const VENV_DIR = app.isPackaged
  ? path.join(DATA_DIR, '.venv')
  : path.join(DEV_ROOT, 'backend', '.venv');
const BACKEND_VENV_PY = path.join(VENV_DIR, 'Scripts', 'python.exe');
const BACKEND_LOG_FILE = path.join(DATA_DIR, 'logs', 'desktop-backend.log');
const BOOTSTRAP_STATE_FILE = path.join(DATA_DIR, 'state', 'bootstrap-state.json');
const BOOTSTRAP_VERSION = 2;

let mainWindow = null;
let splashWindow = null;
let backendProc = null;
let isQuitting = false;

function ensureLogDir() {
  fs.mkdirSync(path.dirname(BACKEND_LOG_FILE), { recursive: true });
}

function appendBootstrapLog(message) {
  try {
    ensureLogDir();
    fs.appendFileSync(BACKEND_LOG_FILE, `[${new Date().toISOString()}] [bootstrap] ${message}\n`);
  } catch (_) {}
}

function readBootstrapState() {
  try {
    if (!fs.existsSync(BOOTSTRAP_STATE_FILE)) return null;
    const raw = fs.readFileSync(BOOTSTRAP_STATE_FILE, 'utf-8');
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function writeBootstrapState(state) {
  fs.mkdirSync(path.dirname(BOOTSTRAP_STATE_FILE), { recursive: true });
  fs.writeFileSync(BOOTSTRAP_STATE_FILE, JSON.stringify(state, null, 2), 'utf-8');
}

function requirementsHash() {
  if (!fs.existsSync(BACKEND_REQ_FILE)) return 'missing';
  const raw = fs.readFileSync(BACKEND_REQ_FILE);
  return crypto.createHash('sha256').update(raw).digest('hex');
}

function runCommand(command, args, opts = {}) {
  const { cwd = BACKEND_DIR, env = process.env } = opts;
  return new Promise((resolve) => {
    const proc = spawn(command, args, { cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => { stdout += String(d || ''); });
    proc.stderr.on('data', (d) => { stderr += String(d || ''); });
    proc.on('error', (err) => resolve({ code: 1, stdout, stderr: `${stderr}\n${String(err)}` }));
    proc.on('exit', (code) => resolve({ code: Number(code || 0), stdout, stderr }));
  });
}

async function findSystemPython() {
  const probes = [
    { cmd: 'py', args: ['-3.11'] },
    { cmd: 'py', args: ['-3'] },
    { cmd: 'python', args: [] },
    { cmd: 'python3', args: [] },
  ];
  for (const p of probes) {
    // eslint-disable-next-line no-await-in-loop
    const out = await runCommand(
      p.cmd,
      [...p.args, '-c', 'import sys; print(sys.executable)'],
      { cwd: APP_ROOT }
    );
    if (out.code === 0) {
      const exe = String(out.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop();
      if (exe && fs.existsSync(exe)) return exe;
    }
  }
  return null;
}

// ── Splash window ─────────────────────────────────────────────────────────────

let _lastSplashMsg = '';

async function createSplash() {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 260,
    frame: false,
    alwaysOnTop: true,
    center: true,
    resizable: false,
    skipTaskbar: true,
    backgroundColor: '#0f172a',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  await splashWindow.loadFile(path.join(__dirname, 'splash.html'));

  splashWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.show();
    }
  });

  splashWindow.on('closed', () => {
    splashWindow = null;
  });

  // Replay the last queued status once the renderer is ready to receive IPC.
  splashWindow.webContents.on('did-finish-load', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.webContents.send('boot-version', app.getVersion());

      if (_lastSplashMsg) {
        splashWindow.webContents.send('boot-status', _lastSplashMsg);
      }
    }
  });
}

function sendSplash(message) {
  _lastSplashMsg = message;

  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('boot-status', message);
  }
}

function closeSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
    splashWindow = null;
  }
}

// ── Error message mapping ─────────────────────────────────────────────────────

function mapErrorToCreatorMessage(rawMsg) {
  const msg = String(rawMsg || '');
  if (msg.includes('EADDRINUSE') || msg.includes('address already in use')) {
    return 'Another instance of Render Studio is already running.\n\nClose it and try again.';
  }
  if (app.isPackaged) {
    if (msg.includes('exit code') || msg.includes('ENOENT') || msg.includes('spawn')) {
      return 'The render engine could not start. Please restart the app.\n\nIf this keeps happening, re-install Render Studio.';
    }
    return 'The render engine did not start in time. Please restart the app.';
  }
  if (msg.includes('Python') || msg.includes('python')) {
    return `Python 3.11+ not found on this machine.\n\nInstall Python from python.org and restart.\n\nDetails: ${msg}`;
  }
  if (msg.includes('pip') || msg.includes('requirements')) {
    return `Failed to install Python dependencies.\n\nCheck internet connection and retry.\n\nDetails: ${msg}`;
  }
  if (msg.includes('playwright') || msg.includes('Playwright')) {
    return `Failed to install browser engine (Playwright).\n\nCheck internet connection and retry.\n\nDetails: ${msg}`;
  }
  return `Could not start render engine.\n\n${msg}`;
}

// ── Bootstrap: Python env + pip + playwright ──────────────────────────────────

async function ensureBackendBootstrap() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const reqHash = requirementsHash();
  const state = readBootstrapState();
  const alreadyReady = state
    && state.bootstrapVersion === BOOTSTRAP_VERSION
    && state.requirementsHash === reqHash
    && fs.existsSync(BACKEND_VENV_PY);
  if (alreadyReady) return;

  sendSplash('Setting up video tools (first run)...');
  appendBootstrapLog('Bootstrap start: creating/updating Python environment');
  const sysPy = await findSystemPython();
  if (!sysPy) {
    throw new Error('Python 3.11+ not found. Please install Python and retry.');
  }

  if (!fs.existsSync(BACKEND_VENV_PY)) {
    sendSplash('Creating workspace environment...');
    appendBootstrapLog(`Creating venv with ${sysPy}`);
    const mk = await runCommand(sysPy, ['-m', 'venv', VENV_DIR], { cwd: DATA_DIR });
    if (mk.code !== 0) {
      throw new Error(`Cannot create venv.\n${mk.stderr || mk.stdout}`);
    }
  }

  sendSplash('Installing video tools (this may take a few minutes on first run)...');
  appendBootstrapLog('Installing Python requirements');
  const pipInstall = await runCommand(BACKEND_VENV_PY, ['-m', 'pip', 'install', '-r', BACKEND_REQ_FILE], { cwd: BACKEND_DIR });
  if (pipInstall.code !== 0) {
    throw new Error(`Failed to install requirements.\n${pipInstall.stderr || pipInstall.stdout}`);
  }

  sendSplash('Installing browser engine...');
  appendBootstrapLog('Installing Playwright Chromium');
  const pwInstall = await runCommand(BACKEND_VENV_PY, ['-m', 'playwright', 'install', 'chromium'], { cwd: BACKEND_DIR });
  if (pwInstall.code !== 0) {
    throw new Error(`Failed to install Playwright Chromium.\n${pwInstall.stderr || pwInstall.stdout}`);
  }

  writeBootstrapState({
    bootstrapVersion: BOOTSTRAP_VERSION,
    requirementsHash: reqHash,
    updatedAt: new Date().toISOString(),
  });
  appendBootstrapLog('Bootstrap complete');
}

// ── Health + wait ─────────────────────────────────────────────────────────────

function killPortProcess(port) {
  return new Promise((resolve) => {
    const { exec } = require('child_process');
    exec(`netstat -ano | findstr :${port} | findstr LISTENING`, (err, stdout) => {
      if (err || !stdout.trim()) return resolve();
      const pid = stdout.trim().split(/\s+/).pop();
      if (!pid || isNaN(Number(pid))) return resolve();
      exec(`taskkill /F /PID ${pid}`, () => resolve());
    });
  });
}

function healthCheck(timeoutMs = 1000) {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, { timeout: timeoutMs }, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitBackendReady(maxWaitMs = 120000, onTick = null) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await healthCheck(1200);
    if (ok) return true;
    const elapsed = Math.round((Date.now() - start) / 1000);
    if (onTick) onTick(elapsed);
    // eslint-disable-next-line no-await-in-loop
    await wait(1000);
  }
  return false;
}

// ── Backend spawn ─────────────────────────────────────────────────────────────

function startBackendWithCommand(command, args) {
  return new Promise((resolve, reject) => {
    const channelsDir = app.isPackaged ? path.join(DATA_DIR, 'channels') : path.join(DEV_ROOT, 'channels');
    const tempDir = path.join(DATA_DIR, 'temp');
    const tmpDir = path.join(DATA_DIR, 'tmp');
    const cacheDir = path.join(DATA_DIR, 'cache');
    const torchDir = path.join(DATA_DIR, 'torch');
    const hfDir = path.join(DATA_DIR, 'huggingface');
    const pwDir = path.join(DATA_DIR, 'playwright');
    fs.mkdirSync(channelsDir, { recursive: true });
    fs.mkdirSync(tempDir, { recursive: true });
    fs.mkdirSync(tmpDir, { recursive: true });
    fs.mkdirSync(cacheDir, { recursive: true });
    fs.mkdirSync(torchDir, { recursive: true });
    fs.mkdirSync(hfDir, { recursive: true });
    fs.mkdirSync(path.join(hfDir, 'hub'), { recursive: true });
    fs.mkdirSync(path.join(DATA_DIR, 'ollama', 'models'), { recursive: true });
    fs.mkdirSync(pwDir, { recursive: true });
    const env = {
      ...process.env,
      STATIC_UI_VERSION: 'v2',
      APP_DATA_DIR: DATA_DIR,
      DATABASE_PATH: path.join(DATA_DIR, 'app.db'),
      REPORTS_DIR: path.join(DATA_DIR, 'reports'),
      CHANNELS_DIR: channelsDir,
      TEMP_DIR: tempDir,
      XDG_CACHE_HOME: cacheDir,
      TORCH_HOME: torchDir,
      HF_HOME: hfDir,
      TRANSFORMERS_CACHE: path.join(hfDir, 'hub'),
      OLLAMA_MODELS: path.join(DATA_DIR, 'ollama', 'models'),
      TEMP: tmpDir,
      TMP: tmpDir,
      PLAYWRIGHT_BROWSERS_PATH: pwDir,
      PYTHONUNBUFFERED: '1',
    };
    if (app.isPackaged && fs.existsSync(FFMPEG_BIN_PACKAGED) && fs.existsSync(FFPROBE_BIN_PACKAGED)) {
      env.FFMPEG_BIN = FFMPEG_BIN_PACKAGED;
      env.FFPROBE_BIN = FFPROBE_BIN_PACKAGED;
    }

    const proc = spawn(command, args, {
      cwd: BACKEND_DIR,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env,
    });
    ensureLogDir();
    const logStream = fs.createWriteStream(BACKEND_LOG_FILE, { flags: 'a' });
    logStream.write(`\n[${new Date().toISOString()}] spawn: ${command} ${args.join(' ')}\n`);
    let stderr = '';
    proc.stdout.on('data', (d) => { logStream.write(String(d)); });
    proc.stderr.on('data', (d) => { stderr += String(d); });
    proc.stderr.on('data', (d) => { logStream.write(String(d)); });
    proc.on('error', (err) => reject(err));
    proc.on('spawn', () => {
      backendProc = proc;
      resolve();
    });
    proc.on('exit', (code) => {
      logStream.write(`[${new Date().toISOString()}] exit code: ${code}\n`);
      try { logStream.end(); } catch (_) {}
      if (backendProc === proc) {
        backendProc = null;
      }
      if (code !== 0 && stderr && !mainWindow && !isQuitting) {
        reject(new Error(stderr));
      }
    });
  });
}

async function startBackend() {
  if (app.isPackaged && fs.existsSync(BACKEND_EXE_PACKAGED)) {
    sendSplash('Starting render engine...');
    await startBackendWithCommand(BACKEND_EXE_PACKAGED, []);
    return;
  }
  await ensureBackendBootstrap();
  sendSplash('Starting render engine...');
  const uvicornArgs = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'];
  const candidates = [
    ...(fs.existsSync(BACKEND_VENV_PY)
      ? [{ cmd: BACKEND_VENV_PY, args: uvicornArgs }]
      : []),
    { cmd: 'py',      args: ['-3', ...uvicornArgs] },
    { cmd: 'python',  args: uvicornArgs },
    { cmd: 'python3', args: uvicornArgs },
  ];
  let lastErr = null;
  for (const c of candidates) {
    try {
      // eslint-disable-next-line no-await-in-loop
      await startBackendWithCommand(c.cmd, c.args);
      return;
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(
    (lastErr && lastErr.message) ||
    'Cannot start local backend. Make sure Python and uvicorn dependencies are installed.'
  );
}

// ── Main window ───────────────────────────────────────────────────────────────

function createWindow() {
  const iconPath = path.join(__dirname, 'build', 'icon.ico');
  const winOpts = {
    width: 1460,
    height: 980,
    minWidth: 1200,
    minHeight: 760,
    autoHideMenuBar: true,
    show: false,
    backgroundColor: '#0f172a',
    title: 'Render Studio Desktop',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  };
  if (fs.existsSync(iconPath)) {
    winOpts.icon = iconPath;
  }
  mainWindow = new BrowserWindow(winOpts);
  mainWindow.once('ready-to-show', () => {
    closeSplash();
    mainWindow.show();
  });
  if (isDev) {
    mainWindow.loadURL(VITE_DEV_URL);
  } else {
    // Force fresh UI load to avoid stale cached index.html after frontend updates.
    mainWindow.webContents.session.clearCache().catch(() => {});
    mainWindow.loadURL(`${BACKEND_URL}/?v=${Date.now()}`);
  }
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

async function bootstrap() {
  createSplash();
  try {
    if (isDev) {
      sendSplash('Dev mode — waiting for backend on :8000 ...');
    } else {
      sendSplash('Restarting render engine...');
      await killPortProcess(8000);
      await wait(500);
      await startBackend();
    }
    const maxWait = 120000;
    const ok = await waitBackendReady(maxWait, (elapsed) => {
      const remaining = Math.max(0, Math.round((maxWait / 1000) - elapsed));
      sendSplash(`Starting render engine... (${remaining}s)`);
    });
    if (!ok) {
      throw new Error('Backend did not become healthy on http://localhost:8000/health');
    }
    sendSplash('Opening Render Studio...');
    createWindow();
  } catch (e) {
    closeSplash();
    const creatorMsg = mapErrorToCreatorMessage(e.message || String(e));
    const result = await dialog.showMessageBox({
      type: 'error',
      title: 'Render Studio — Could Not Start',
      message: 'Render Studio could not start.',
      detail: `${creatorMsg}\n\nLog: ${BACKEND_LOG_FILE}`,
      buttons: ['Open Log File', 'Quit'],
      defaultId: 1,
      cancelId: 1,
    });
    if (result.response === 0) {
      shell.openPath(BACKEND_LOG_FILE);
    }
    app.quit();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(bootstrap);
}

app.on('before-quit', () => { isQuitting = true; });

app.on('window-all-closed', () => {
  if (backendProc && !backendProc.killed) {
    try { backendProc.kill(); } catch (_) {}
  }
  if (process.platform !== 'darwin') app.quit();
});

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('pick-video-file', async () => {
  const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null;
  try {
    const result = await dialog.showOpenDialog(win || undefined, {
      title: 'Choose Video File',
      properties: ['openFile'],
      filters: [
        { name: 'Video Files', extensions: ['mp4', 'mov', 'mkv', 'avi', 'webm', 'wmv', 'm4v', 'flv'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths || !result.filePaths.length) return null;
    return String(result.filePaths[0] || '');
  } catch (err) {
    console.error('[FilePicker] error:', err);
    return null;
  }
});

ipcMain.handle('pick-cookies-file', async () => {
  const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null;
  try {
    const result = await dialog.showOpenDialog(win || undefined, {
      title: 'Choose cookies.txt file (exported from Chrome extension)',
      properties: ['openFile'],
      filters: [
        { name: 'Cookies file', extensions: ['txt'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths || !result.filePaths.length) return null;
    return String(result.filePaths[0] || '');
  } catch (err) {
    console.error('[CookiePicker] error:', err);
    return null;
  }
});

ipcMain.handle('app:getVersion', () => app.getVersion());

ipcMain.handle('path:exists', (_event, targetPath) => {
  const p = String(targetPath || '').trim();
  return p ? fs.existsSync(p) : false;
});

ipcMain.handle('open-folder-picker', async () => {
  const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null;
  try {
    const result = await dialog.showOpenDialog(win || undefined, {
      title: 'Choose Profile Folder',
      properties: ['openDirectory'],
    });
    if (result.canceled || !result.filePaths || !result.filePaths.length) return null;
    return String(result.filePaths[0] || '');
  } catch (err) {
    console.error('[FolderPicker] error:', err);
    return null;
  }
});

ipcMain.handle('dialog:pickDirectory', async () => {
  const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null;
  const result = await dialog.showOpenDialog(win || undefined, {
    title: 'Choose Channels Root Folder',
    properties: ['openDirectory'],
  });
  if (result.canceled || !result.filePaths || !result.filePaths.length) return '';
  return String(result.filePaths[0] || '');
});

ipcMain.handle('shell:openPath', async (_event, targetPath) => {
  const p = String(targetPath || '').trim();
  if (!p) return 'Missing path';
  return shell.openPath(p);
});

// ---------------------------------------------------------------------------
// open-browser-profile: launch Chrome/Edge with isolated profile + proxy
// ---------------------------------------------------------------------------
const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

function findBrowserExe() {
  for (const p of CHROME_CANDIDATES) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

ipcMain.handle('open-browser-profile', async (_event, opts) => {
  const profilePath = String((opts && opts.profilePath) || '').trim();
  if (!profilePath) {
    return { ok: false, error: 'profilePath is required' };
  }

  const browserExe = findBrowserExe();
  if (!browserExe) {
    return {
      ok: false,
      error: 'Chrome or Edge not found. Install Google Chrome and retry.',
    };
  }

  try {
    fs.mkdirSync(profilePath, { recursive: true });
  } catch (_) {}

  const args = [
    `--user-data-dir=${profilePath}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-sync',
    '--disable-translate',
  ];

  const proxyServer = String((opts && opts.proxyServer) || '').trim();
  if (proxyServer) {
    args.push(`--proxy-server=${proxyServer}`);
  }

  if (opts && opts.timezone) {
    args.push(`--lang=${String(opts.locale || 'en-US')}`);
  }

  try {
    const child = spawn(browserExe, args, { detached: true, stdio: 'ignore' });
    child.unref();
    appendBootstrapLog(`[profile] Opened browser profile: ${profilePath} (proxy: ${proxyServer || 'none'})`);
    return { ok: true, browser: path.basename(browserExe) };
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  }
});
