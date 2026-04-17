#!/usr/bin/env node
// Reads render error logs and prints formatted entries.
//
// Log sources (priority order):
//   1. data/logs/error.log        — structured JSON-lines (ERROR/CRITICAL only)
//                                   Created automatically on first failed render.
//   2. data/logs/app.log          — structured JSON-lines (all render events)
//                                   Created automatically on first render.
//   3. data/logs/desktop-backend.log — raw backend stdout/stderr piped by Electron.
//                                   Always present after first backend start.
//
// Usage:
//   npm run logerror              Print error entries (structured or raw fallback)
//   npm run logerror -- --list   Show all log files with sizes and status
'use strict';

const fs   = require('fs');
const path = require('path');

// Respect APP_DATA_DIR env (set by Electron's startBackendWithCommand).
// Falls back to project-root/data for dev / direct npm usage.
const DATA_DIR = process.env.APP_DATA_DIR
  ? path.resolve(process.env.APP_DATA_DIR)
  : path.resolve(__dirname, '..', '..', 'data');

const LOGS_DIR    = path.join(DATA_DIR, 'logs');
const ERROR_LOG   = path.join(LOGS_DIR, 'error.log');
const APP_LOG     = path.join(LOGS_DIR, 'app.log');
const BACKEND_LOG = path.join(LOGS_DIR, 'desktop-backend.log');

// ── helpers ───────────────────────────────────────────────────────────────────

function fileSizeLabel(filePath) {
  try {
    const bytes = fs.statSync(filePath).size;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  } catch { return 'unknown'; }
}

function printJsonLine(line) {
  try {
    const e = JSON.parse(line);
    const parts = [
      `[${e.timestamp || ''}]`,
      `[${e.level || 'ERROR'}]`,
      e.error_code ? `[${e.error_code}]` : null,
      `[${e.event  || ''}]`,
      e.message || '',
      e.job_id     ? `job=${e.job_id.slice(0, 8)}` : null,
      e.exception  ? `| ${e.exception}` : null,
    ].filter(Boolean);
    console.log(parts.join(' '));
  } catch {
    console.log(line);
  }
}

// ── --list ────────────────────────────────────────────────────────────────────

function runList() {
  console.log(`Log directory: ${LOGS_DIR}\n`);

  const files = [
    {
      label: 'error.log',
      note:  'Structured JSON errors (ERROR/CRITICAL). Created on first failed render.',
      file:  ERROR_LOG,
    },
    {
      label: 'app.log',
      note:  'All structured render events. Created on first render job.',
      file:  APP_LOG,
    },
    {
      label: 'desktop-backend.log',
      note:  'Raw backend stdout/stderr. Written by Electron on every start.',
      file:  BACKEND_LOG,
    },
  ];

  let existCount = 0;
  for (const { label, note, file } of files) {
    if (fs.existsSync(file)) {
      console.log(`  [exists]  ${label}  (${fileSizeLabel(file)})`);
      console.log(`            ${note}`);
      console.log(`            ${file}`);
      existCount++;
    } else {
      console.log(`  [missing] ${label}`);
      console.log(`            ${note}`);
    }
    console.log('');
  }

  // Per-job logs under channels/
  const channelsRoot = path.resolve(DATA_DIR, '..', 'channels');
  if (fs.existsSync(channelsRoot)) {
    let jobLogs = 0;
    try {
      for (const ch of fs.readdirSync(channelsRoot)) {
        const chLogsDir = path.join(channelsRoot, ch, 'logs');
        if (!fs.existsSync(chLogsDir)) continue;
        jobLogs += fs.readdirSync(chLogsDir).filter(f => f.endsWith('.log')).length;
      }
    } catch { /* ignore permission errors */ }
    if (jobLogs > 0) {
      console.log(`  Per-job logs: ${jobLogs} file(s) in channels/*/logs/`);
      console.log(`                (written per render job alongside structured events)`);
      console.log('');
    }
  }

  if (existCount === 0) {
    console.log('No log files found. Start the backend to generate desktop-backend.log.');
    console.log('Run a render job to generate app.log and error.log.');
  } else if (!fs.existsSync(ERROR_LOG) && !fs.existsSync(APP_LOG)) {
    console.log('Note: error.log and app.log are absent because no render job has run');
    console.log('      since structured logging was added (commit ea0326f, Apr 15 2026).');
    console.log('      They will be created automatically on the next render.');
  }
}

// ── main ──────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);

if (args.includes('--list')) {
  runList();
  process.exit(0);
}

// 1. Structured error log (preferred — exists after first failed render)
if (fs.existsSync(ERROR_LOG)) {
  const content = fs.readFileSync(ERROR_LOG, 'utf8').trim();
  if (!content) {
    console.log('error.log exists but contains no entries.');
    process.exit(0);
  }
  const lines = content.split('\n').filter(Boolean);
  lines.forEach(printJsonLine);
  console.log(`\n--- ${lines.length} error(s) in ${ERROR_LOG} ---`);
  process.exit(0);
}

// 2. Fallback: scan desktop-backend.log for error lines.
//    Split on \r and \n — yt-dlp uses \r-only progress lines which produce
//    multi-MB "lines" when split on \n alone.  Filtering noise patterns avoids
//    download progress lines that incidentally match "error" substrings.
if (fs.existsSync(BACKEND_LOG)) {
  console.log('error.log not found (no failed renders since structured logging was added).');
  console.log(`Falling back to ${BACKEND_LOG}\n`);

  const content = fs.readFileSync(BACKEND_LOG, 'utf8');
  const ERROR_PAT = /\b(ERROR|CRITICAL|Traceback|Exception:|raise |error:)\b/;
  const NOISE_PAT = /^\[download\]|^\[ffmpeg\]|^\[info\]|^\s*\d+\.\d+%/;

  const errorLines = content
    .split(/[\r\n]+/)
    .map(l => l.trim())
    .filter(l => l.length > 0 && ERROR_PAT.test(l) && !NOISE_PAT.test(l));

  if (!errorLines.length) {
    console.log('No error lines found in desktop-backend.log.');
    console.log('The backend has run cleanly — no errors recorded.');
  } else {
    errorLines.forEach(l => console.log(l));
    console.log(`\n--- ${errorLines.length} line(s) matched in ${BACKEND_LOG} ---`);
    console.log('(Raw text fallback. Structured error.log will appear after the first failed render.)');
  }
  process.exit(0);
}

// 3. Nothing at all
console.log('No log files found.');
console.log(`Expected log directory: ${LOGS_DIR}`);
console.log('Start the backend to generate desktop-backend.log.');
console.log('Run a render job to generate app.log and error.log.');
console.log('\nRun "npm run logerror -- --list" to inspect available log files.');
process.exit(0);
