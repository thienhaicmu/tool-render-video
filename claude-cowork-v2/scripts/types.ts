/**
 * types.ts
 *
 * Central type definitions for the Claude Cowork V2 pipeline.
 * All pipeline components import from here. Do not define domain
 * types in individual scripts.
 */

// ── Enumerations ──────────────────────────────────────────────────────────────

export type TaskType =
  | 'bugfix'
  | 'feature'
  | 'refactor'
  | 'infra'
  | 'docs'
  | 'test'
  | 'security'
  | 'performance';

export type TaskComplexity = 'trivial' | 'small' | 'medium' | 'large' | 'xl';

export type TaskPriority = 'low' | 'normal' | 'high' | 'critical';

export type ExecutorMode = 'claude_cli' | 'simulated' | 'dry_run';

export type ExecutionStatus =
  | 'success'
  | 'partial'
  | 'failed'
  | 'timeout'
  | 'dry_run'
  | 'simulated';

export type ReviewVerdict =
  | 'accepted'
  | 'accepted_with_followup'
  | 'changes_requested'
  | 'rejected';

export type ReviewMode = 'llm' | 'deterministic' | 'mock';

export type PipelineStatus = 'completed' | 'partial' | 'failed';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type NormalizerProviderName = 'mock' | 'openai_compat';

export type ReviewerProviderName = 'mock' | 'openai_compat' | 'deterministic';

// ── Event taxonomy ────────────────────────────────────────────────────────────

export type EventName =
  | 'task.received'
  | 'task.normalized'
  | 'task.validation.failed'
  | 'task.packaged'
  | 'task.execution.started'
  | 'task.execution.completed'
  | 'task.execution.failed'
  | 'task.review.started'
  | 'task.review.completed'
  | 'artifact.archived'
  | 'pipeline.completed'
  | 'pipeline.failed';

// ── Core domain models ────────────────────────────────────────────────────────

export interface RawTask {
  task_id: string;
  submitted_at: string;
  submitted_by: string;
  raw_prompt: string;
  priority?: TaskPriority;
  labels?: string[];
  target_branch?: string;
  project_hint?: string;
  attachments?: Array<{
    name: string;
    path: string;
    description?: string;
  }>;
}

export interface NormalizedPrompt {
  schema_version: '2.0';
  task_id: string;
  task_type: TaskType;
  title: string;
  objective: string;
  business_context: string;
  project_context_needed: string[];
  scope_in: string[];
  scope_out: string[];
  constraints: string[];
  assumptions: string[];
  related_files: string[];
  acceptance_criteria: string[];
  logging_requirements: string[];
  review_checkpoints: string[];
  expected_deliverables: string[];
  risk_flags?: string[];
  estimated_complexity: TaskComplexity;
  raw_task_ref: string;
  normalized_at: string;
  normalizer_model?: string;
  normalizer_provider?: string;
}

export interface NormalizationError {
  error: 'insufficient_context' | 'ambiguous_scope' | 'normalization_failed';
  message: string;
  questions?: string[];
}

export interface FileChange {
  path: string;
  operation: 'created' | 'modified' | 'deleted';
  lines_added?: number;
  lines_removed?: number;
}

export interface ExecutionResult {
  schema_version: '2.0';
  task_id: string;
  run_id: string;
  session_id: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  status: ExecutionStatus;
  executor_mode: ExecutorMode;
  summary?: string;
  files_read?: string[];
  files_changed?: FileChange[];
  stdout_excerpt?: string;
  stderr_excerpt?: string;
  stdout_path?: string;
  stderr_path?: string;
  exit_code?: number | null;
  risks?: string[];
  followups?: string[];
  raw_output_ref?: string;
  error?: string | null;
}

export interface AcceptanceCriterionResult {
  criterion: string;
  met: 'yes' | 'no' | 'partial' | 'not_verifiable';
  evidence: string;
}

export interface ReviewCheckpointResult {
  checkpoint: string;
  passed: boolean;
  notes: string;
}

export interface ReviewReport {
  schema_version: '2.0';
  task_id: string;
  run_id: string;
  reviewed_at: string;
  reviewer_mode: ReviewMode;
  reviewer_model?: string;
  verdict: ReviewVerdict;
  scope_fit_score: number;
  safety_score: number;
  logging_score: number;
  overall_score: number;
  acceptance_criteria_results: AcceptanceCriterionResult[];
  review_checkpoint_results?: ReviewCheckpointResult[];
  scope_assessment: string;
  safety_assessment: string;
  logging_assessment: string;
  followup_tasks?: string[];
  blocking_issues?: string[];
  summary: string;
  recommendations: string[];
}

export interface ArtifactFile {
  name: string;
  path: string;
  type:
    | 'raw-prompt'
    | 'normalized-prompt'
    | 'task-pack'
    | 'execution-result'
    | 'review-report'
    | 'final-summary'
    | 'logs-index'
    | 'stdout'
    | 'stderr'
    | 'other';
  size_bytes?: number;
  sha256?: string;
}

export interface ArtifactManifest {
  schema_version: '2.0';
  task_id: string;
  run_id: string;
  archived_at: string;
  artifact_root: string;
  pipeline_status: PipelineStatus;
  execution_status?: ExecutionStatus;
  review_verdict?: ReviewVerdict | 'skipped';
  files: ArtifactFile[];
  retention_expires_at?: string;
  tags?: string[];
}

// ── Config model ──────────────────────────────────────────────────────────────

export interface PipelineConfig {
  version: string;
  project_name: string;
  executor_mode: ExecutorMode;
  claude_cli_command: string;
  normalizer_provider: NormalizerProviderName;
  normalizer_model: string;
  normalizer_base_url?: string;
  reviewer_provider: ReviewerProviderName;
  reviewer_model: string;
  reviewer_base_url?: string;
  log_level: LogLevel;
  artifact_root: string;
  tasks_root: string;
  logs_root: string;
  retention_days: number;
  max_retries: number;
  timeout_seconds: number;
  doc_paths: string[];
}

// ── Structured event log ──────────────────────────────────────────────────────

export interface StructuredEvent {
  timestamp: string;
  task_id: string;
  run_id: string;
  session_id: string;
  component: string;
  event_name: EventName;
  actor: string;
  status: 'started' | 'completed' | 'failed' | 'skipped' | 'info';
  metadata?: Record<string, unknown>;
  error?: string;
}

// ── Pipeline context (passed through stages) ──────────────────────────────────

export interface PipelineContext {
  task_id: string;
  run_id: string;
  session_id: string;
  config: PipelineConfig;
  raw_task?: RawTask;
  normalized?: NormalizedPrompt;
  task_pack_path?: string;
  execution_result?: ExecutionResult;
  review_report?: ReviewReport;
  artifact_manifest?: ArtifactManifest;
  started_at: string;
  completed_at?: string;
  status: PipelineStatus;
  stage_errors: Array<{ stage: string; error: string }>;
}

// ── LLM provider interfaces ───────────────────────────────────────────────────

export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMCompletionOptions {
  messages: LLMMessage[];
  max_tokens?: number;
  temperature?: number;
}

export interface LLMCompletionResult {
  content: string;
  model?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
  };
}

export interface NormalizerProviderInterface {
  complete(options: LLMCompletionOptions): Promise<LLMCompletionResult>;
}

export interface ReviewerProviderInterface {
  complete(options: LLMCompletionOptions): Promise<LLMCompletionResult>;
}

// ── Executor interfaces ───────────────────────────────────────────────────────

export interface ExecutorOptions {
  task_id: string;
  run_id: string;
  session_id: string;
  task_pack_path: string;
  task_pack_content: string;
  timeout_seconds: number;
  config: PipelineConfig;
}

export interface TaskExecutor {
  execute(options: ExecutorOptions): Promise<ExecutionResult>;
}
