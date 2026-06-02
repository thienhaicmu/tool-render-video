/**
 * static-readiness.test.ts — Phase 6.6 static build readiness checks.
 *
 * Tests:
 * - BASE_URL uses import.meta.env.VITE_API_BASE_URL, not hardcoded 127.0.0.1
 * - vite.config.ts outDir points to static-v2
 * - No /api/upload/* (old domain) in any src file
 * - getJobHistory is used in history (paginated, not unbounded)
 * - STATIC_UI_VERSION env var is documented in backend
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const SRC_DIR = join(__dirname, '../src')
const ROOT_DIR = join(__dirname, '../..')

function readSrc(relPath: string): string {
  return readFileSync(join(SRC_DIR, relPath), 'utf-8')
}

function readRoot(relPath: string): string {
  return readFileSync(join(ROOT_DIR, relPath), 'utf-8')
}

// ── BASE_URL env-awareness ────────────────────────────────────────────────────

describe('static-readiness — BASE_URL', () => {
  it('client.ts uses import.meta.env.VITE_API_BASE_URL', () => {
    const content = readSrc('api/client.ts')
    expect(content).toContain('import.meta.env.VITE_API_BASE_URL')
  })

  it('client.ts does NOT hardcode http://127.0.0.1:8000 as BASE_URL value', () => {
    const content = readSrc('api/client.ts')
    // The hardcoded assignment must not appear
    expect(content).not.toContain("export const BASE_URL = 'http://127.0.0.1:8000'")
    expect(content).not.toContain('export const BASE_URL = "http://127.0.0.1:8000"')
  })

  it('BASE_URL falls back to empty string (same-origin) when env var absent', () => {
    const content = readSrc('api/client.ts')
    // Must use nullish coalescing with '' as fallback
    expect(content).toMatch(/VITE_API_BASE_URL\s*\?\?\s*['"]''|VITE_API_BASE_URL\s*\?\?\s*''/)
    // More flexible: just check that ?? '' is present after the env var
    expect(content).toMatch(/VITE_API_BASE_URL.*\?\?.*''|VITE_API_BASE_URL.*\?\?.*""/)
  })
})

// ── WebSocket URL safety ──────────────────────────────────────────────────────

describe('static-readiness — WebSocket URL', () => {
  it('RenderSocketClient.ts uses computeWsBase() function', () => {
    const content = readSrc('websocket/RenderSocketClient.ts')
    expect(content).toContain('computeWsBase')
  })

  it('RenderSocketClient.ts falls back to window.location.origin when BASE_URL is empty', () => {
    const content = readSrc('websocket/RenderSocketClient.ts')
    expect(content).toContain('window.location.origin')
  })

  it('RenderSocketClient.ts has SSR/test fallback to ws://127.0.0.1:8000', () => {
    const content = readSrc('websocket/RenderSocketClient.ts')
    expect(content).toContain('ws://127.0.0.1:8000')
  })
})

// ── Vite build config ─────────────────────────────────────────────────────────

describe('static-readiness — vite.config.ts', () => {
  it('outDir points to ../backend/static-v2', () => {
    const content = readFileSync(join(__dirname, '../vite.config.ts'), 'utf-8')
    expect(content).toContain('static-v2')
  })

  it('has /api proxy pointing to 127.0.0.1:8000', () => {
    const content = readFileSync(join(__dirname, '../vite.config.ts'), 'utf-8')
    expect(content).toContain('/api')
    expect(content).toContain('127.0.0.1:8000')
  })
})

// ── Old upload domain audit ───────────────────────────────────────────────────

describe('static-readiness — no old /api/upload/ domain', () => {
  it('upload.ts does not use /api/upload/ (slash domain)', () => {
    const content = readSrc('api/upload.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })

  it('render.ts does not use /api/upload/ domain', () => {
    const content = readSrc('api/render.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })

  it('jobs.ts does not use /api/upload/ domain', () => {
    const content = readSrc('api/jobs.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })
})

// ── getJobHistory usage ───────────────────────────────────────────────────────

describe('static-readiness — getJobHistory usage', () => {
  it('HistoryScreen.tsx uses getJobHistory (paginated)', () => {
    const content = readSrc('features/jobs/HistoryScreen.tsx')
    expect(content).toContain('getJobHistory')
  })

  it('api/jobs.ts exports getJobHistory', () => {
    const content = readSrc('api/jobs.ts')
    expect(content).toContain('getJobHistory')
  })
})

// ── STATIC_UI_VERSION documented in backend ───────────────────────────────────

describe('static-readiness — STATIC_UI_VERSION', () => {
  it('ui_gate.py documents STATIC_UI_VERSION env var', () => {
    const content = readRoot('backend/app/core/ui_gate.py')
    expect(content).toContain('STATIC_UI_VERSION')
  })

  it('main.py uses resolve_static_directory from ui_gate', () => {
    const content = readRoot('backend/app/main.py')
    expect(content).toContain('resolve_static_directory')
  })

  it('main.py documents STATIC_UI_VERSION=v2 activates static-v2', () => {
    const content = readRoot('backend/app/main.py')
    expect(content).toContain('STATIC_UI_VERSION')
  })
})

// ── .gitignore covers build artifacts ────────────────────────────────────────

describe('static-readiness — .gitignore', () => {
  it('frontend/.gitignore ignores *.tsbuildinfo', () => {
    const content = readFileSync(join(__dirname, '../.gitignore'), 'utf-8')
    expect(content).toContain('*.tsbuildinfo')
  })
})
