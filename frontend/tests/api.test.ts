/**
 * API layer tests
 * - ApiError class
 * - upload function uses /api/upload-file (not /api/upload/*)
 * - old /api/upload/ path is not present in any api/*.ts file
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { ApiError } from '../src/api/client'

describe('ApiError', () => {
  it('should construct with status and detail', () => {
    const err = new ApiError(404, 'Not found')
    expect(err.status).toBe(404)
    expect(err.detail).toBe('Not found')
    expect(err.name).toBe('ApiError')
    expect(err instanceof Error).toBe(true)
    expect(err instanceof ApiError).toBe(true)
  })

  it('should use provided message when given', () => {
    const err = new ApiError(422, { detail: [{ loc: [], msg: 'invalid' }] }, 'Validation failed')
    expect(err.message).toBe('Validation failed')
    expect(err.status).toBe(422)
  })

  it('should auto-generate message from status + detail when no message provided', () => {
    const err = new ApiError(500, 'Internal server error')
    expect(err.message).toContain('500')
  })

  it('should be catchable as a specific type', () => {
    let caught: ApiError | null = null
    try {
      throw new ApiError(403, 'Forbidden')
    } catch (e) {
      if (e instanceof ApiError) caught = e
    }
    expect(caught).not.toBeNull()
    expect(caught?.status).toBe(403)
  })
})

// ── Upload file path audit ────────────────────────────────────────────────────

const API_DIR = join(__dirname, '../src/api')

function readApiFile(filename: string): string {
  return readFileSync(join(API_DIR, filename), 'utf-8')
}

describe('upload API — path audit', () => {
  it('upload.ts uses /api/upload-file (hyphen form)', () => {
    const content = readApiFile('upload.ts')
    expect(content).toContain('/api/upload-file')
  })

  it('upload.ts does NOT call /api/upload/ (old slash domain)', () => {
    const content = readApiFile('upload.ts')
    // The pattern /api/upload/ should only appear in comments (DO NOT USE), not in actual fetch calls
    // We check the actual code doesn't have fetch('/api/upload/...')
    const lines = content.split('\n').filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*'))
    const hasBadPath = lines.some((line) => line.includes("'/api/upload/'") || line.includes('"/api/upload/"') || line.includes('`/api/upload/`'))
    expect(hasBadPath).toBe(false)
  })

  it('render.ts does NOT reference /api/upload/', () => {
    const content = readApiFile('render.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })

  it('jobs.ts does NOT reference /api/upload/', () => {
    const content = readApiFile('jobs.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })

  it('client.ts does NOT reference /api/upload/', () => {
    const content = readApiFile('client.ts')
    expect(content).not.toMatch(/['"`]\/api\/upload\//)
  })
})

// ── Upload endpoint name correctness ─────────────────────────────────────────

describe('upload API — endpoint correctness', () => {
  it('upload.ts exports uploadFile function', () => {
    const content = readApiFile('upload.ts')
    expect(content).toContain('export async function uploadFile')
  })

  it('upload.ts uses FormData field "file"', () => {
    const content = readApiFile('upload.ts')
    expect(content).toContain("form.append('file', file)")
  })
})
