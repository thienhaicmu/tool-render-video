#!/usr/bin/env node
// Reads data/logs/error.log (JSON-lines) and prints formatted render error entries.
'use strict';

const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, '..', '..', 'data', 'logs', 'error.log');

if (!fs.existsSync(LOG_FILE)) {
  console.log('No error log found at:', LOG_FILE);
  process.exit(0);
}

const content = fs.readFileSync(LOG_FILE, 'utf8').trim();
if (!content) {
  console.log('Error log is empty.');
  process.exit(0);
}

const lines = content.split('\n').filter(Boolean);
lines.forEach(line => {
  try {
    const e = JSON.parse(line);
    const parts = [
      `[${e.timestamp || ''}]`,
      `[${e.level || 'ERROR'}]`,
      e.error_code ? `[${e.error_code}]` : null,
      `[${e.event || ''}]`,
      e.message || '',
      e.job_id ? `job=${e.job_id.slice(0, 8)}` : null,
      e.exception ? `| ${e.exception}` : null,
    ].filter(Boolean);
    console.log(parts.join(' '));
  } catch {
    console.log(line);
  }
});

console.log(`\n--- ${lines.length} error(s) in ${LOG_FILE} ---`);
