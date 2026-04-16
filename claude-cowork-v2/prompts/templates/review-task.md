Review the task specification and execution result provided above.

Evaluate every acceptance criterion individually. For each one, set `met` to exactly one of:
- `"yes"` — criterion is demonstrably satisfied by the execution output
- `"no"` — criterion is demonstrably not satisfied
- `"partial"` — criterion is partially satisfied; explain what is missing in `evidence`
- `"not_verifiable"` — execution mode (simulated/dry_run) or missing output makes it impossible to verify

Evaluate every review checkpoint. Set `passed` to `true` only if the checkpoint condition is verifiable and confirmed.

Produce your review as a single JSON object matching the schema in the system prompt.
Output only the JSON object. No markdown fences. No commentary before or after.
