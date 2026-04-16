# claude-cowork-v2

Runtime bug logging and auto-fix workflow for the `tool-render-video` project — Version 3.

## Bug Debug & Auto Fix Workflow

The workflow captures runtime errors, ranks them by priority, and either prints or sends a structured bug-fix prompt to Claude CLI.

### Commands

**List all captured errors ranked by priority:**
```bash
npm run log_error -- --list
```
Shows a table with rank, score, severity, frequency, timestamp, component, action, error message, and error ID. Errors are sorted highest-priority first (severity → frequency → recency → context relevance).

**Show score breakdown for the top-ranked error:**
```bash
npm run log_error -- --explain
```
Prints a detailed breakdown of how the priority score was computed: severity score, frequency score, recency score, and context boosts (session / task / component).

**Print the bug-fix prompt for the top-ranked error:**
```bash
npm run log_error
```
Outputs the structured bug-fix prompt to stdout. Use this to review what will be sent to Claude before running it.

**Send the bug-fix prompt to Claude CLI automatically:**
```bash
npm run log_error:run
```
Invokes `claude -p <prompt>` directly. Requires `claude` to be installed and available in `PATH`.

### Typical Workflow

1. A runtime error occurs in the backend pipeline.
2. Capture it:
   ```bash
   npm run capture-error -- \
     --session sess-001 \
     --task    task-42  \
     --run     run-1    \
     --component render_engine \
     --action  render \
     --error-name RuntimeError \
     --message "render failed: exit code 1"
   ```
3. Review ranked errors:
   ```bash
   npm run log_error -- --list
   ```
4. Inspect the top candidate's score:
   ```bash
   npm run log_error -- --explain
   ```
5. Print the prompt, review it, then send to Claude:
   ```bash
   npm run log_error        # review
   npm run log_error:run    # send
   ```

### Optional Filters

All `log_error` commands accept these flags to narrow the candidate pool before ranking:

| Flag | Description |
|------|-------------|
| `--session <id>` | Limit to errors from this session |
| `--task <id>` | Limit to errors from this task |
| `--component <name>` | Limit to errors from this component |
| `--severity critical\|high\|medium\|low` | Limit to errors of this severity |
| `--id <error_id>` | Pin to a specific error record |
| `--latest` | Use only the most recently captured error |

Example — show only critical errors from the render pipeline:
```bash
npm run log_error -- --list --component render_engine --severity critical
```

### Priority Scoring

Errors are ranked using a deterministic score:

| Factor | Weight |
|--------|--------|
| Severity: critical / high / medium / low | +100 / +70 / +40 / +10 |
| Frequency: 2× / 3–5× / 6+× | +10 / +20 / +30 |
| Recency: ≤5 min / ≤30 min / ≤2 h / ≤24 h | +20 / +15 / +10 / +5 |
| Same session | +8 |
| Same task | +6 |
| Same component | +4 |

### Storage Paths

```
claude-cowork-v2/
  .claude-cowork/
    errors/           # <error_id>.json — one file per captured error
    bug-prompts/      # <error_id>.md  — generated bug-fix prompts
    error-index.json  # signature frequency tracking
    last-error.json   # pointer to most recently captured error
```
