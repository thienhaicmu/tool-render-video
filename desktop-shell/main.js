const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const BACKEND_URL = 'http://127.0.0.1:8000';
const HEALTH_URL = `${BACKEND_URL}/health`;
const DEV_ROOT = path.resolve(__dirname, '..');
const APP_ROOT = app.isPackaged ? process.resourcesPath : DEV_ROOT;
const BACKEND_DIR = path.join(APP_ROOT, 'backend');
const BACKEND_REQ_FILE = path.join(BACKEND_DIR, 'requirements.txt');
const BACKEND_EXE_PACKAGED = path.join(APP_ROOT, 'backend-bin', 'render-backend.exe');
const DATA_DIR = app.isPackaged
  ? path.join(path.dirname(process.execPath), 'data')
  : path.join(DEV_ROOT, 'data');
const VENV_DIR = app.isPackaged
  ? path.join(DATA_DIR, '.venv')
  : path.join(DEV_ROOT, 'backend', '.venv');
const BACKEND_VENV_PY = path.join(VENV_DIR, 'Scripts', 'python.exe');
const BACKEND_LOG_FILE = path.join(DATA_DIR, 'logs', 'desktop-backend.log');
const BOOTSTRAP_STATE_FILE = path.join(DATA_DIR, 'state', 'bootstrap-state.json');
const BOOTSTRAP_VERSION = 2;

let mainWindow = null;
let backendProc = null;

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

async function ensureBackendBootstrap() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const reqHash = requirementsHash();
  const state = readBootstrapState();
  const alreadyReady = state
    && state.bootstrapVersion === BOOTSTRAP_VERSION
    && state.requirementsHash === reqHash
    && fs.existsSync(BACKEND_VENV_PY);
  if (alreadyReady) return;

  appendBootstrapLog('Bootstrap start: creating/updating Python environment');
  const sysPy = await findSystemPython();
  if (!sysPy) {
    throw new Error('Python 3.11+ not found. Please install Python and retry.');
  }

  if (!fs.existsSync(BACKEND_VENV_PY)) {
    appendBootstrapLog(`Creating venv with ${sysPy}`);
    const mk = await runCommand(sysPy, ['-m', 'venv', VENV_DIR], { cwd: DATA_DIR });
    if (mk.code !== 0) {
      throw new Error(`Cannot create venv.\n${mk.stderr || mk.stdout}`);
    }
  }

  appendBootstrapLog('Installing Python requirements');
  const pipInstall = await runCommand(BACKEND_VENV_PY, ['-m', 'pip', 'install', '-r', BACKEND_REQ_FILE], { cwd: BACKEND_DIR });
  if (pipInstall.code !== 0) {
    throw new Error(`Failed to install requirements.\n${pipInstall.stderr || pipInstall.stdout}`);
  }

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

async function waitBackendReady(maxWaitMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await healthCheck(1200);
    if (ok) return true;
    // eslint-disable-next-line no-await-in-loop
    await wait(1000);
  }
  return false;
}

function isUvicornCmd(args) {
  const joined = args.join(' ');
  return joined.includes('uvicorn') && joined.includes('app.main:app');
}

function startBackendWithCommand(command, args) {
  return new Promise((resolve, reject) => {
    const channelsDir = app.isPackaged ? path.join(DATA_DIR, 'channels') : path.join(DEV_ROOT, 'channels');
    fs.mkdirSync(channelsDir, { recursive: true });
    const env = {
      ...process.env,
      APP_DATA_DIR:    DATA_DIR,
      DATABASE_PATH:   path.join(DATA_DIR, 'app.db'),
      REPORTS_DIR:     path.join(DATA_DIR, 'reports'),
      CHANNELS_DIR:    channelsDir,
      TEMP_DIR:        path.join(DATA_DIR, 'temp'),
      PYTHONUNBUFFERED: '1',
    };

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
      // If process exits immediately after spawn, report useful error.
      if (code !== 0 && stderr && !mainWindow) {
        reject(new Error(stderr));
      }
    });
  });
}

async function startBackend() {
  // Offline packaged mode: prebuilt backend executable, no first-run pip install.
  if (app.isPackaged && fs.existsSync(BACKEND_EXE_PACKAGED)) {
    await startBackendWithCommand(BACKEND_EXE_PACKAGED, []);
    return;
  }
  await ensureBackendBootstrap();
  const candidates = [
    ...(fs.existsSync(BACKEND_VENV_PY)
      ? [{ cmd: BACKEND_VENV_PY, args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'] }]
      : []),
    { cmd: 'py', args: ['-3', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'] },
    { cmd: 'python', args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'] },
    { cmd: 'python3', args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'] },
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

function createWindow() {
  const iconPath = path.join(__dirname, 'build', 'icon.ico');
  const winOpts = {
    width: 1460,
    height: 980,
    minWidth: 1200,
    minHeight: 760,
    autoHideMenuBar: true,
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
  mainWindow.loadURL(BACKEND_URL);
}

async function bootstrap() {
  try {
    const ready = await healthCheck();
    if (!ready) {
      await startBackend();
    }
    const ok = await waitBackendReady();
    if (!ok) {
      throw new Error('Backend did not become healthy on http://localhost:8000/health');
    }
    createWindow();
  } catch (e) {
    dialog.showErrorBox(
      'Cannot start desktop app',
      `Failed to start local backend.\n\n${e.message || String(e)}\n\n` +
      `See log: ${BACKEND_LOG_FILE}\n\n` +
      'Make sure Python is installed and backend dependencies are installed.'
    );
    app.quit();
  }
}

app.whenReady().then(bootstrap);

ipcMain.handle('dialog:pickDirectory', async () => {
  const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null;
  const result = await dialog.showOpenDialog(win || undefined, {
    title: 'Choose Channels Root Folder',
    properties: ['openDirectory'],
  });
  if (result.canceled || !result.filePaths || !result.filePaths.length) return '';
  return String(result.filePaths[0] || '');
});
app.on('window-all-closed', () => {
  if (backendProc && !backendProc.killed) {
    try { backendProc.kill(); } catch (_) {}
  }
  if (process.platform !== 'darwin') app.quit();
});
