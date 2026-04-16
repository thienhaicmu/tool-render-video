/**
 * prompt-loader.ts
 *
 * Loads prompt files from the prompts/ directory.
 * Supports caching to avoid redundant disk reads.
 */

import fs from 'fs-extra';
import path from 'path';

// ── Cache ─────────────────────────────────────────────────────────────────────

const promptCache = new Map<string, string>();

// ── Loader ────────────────────────────────────────────────────────────────────

/**
 * Loads a prompt file from the prompts/ directory.
 * Path should be relative to prompts/, e.g. 'system/claude-cowork-system.md'
 */
export async function loadPrompt(relativePath: string): Promise<string> {
  if (promptCache.has(relativePath)) {
    return promptCache.get(relativePath)!;
  }

  const fullPath = path.resolve(process.cwd(), 'prompts', relativePath);

  try {
    const content = await fs.readFile(fullPath, 'utf-8');
    promptCache.set(relativePath, content);
    return content;
  } catch (err) {
    throw new Error(`Failed to load prompt: ${relativePath} (${fullPath})\n${String(err)}`);
  }
}

// ── Convenience loaders ───────────────────────────────────────────────────────

export async function loadSystemPrompt(name: string): Promise<string> {
  return loadPrompt(`system/${name}.md`);
}

export async function loadTemplate(name: string): Promise<string> {
  return loadPrompt(`templates/${name}.md`);
}

export async function loadFewShots(name: string): Promise<string> {
  return loadPrompt(`fewshots/${name}.md`);
}

/**
 * Renders a template by replacing {{KEY}} placeholders with values.
 */
export function renderTemplate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => {
    if (key in vars) return vars[key];
    // Return the original placeholder if no value provided — makes gaps visible
    return `{{${key}}}`;
  });
}

/**
 * Clears the prompt cache. Useful for testing.
 */
export function clearPromptCache(): void {
  promptCache.clear();
}
