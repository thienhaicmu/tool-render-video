#!/usr/bin/env ts-node
/**
 * log-error.ts — V3
 *
 * Main CLI entry point for the bug logging and auto-fix workflow.
 *
 * Selects the highest-priority bug candidate using a deterministic score:
 *   severity + frequency + recency + context relevance boosts
 *
 * Modes:
 *   log_error                          print highest-priority bug-fix prompt
 *   log_error --run                    invoke Claude CLI with that prompt
 *   log_error --list                   show ranked candidates
 *   log_error --explain                show score breakdown for top candidate
 *
 * Filters (narrow candidate pool before ranking):
 *   --session   <session_id>
 *   --task      <task_id>
 *   --component <component>
 *   --severity  <critical|high|medium|low>
 *   --id        <error_id>             pin to a specific error
 *   --latest                           use last-error pointer only
 */

import * as fs    from 'fs';
import * as path  from 'path';
import { spawnSync } from 'child_process';

import {
  rankCandidates,
  classifyErrorSeverity,
  buildPromptContent,
  computeBugSignature,
  isValidSeverity,
  ScoredCandidate,
  ErrorRecord,
  RankingContext,
} from './error-ranking';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const ROOT        = path.resolve(__dirname, '..');
const COWORK_DIR  = path.join(ROOT, '.claude-cowork');
const ERRORS_DIR  = path.join(COWORK_DIR, 'errors');
const PROMPTS_DIR = path.join(COWORK_DIR, 'bug-prompts');
const INDEX_PATH  = path.join(COWORK_DIR, 'error-index.json');
const LAST_PATH   = path.join(COWORK_DIR, 'last-error.json');

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CliFlags {
  run:        boolean;
  list:       boolean;
  explain:    boolean;
  latest:     boolean;
  session?:   string;
  task?:      string;
  component?: string;
  severity?:  string;
  id?:        string;
}

interface ErrorIndex {
  signatures: Record<string, {
    count: number;
    first_seen_at: string;
    last_seen_at: string;
    error_ids: string[];
  }>;
  last_error_id: string | null;
}

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

function parseFlags(argv: string[]): CliFlags {
  const flags: CliFlags = { run: false, list: false, explain: false, latest: false };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--run':       flags.run       = true;        break;
      case '--list':      flags.list      = true;        break;
      case '--explain':   flags.explain   = true;        break;
      case '--latest':    flags.latest    = true;        break;
      case '--session':   flags.session   = argv[++i];   break;
      case '--task':      flags.task      = argv[++i];   break;
      case '--component': flags.component = argv[++i];   break;
      case '--severity':  flags.severity  = argv[++i];   break;
      case '--id':        flags.id        = argv[++i];   break;
    }
  }
  return flags;
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

function loadAllRecords(): ErrorRecord[] {
  if (!fs.existsSync(ERRORS_DIR)) return [];
  return fs.readdirSync(ERRORS_DIR)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      try {
        const r = JSON.parse(fs.readFileSync(path.join(ERRORS_DIR, f), 'utf8')) as ErrorRecord;
        // Back-fill bug_signature for records that predate V3
        if (!r.bug_signature) r.bug_signature = computeBugSignature(r);
        return r;
      } catch {
        return null;
      }
    })
    .filter((r): r is ErrorRecord => r !== null);
}

function loadIndex(): Map<string, number> {
  const counts = new Map<string, number>();
  if (!fs.existsSync(INDEX_PATH)) return counts;
  try {
    const idx = JSON.parse(fs.readFileSync(INDEX_PATH, 'utf8')) as ErrorIndex;
    for (const [sig, entry] of Object.entries(idx.signatures)) {
      counts.set(sig, entry.count);
    }
  } catch { /* ignore corrupt index — ranking falls back to frequency_count on record */ }
  return counts;
}

function loadLastErrorId(): string | null {
  if (!fs.existsSync(LAST_PATH)) return null;
  try {
    const last = JSON.parse(fs.readFileSync(LAST_PATH, 'utf8')) as { error_id?: string };
    return last.error_id ?? null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Prompt resolution — no duplicated template logic; delegates to error-ranking
// ---------------------------------------------------------------------------

/**
 * Returns the absolute path to the bug-fix prompt .md file.
 * Generates and caches the file on-the-fly if it is absent.
 */
function resolvePromptPath(candidate: ScoredCandidate): string {
  // 1. Stored relative path exists and file is present
  if (candidate.bug_prompt_path) {
    const abs = path.resolve(ROOT, candidate.bug_prompt_path);
    if (fs.existsSync(abs)) return abs;
  }

  // 2. Conventional location
  const conventional = path.join(PROMPTS_DIR, `${candidate.error_id}.md`);
  if (fs.existsSync(conventional)) return conventional;

  // 3. Regenerate using shared template from error-ranking.ts
  if (!fs.existsSync(PROMPTS_DIR)) fs.mkdirSync(PROMPTS_DIR, { recursive: true });

  const content     = buildPromptContent(candidate);
  const prompt_path = path.join(PROMPTS_DIR, `${candidate.error_id}.md`);
  fs.writeFileSync(prompt_path, content, 'utf8');

  // Back-patch error record with the new path
  try {
    const rec_path = path.join(ERRORS_DIR, `${candidate.error_id}.json`);
    if (fs.existsSync(rec_path)) {
      const rec = JSON.parse(fs.readFileSync(rec_path, 'utf8')) as ErrorRecord;
      rec.bug_prompt_path = path.relative(ROOT, prompt_path).replace(/\\/g, '/');
      fs.writeFileSync(rec_path, JSON.stringify(rec, null, 2), 'utf8');
    }
  } catch { /* non-fatal */ }

  return prompt_path;
}

// ---------------------------------------------------------------------------
// Output helpers
// ---------------------------------------------------------------------------

const SEV_COLOR: Record<string, string> = {
  critical: '\x1b[31m',  // red
  high:     '\x1b[33m',  // yellow
  medium:   '\x1b[36m',  // cyan
  low:      '\x1b[37m',  // white
};
const RESET = '\x1b[0m';

function colorSev(sev: string): string {
  return `${SEV_COLOR[sev] ?? ''}${sev.toUpperCase()}${RESET}`;
}

function padR(s: string, n: number): string {
  return s.length >= n ? s.slice(0, n) : s + ' '.repeat(n - s.length);
}

function printList(ranked: ScoredCandidate[]): void {
  if (ranked.length === 0) {
    console.log('No error candidates found.');
    return;
  }

  const header = [
    padR('#',          3),
    padR('SCORE',      6),
    padR('SEV',        9),
    padR('FREQ',       5),
    padR('TIMESTAMP',  26),
    padR('COMPONENT',  18),
    padR('ACTION',     16),
    padR('ERROR',      28),
    padR('ERROR_ID',   38),
  ].join(' ');

  console.log('\n' + header);
  console.log('-'.repeat(header.length));

  ranked.forEach((c, i) => {
    const short_msg = c.error_message.replace(/\n/g, ' ').slice(0, 28);
    const row = [
      padR(String(i + 1),            3),
      padR(String(c.scores.total),   6),
      padR(c.severity,               9),
      padR(String(c.frequency_count), 5),
      padR(c.timestamp,              26),
      padR(c.component,              18),
      padR(c.action,                 16),
      padR(short_msg,                28),
      padR(c.error_id,               38),
    ].join(' ');
    const color = SEV_COLOR[c.severity] ?? '';
    console.log(`${color}${row}${RESET}`);
  });
  console.log();
}

function printExplain(c: ScoredCandidate, rank: number, total: number): void {
  const s = c.scores;
  console.log(`\n=== Score Breakdown: Rank #${rank} of ${total} ===`);
  console.log(`    error_id   : ${c.error_id}`);
  console.log(`    component  : ${c.component}`);
  console.log(`    action     : ${c.action}`);
  console.log(`    error_name : ${c.error_name}`);
  console.log(`    timestamp  : ${c.timestamp}`);
  console.log(`    signature  : ${c.bug_signature}`);
  console.log();
  console.log(`  Severity  (${c.severity.padEnd(8)})      : +${s.severity_score}`);
  console.log(`  Frequency (${String(c.frequency_count).padEnd(3)}×)          : +${s.frequency_score}`);
  console.log(`  Recency                        : +${s.recency_score}`);
  console.log(`  Session boost                  : +${s.session_boost}`);
  console.log(`  Task boost                     : +${s.task_boost}`);
  console.log(`  Component boost                : +${s.component_boost}`);
  console.log(`  ────────────────────────────────────`);
  console.log(`  TOTAL                          :  ${s.total}`);
  console.log();
}

// ---------------------------------------------------------------------------
// Candidate filtering — single unified pipeline
// ---------------------------------------------------------------------------

function applyFilters(records: ErrorRecord[], flags: CliFlags): ErrorRecord[] {
  // Pin modes take priority — they collapse the pool to one candidate
  if (flags.id) {
    const pinned = records.filter(r => r.error_id === flags.id);
    if (pinned.length === 0) {
      console.error(`No error found with id: ${flags.id}`);
      process.exit(1);
    }
    return pinned;
  }

  if (flags.latest) {
    const last_id = loadLastErrorId();
    if (!last_id) {
      console.error('No last-error.json found.');
      process.exit(1);
    }
    const pinned = records.filter(r => r.error_id === last_id);
    if (pinned.length === 0) {
      console.error(`Last error id ${last_id} not found in error records.`);
      process.exit(1);
    }
    return pinned;
  }

  // Attribute filters narrow the pool; ranking selects the best within it
  let filtered = records;
  if (flags.session)   filtered = filtered.filter(r => r.session_id === flags.session);
  if (flags.task)      filtered = filtered.filter(r => r.task_id    === flags.task);
  if (flags.component) filtered = filtered.filter(r => r.component  === flags.component);

  if (flags.severity) {
    if (!isValidSeverity(flags.severity)) {
      console.error(`Invalid --severity "${flags.severity}". Valid values: critical | high | medium | low`);
      process.exit(1);
    }
    // Use classifyErrorSeverity to match ranking behavior — not a hardcoded fallback
    filtered = filtered.filter(r => classifyErrorSeverity(r) === flags.severity);
  }

  return filtered;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  const flags = parseFlags(process.argv.slice(2));

  // ── Load ─────────────────────────────────────────────────────────────────

  const all_records = loadAllRecords();
  if (all_records.length === 0) {
    console.error('No error records found. Run capture-error.ts to log a runtime error.');
    process.exit(1);
  }

  // ── Filter ───────────────────────────────────────────────────────────────

  const candidates = applyFilters(all_records, flags);
  if (candidates.length === 0) {
    console.error('No error candidates match the given filters.');
    process.exit(1);
  }

  // ── Derive ranking context from most recent candidate in filtered pool ───

  const most_recent = [...candidates].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )[0];

  const context: RankingContext = {
    session_id: flags.session ?? most_recent.session_id,
    task_id:    flags.task    ?? most_recent.task_id,
    component:  flags.component,
  };

  // ── Rank ─────────────────────────────────────────────────────────────────

  const sig_counts = loadIndex();
  const ranked     = rankCandidates(candidates, context, sig_counts);
  const top        = ranked[0];

  // ── List mode ─────────────────────────────────────────────────────────────

  if (flags.list) {
    printList(ranked);
    return;
  }

  // ── Explain mode ──────────────────────────────────────────────────────────

  if (flags.explain) {
    printExplain(top, 1, ranked.length);
    return;
  }

  // ── Resolve prompt (no template duplication — uses error-ranking.ts) ─────

  const prompt_path    = resolvePromptPath(top);
  const prompt_content = fs.readFileSync(prompt_path, 'utf8');

  // ── Default: print prompt ─────────────────────────────────────────────────

  if (!flags.run) {
    console.log(
      `\n${colorSev(top.severity)} | score=${top.scores.total} | ` +
      `${top.component}::${top.action} | ${top.error_id}\n`,
    );
    console.log(prompt_content);
    return;
  }

  // ── --run: invoke Claude CLI ──────────────────────────────────────────────
  //
  // Uses shell:false on all platforms to avoid cmd.exe 32K char limit on
  // Windows, which would silently truncate large prompts.

  console.log(
    `\n${colorSev(top.severity)} | score=${top.scores.total} | ` +
    `${top.component}::${top.action} | ${top.error_id}`,
  );
  console.log(`Sending to Claude: ${prompt_path}\n`);

  const result = spawnSync('claude', ['-p', prompt_content], {
    stdio:    'inherit',
    cwd:      ROOT,
    shell:    false,
  });

  if (result.error) {
    console.error(`\nFailed to invoke Claude CLI: ${result.error.message}`);
    console.error('Ensure `claude` is installed and available in PATH.');
    process.exit(1);
  }

  process.exit(result.status ?? 0);
}

main();
