/**
 * doc-loader.ts
 *
 * Loads project documentation files and assembles them into a
 * context string for use in prompts. Handles missing files gracefully
 * with a warning rather than a crash — docs evolve over time.
 */

import fs from 'fs-extra';
import path from 'path';
import type { PipelineConfig } from './types.js';

export interface LoadedDoc {
  path: string;
  content: string;
  loaded: boolean;
  error?: string;
}

/**
 * Loads a single doc file by relative path from project root.
 */
export async function loadDoc(relativePath: string): Promise<LoadedDoc> {
  const fullPath = path.resolve(process.cwd(), relativePath);
  try {
    const content = await fs.readFile(fullPath, 'utf-8');
    return { path: relativePath, content, loaded: true };
  } catch {
    return {
      path: relativePath,
      content: '',
      loaded: false,
      error: `File not found: ${relativePath}`,
    };
  }
}

/**
 * Loads all doc files listed in config.doc_paths.
 * Returns an array of LoadedDoc — never throws.
 */
export async function loadConfiguredDocs(
  config: Pick<PipelineConfig, 'doc_paths'>
): Promise<LoadedDoc[]> {
  return Promise.all(config.doc_paths.map((p) => loadDoc(p)));
}

/**
 * Loads a specific list of doc paths (e.g. from normalized task's
 * project_context_needed field).
 */
export async function loadProjectContextDocs(docPaths: string[]): Promise<LoadedDoc[]> {
  return Promise.all(docPaths.map((p) => loadDoc(p)));
}

/**
 * Assembles loaded docs into a single markdown context string
 * suitable for inclusion in a prompt.
 */
export function assembleDocContext(docs: LoadedDoc[]): string {
  const loaded = docs.filter((d) => d.loaded);
  const failed = docs.filter((d) => !d.loaded);

  const sections = loaded.map(
    (d) => `### ${d.path}\n\n${d.content.trim()}`
  );

  const warnings =
    failed.length > 0
      ? `\n\n> **Missing docs (not loaded):** ${failed.map((d) => d.path).join(', ')}`
      : '';

  return sections.join('\n\n---\n\n') + warnings;
}

/**
 * One-call helper: loads all configured docs and assembles them into
 * a context string.
 */
export async function buildDocContext(
  config: Pick<PipelineConfig, 'doc_paths'>
): Promise<string> {
  const docs = await loadConfiguredDocs(config);
  return assembleDocContext(docs);
}
