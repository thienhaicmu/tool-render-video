#!/usr/bin/env node
/**
 * run-python.mjs — invoke a Python script using the backend venv if
 * available, falling back to system `python` otherwise.
 *
 * Sprint 5.1: needed by the gen:openapi npm script. Locally the developer
 * runs in their backend venv where fastapi/pydantic are installed; in CI
 * fastapi is installed against the system Python via
 * `pip install -r backend/requirements.txt`. This wrapper bridges both.
 *
 * Usage: node scripts/run-python.mjs <path-to-script> [args...]
 */
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
// frontend/scripts → frontend → repo root → backend
const REPO_ROOT = resolve(__dirname, '..', '..')
const BACKEND = resolve(REPO_ROOT, 'backend')

const VENV_CANDIDATES = [
  resolve(BACKEND, '.venv', 'Scripts', 'python.exe'),  // Windows venv
  resolve(BACKEND, '.venv', 'bin', 'python'),          // POSIX venv
  resolve(BACKEND, '.venv', 'bin', 'python3'),         // POSIX venv (rare)
]

function pickPython() {
  for (const candidate of VENV_CANDIDATES) {
    if (existsSync(candidate)) return candidate
  }
  // Fall back to whatever `python` is on PATH (typical in CI after
  // actions/setup-python). On systems without `python`, the spawn will
  // surface its own ENOENT — clearer than us guessing further.
  return 'python'
}

const [, , scriptPath, ...rest] = process.argv
if (!scriptPath) {
  console.error('usage: run-python.mjs <script.py> [args...]')
  process.exit(2)
}

const python = pickPython()
const result = spawnSync(python, [scriptPath, ...rest], { stdio: 'inherit' })
if (result.error) {
  console.error(`failed to spawn ${python}: ${result.error.message}`)
  process.exit(127)
}
process.exit(result.status ?? 0)
