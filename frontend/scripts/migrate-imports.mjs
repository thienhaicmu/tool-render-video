#!/usr/bin/env node
/**
 * migrate-imports.mjs — convert deep relative imports to `@/...` alias form.
 *
 * Sprint 9 (audit followup_2): the @/* alias was declared in
 * tsconfig.app.json since project init but never used. This codemod
 * rewrites every `from '../../X'` or deeper into `from '@/X'`, calculating
 * the absolute-from-src path based on each file's own location.
 *
 * Scope: 2+ level relative imports only (`../../X` and deeper). Single
 * `../X` imports are left alone — they typically reach a peer module
 * inside the same feature folder, and the relative form documents that
 * locality better than the alias.
 *
 * Targets: every .ts / .tsx under frontend/src/.
 *
 * Dry-run by default. Pass `--write` to actually edit files.
 *
 * Usage:
 *   node scripts/migrate-imports.mjs           # dry run
 *   node scripts/migrate-imports.mjs --write   # commit changes
 */
import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(__dirname, '..', 'src')
const WRITE = process.argv.includes('--write')

/** Recursively walk a directory, yielding all .ts / .tsx file paths. */
function* walk(root) {
  for (const name of readdirSync(root)) {
    const full = join(root, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      yield* walk(full)
    } else if (st.isFile() && /\.(tsx?|mts|cts)$/.test(name)) {
      yield full
    }
  }
}

const IMPORT_RE = /(\bfrom\s+['"]|\bimport\s*\(\s*['"]|\brequire\s*\(\s*['"])(\.\.\/(?:\.\.\/)+[^'"]+)(['"])/g

let filesChanged = 0
let edits = 0

for (const file of walk(SRC)) {
  const original = readFileSync(file, 'utf8')
  const fileDir = dirname(file)
  let modified = false

  const next = original.replace(IMPORT_RE, (full, prefix, importPath, suffix) => {
    // Resolve the import path relative to the importing file's directory.
    const absTarget = resolve(fileDir, importPath)
    // Compute the path relative to SRC.
    const fromSrc = relative(SRC, absTarget)
    // If the target escapes SRC, leave it alone.
    if (fromSrc.startsWith('..')) return full
    // Normalize path separators for cross-platform.
    const aliased = `@/${fromSrc.split(/[\\/]/).join('/')}`
    edits += 1
    modified = true
    return `${prefix}${aliased}${suffix}`
  })

  if (modified) {
    filesChanged += 1
    if (WRITE) {
      writeFileSync(file, next, 'utf8')
    }
    const rel = relative(resolve(__dirname, '..'), file).split(/[\\/]/).join('/')
    console.log(`${WRITE ? 'edited' : 'would edit'}: ${rel}`)
  }
}

console.log(`\n${WRITE ? 'Updated' : 'Would update'} ${edits} import(s) in ${filesChanged} file(s).`)
if (!WRITE) console.log('Re-run with --write to apply.')
