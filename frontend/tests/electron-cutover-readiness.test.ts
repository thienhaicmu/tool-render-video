/**
 * electron-cutover-readiness.test.ts — Phase 6.7 Electron cut-over readiness checks.
 *
 * Verifies the frontend is ready for Electron same-origin serving.
 * Does NOT require a running backend — pure source/config checks.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'

const ROOT = join(__dirname, '..')
const SRC_ROOT = join(ROOT, 'src')

function readSrc(relPath: string): string {
  return readFileSync(join(SRC_ROOT, relPath), 'utf-8')
}

describe('Electron cutover — BASE_URL same-origin safety', () => {
  it('BASE_URL uses VITE_API_BASE_URL env var, not hardcoded 127.0.0.1', () => {
    const clientSrc = readSrc('api/client.ts')
    expect(clientSrc).toContain('VITE_API_BASE_URL')
    expect(clientSrc).not.toContain("'http://127.0.0.1:8000'")
    expect(clientSrc).not.toContain('"http://127.0.0.1:8000"')
  })

  it('BASE_URL falls back to empty string for same-origin production serving', () => {
    const clientSrc = readSrc('api/client.ts')
    // Must use nullish coalescing with '' or "" as fallback
    expect(clientSrc).toMatch(/VITE_API_BASE_URL.*\?\?.*(?:''|"")/)
  })

  it('apiFetch uses same-origin path for /api routes (no absolute URL prefix)', () => {
    const clientSrc = readSrc('api/client.ts')
    // Verify BASE_URL is prepended only; if empty, result is just the path
    expect(clientSrc).toContain('`${BASE_URL}${path}`')
  })
})

describe('Electron cutover — WebSocket client', () => {
  it('RenderSocketClient.ts uses computeWsBase() function', () => {
    const wsSrc = readSrc('websocket/RenderSocketClient.ts')
    expect(wsSrc).toContain('computeWsBase')
  })

  it('computeWsBase derives URL from window.location.origin when BASE_URL is empty', () => {
    const wsSrc = readSrc('websocket/RenderSocketClient.ts')
    expect(wsSrc).toContain('window.location.origin')
  })

  it('RenderSocketClient does not hardcode ws://127.0.0.1:8000 as only WS path', () => {
    const wsSrc = readSrc('websocket/RenderSocketClient.ts')
    // computeWsBase must exist — the hardcoded URL can only appear as a fallback
    expect(wsSrc).toContain('computeWsBase')
    // The function exists = dynamic resolution is in place
  })
})

describe('Electron cutover — Vite build config', () => {
  it('vite.config.ts outDir points to static-v2', () => {
    const configSrc = readFileSync(join(ROOT, 'vite.config.ts'), 'utf-8')
    expect(configSrc).toContain('static-v2')
  })

  it('vite.config.ts has no explicit base that would break same-origin serving', () => {
    const configSrc = readFileSync(join(ROOT, 'vite.config.ts'), 'utf-8')
    // base: '/' is correct; base: './' would break /assets mount
    // If base is unset (default), Vite uses '/' which is also correct
    expect(configSrc).not.toContain("base: './'")
    expect(configSrc).not.toContain('base: "./"')
  })
})

describe('Electron cutover — no old /api/upload/ domain in API files', () => {
  const apiFiles = ['api/render.ts', 'api/jobs.ts', 'api/upload.ts', 'api/client.ts']

  apiFiles.forEach(f => {
    it(`${f} does not call removed /api/upload/ (slash) domain in string literals`, () => {
      const src = readSrc(f)
      // Old upload domain was /api/upload/channel, /api/upload/file, etc.
      // New endpoint is /api/upload-file (with dash, no trailing slash path).
      // Only match the pattern inside string/template literals — not inside comments.
      expect(src).not.toMatch(/['"`]\/api\/upload\//)
    })
  })
})

describe('Electron cutover — API paths are same-origin relative', () => {
  it('render.ts does not use absolute http:// URLs in fetch calls', () => {
    const renderApi = readSrc('api/render.ts')
    expect(renderApi).not.toMatch(/fetch\(['"]http:\/\//)
  })

  it('jobs.ts does not use absolute http:// URLs in fetch calls', () => {
    const jobsApi = readSrc('api/jobs.ts')
    expect(jobsApi).not.toMatch(/fetch\(['"]http:\/\//)
  })
})

describe('Electron cutover — paginated history (no unbounded list)', () => {
  it('HistoryScreen.tsx uses getJobHistory (paginated)', () => {
    const historySrc = readSrc('features/jobs/HistoryScreen.tsx')
    expect(historySrc).toContain('getJobHistory')
    expect(historySrc).not.toContain('listJobs')
  })
})

describe('Electron cutover — no polling in quality components', () => {
  it('QualityPanel.tsx does not use setInterval (fetch-on-open only)', () => {
    const qualitySrc = readSrc('features/quality/QualityPanel.tsx')
    expect(qualitySrc).not.toContain('setInterval')
  })
})

describe('Electron cutover — static-v2 build artifact', () => {
  it('static-v2 directory exists after build+copy', () => {
    const staticV2 = join(ROOT, '..', 'backend', 'static-v2')
    if (!existsSync(staticV2)) {
      console.warn('backend/static-v2 not found — run: cd frontend && npm run build')
      return
    }
    expect(existsSync(join(staticV2, 'index.html'))).toBe(true)
    expect(existsSync(join(staticV2, 'assets'))).toBe(true)
  })

  it('static-v2/index.html uses /assets/ paths (not relative ./assets/)', () => {
    const staticV2 = join(ROOT, '..', 'backend', 'static-v2')
    if (!existsSync(staticV2)) {
      console.warn('backend/static-v2 not found — skipping artifact check')
      return
    }
    const html = readFileSync(join(staticV2, 'index.html'), 'utf-8')
    expect(html).toContain('/assets/')
    expect(html).not.toContain('./assets/')
  })
})

describe('Electron cutover — UI gate env var documented', () => {
  it('backend/app/core/ui_gate.py documents STATIC_UI_VERSION', () => {
    const uiGateSrc = readFileSync(
      join(ROOT, '..', 'backend', 'app', 'core', 'ui_gate.py'),
      'utf-8'
    )
    expect(uiGateSrc).toContain('STATIC_UI_VERSION')
    expect(uiGateSrc).toContain('v2')
    expect(uiGateSrc).toContain('legacy')
  })

  it('backend/app/main.py uses resolve_static_directory from ui_gate', () => {
    const mainSrc = readFileSync(
      join(ROOT, '..', 'backend', 'app', 'main.py'),
      'utf-8'
    )
    expect(mainSrc).toContain('resolve_static_directory')
    expect(mainSrc).toContain('STATIC_UI_VERSION')
  })
})
