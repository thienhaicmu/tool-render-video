/**
 * schema.ts
 *
 * Ajv-based JSON schema validation utilities.
 * All pipeline stages that produce or consume structured data
 * must validate against the appropriate schema before proceeding.
 */

// Ajv ships as CJS; under NodeNext ESM we must use the .default export.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const AjvModule = await import('ajv');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const addFormatsModule = await import('ajv-formats');

// Handle both CJS default export and direct export shapes
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AjvCtor = (AjvModule as any).default ?? AjvModule;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const addFormats = (addFormatsModule as any).default ?? addFormatsModule;

import type { ValidateFunction, AnySchema } from 'ajv';
import fs from 'fs-extra';
import path from 'path';

// ── Ajv singleton ─────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ajv = new (AjvCtor as any)({
  allErrors: true,        // Report all errors, not just the first
  strict: true,           // Disallow unknown keywords
  strictSchema: true,
  strictTypes: true,
  removeAdditional: false,// Never silently strip data
});

addFormats(ajv);

// ── Schema cache ──────────────────────────────────────────────────────────────

const schemaCache = new Map<string, ValidateFunction>();

/**
 * Creates and caches a compiled validator from a raw schema object.
 */
export function createValidator(schema: AnySchema): ValidateFunction {
  const id = typeof schema === 'object' && schema !== null && '$id' in schema
    ? String((schema as Record<string, unknown>)['$id'])
    : JSON.stringify(schema).slice(0, 64);

  if (!schemaCache.has(id)) {
    schemaCache.set(id, ajv.compile(schema));
  }

  return schemaCache.get(id)!;
}

/**
 * Loads a schema by filename from the schemas/ directory, then compiles it.
 * Caches compiled validators.
 */
export async function loadValidator(schemaFile: string): Promise<ValidateFunction> {
  if (schemaCache.has(schemaFile)) {
    return schemaCache.get(schemaFile)!;
  }

  const schemaPath = path.resolve(process.cwd(), 'schemas', schemaFile);
  const raw = await fs.readFile(schemaPath, 'utf-8');
  const schema = JSON.parse(raw);
  const validator = ajv.compile(schema);

  schemaCache.set(schemaFile, validator);
  return validator;
}

// ── Typed validation helpers ──────────────────────────────────────────────────

export interface ValidationResult<T> {
  valid: boolean;
  data?: T;
  errors?: Array<{ path: string; message: string }>;
}

/**
 * Validates data against a named schema file.
 * Returns a typed ValidationResult.
 */
export async function validate<T>(
  schemaFile: string,
  data: unknown
): Promise<ValidationResult<T>> {
  const validator = await loadValidator(schemaFile);
  const valid = validator(data);

  if (valid) {
    return { valid: true, data: data as T };
  }

  const errors = (validator.errors ?? []).map((e) => ({
    path: e.instancePath || '(root)',
    message: e.message ?? 'Unknown validation error',
  }));

  return { valid: false, errors };
}

/**
 * Validates data and throws a descriptive error on failure.
 * Use for fail-fast validation at pipeline stage boundaries.
 */
export async function validateOrThrow<T>(
  schemaFile: string,
  data: unknown,
  context?: string
): Promise<T> {
  const result = await validate<T>(schemaFile, data);

  if (!result.valid) {
    const prefix = context ? `[${context}] ` : '';
    const detail = (result.errors ?? [])
      .map((e) => `  ${e.path}: ${e.message}`)
      .join('\n');
    throw new Error(`${prefix}Schema validation failed for ${schemaFile}:\n${detail}`);
  }

  return result.data!;
}
