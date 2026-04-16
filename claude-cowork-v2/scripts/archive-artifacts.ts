/**
 * archive-artifacts.ts
 *
 * Archives all artifacts for a pipeline run into a single, self-contained
 * directory: artifacts/<task_id>/<run_id>/
 *
 * Produces an artifact-manifest.json that indexes every file in the bundle
 * and records checksums, sizes, and retention expiry.
 *
 * The artifact bundle is the authoritative record of a pipeline run.
 * All source files (normalized task, execution result, review, summary)
 * are copied here for durability — even if the originals are pruned.
 */

import fs from 'fs-extra';
import path from 'path';
import crypto from 'crypto';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { validateOrThrow } from './schema.js';
import { nowIso } from './ids.js';
import type {
  NormalizedPrompt,
  ExecutionResult,
  ReviewReport,
  ArtifactManifest,
  ArtifactFile,
  PipelineStatus,
} from './types.js';

// ── File utilities ────────────────────────────────────────────────────────────

async function sha256File(filePath: string): Promise<string> {
  try {
    const content = await fs.readFile(filePath);
    return crypto.createHash('sha256').update(content).digest('hex');
  } catch {
    return '(unreadable)';
  }
}

async function fileSizeBytes(filePath: string): Promise<number> {
  try {
    const stat = await fs.stat(filePath);
    return stat.size;
  } catch {
    return 0;
  }
}

async function copyIfExists(src: string, dest: string): Promise<boolean> {
  try {
    await fs.copy(src, dest, { overwrite: true });
    return true;
  } catch {
    return false;
  }
}

// ── Archive builder ───────────────────────────────────────────────────────────

interface ArchiveInput {
  normalized: NormalizedPrompt;
  result: ExecutionResult;
  review: ReviewReport;
  final_summary_md: string;
  pipeline_status: PipelineStatus;
}

export async function archiveArtifacts(input: ArchiveInput): Promise<ArtifactManifest> {
  const config = await loadConfig();
  const { normalized, result, review, final_summary_md, pipeline_status } = input;

  const logger = createLogger('archive-artifacts', config, {
    task_id: normalized.task_id,
    run_id: result.run_id,
    session_id: result.session_id,
  });

  logger.info('Archiving artifacts', {
    task_id: normalized.task_id,
    run_id: result.run_id,
  });

  // Create artifact directory
  const artifactDir = path.resolve(
    process.cwd(),
    config.artifact_root,
    normalized.task_id,
    result.run_id
  );
  await fs.ensureDir(artifactDir);

  const files: ArtifactFile[] = [];

  // ── Helper to register a file in the manifest ───────────────────────────────
  async function registerFile(
    destName: string,
    type: ArtifactFile['type'],
    content?: string
  ): Promise<void> {
    const destPath = path.join(artifactDir, destName);

    if (content !== undefined) {
      // Write inline content
      await fs.writeFile(destPath, content, 'utf-8');
    }

    if (await fs.pathExists(destPath)) {
      files.push({
        name: destName,
        path: path.relative(process.cwd(), destPath),
        type,
        size_bytes: await fileSizeBytes(destPath),
        sha256: await sha256File(destPath),
      });
    }
  }

  // ── 1. Raw prompt ───────────────────────────────────────────────────────────
  const rawTaskPath = path.resolve(
    process.cwd(),
    config.tasks_root,
    'incoming',
    `${normalized.task_id}.json`
  );
  const rawTaskDest = path.join(artifactDir, 'raw-prompt.json');
  await copyIfExists(rawTaskPath, rawTaskDest);
  await registerFile('raw-prompt.json', 'raw-prompt');

  // ── 2. Normalized prompt ────────────────────────────────────────────────────
  await registerFile(
    'normalized-prompt.json',
    'normalized-prompt',
    JSON.stringify(normalized, null, 2)
  );

  // ── 3. Task pack ────────────────────────────────────────────────────────────
  const taskPackSrc = path.resolve(
    process.cwd(),
    config.tasks_root,
    'taskpacks',
    `${normalized.task_id}.md`
  );
  const taskPackDest = path.join(artifactDir, 'task-pack.md');
  await copyIfExists(taskPackSrc, taskPackDest);
  await registerFile('task-pack.md', 'task-pack');

  // ── 4. Execution result ─────────────────────────────────────────────────────
  await registerFile(
    'execution-result.json',
    'execution-result',
    JSON.stringify(result, null, 2)
  );

  // ── 5. stdout / stderr ──────────────────────────────────────────────────────
  if (result.stdout_path) {
    const stdoutDest = path.join(artifactDir, 'stdout.txt');
    await copyIfExists(result.stdout_path, stdoutDest);
    await registerFile('stdout.txt', 'stdout');
  }

  if (result.stderr_path) {
    const stderrDest = path.join(artifactDir, 'stderr.txt');
    await copyIfExists(result.stderr_path, stderrDest);
    await registerFile('stderr.txt', 'stderr');
  }

  // ── 6. Review report ────────────────────────────────────────────────────────
  await registerFile(
    'review-report.json',
    'review-report',
    JSON.stringify(review, null, 2)
  );

  // ── 7. Final summary ────────────────────────────────────────────────────────
  await registerFile('final-summary.md', 'final-summary', final_summary_md);

  // ── 8. Logs index ───────────────────────────────────────────────────────────
  const eventLogPath = path.resolve(
    process.cwd(),
    config.logs_root,
    'events',
    `${normalized.task_id}-events.ndjson`
  );
  if (await fs.pathExists(eventLogPath)) {
    const logsIndexDest = path.join(artifactDir, 'logs-index.ndjson');
    await copyIfExists(eventLogPath, logsIndexDest);
    await registerFile('logs-index.ndjson', 'logs-index');
  }

  // ── Build manifest ───────────────────────────────────────────────────────────
  const retentionDate = new Date();
  retentionDate.setDate(retentionDate.getDate() + config.retention_days);

  const manifest: ArtifactManifest = {
    schema_version: '2.0',
    task_id: normalized.task_id,
    run_id: result.run_id,
    archived_at: nowIso(),
    artifact_root: path.relative(process.cwd(), artifactDir),
    pipeline_status,
    execution_status: result.status,
    review_verdict: review.verdict,
    files,
    retention_expires_at: retentionDate.toISOString(),
    tags: [normalized.task_type, normalized.estimated_complexity],
  };

  // Validate and write manifest
  await validateOrThrow<ArtifactManifest>(
    'artifact-manifest.schema.json',
    manifest,
    'archive-artifacts'
  );

  const manifestPath = path.join(artifactDir, 'artifact-manifest.json');
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });

  logger.event('artifact.archived', 'completed', {
    artifact_dir: path.relative(process.cwd(), artifactDir),
    file_count: files.length,
    pipeline_status,
    review_verdict: review.verdict,
    retention_expires_at: manifest.retention_expires_at,
  });

  logger.info(`Artifact bundle complete: ${path.relative(process.cwd(), artifactDir)}`, {
    file_count: files.length,
  });

  return manifest;
}
