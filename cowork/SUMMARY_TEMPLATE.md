# Summary Template — Cowork Task Output

Use this format for all task completion reports. Every cowork task must end with this output.

---

## Template

```markdown
## Summary
[One or two sentences. What was done and what was the outcome.]

## Assumptions
- [Any assumption made about scope, context, or behavior — list them all]
- [Do not hide assumptions behind confident-sounding statements]

## Files Changed
| File | Change |
|---|---|
| `path/to/file.py` | [What changed and why] |

## Verification Result
Command: `/test` (or exact command run)
Result: pass / fail
Output:
```
[paste test output here — do not summarize]
```

## Residual Risk
- [Any behavior that could not be fully verified]
- [Any edge case that was not tested]
- [Any dependency that may be affected]

## Next Recommended Step
- [One clear next action, or "none — task is complete and verified"]
```

---

## Completed Fix Example

```markdown
## Summary
Fixed SRT offset calculation in subtitle_engine.py — subtitles were appearing 2s late
for all segments after the first. Root cause: missing start_time offset when slicing SRT.

## Assumptions
- Assumed the bug was isolated to slice_srt() and not in the render pipeline slice call.
- Tested with default mode only. word_timestamps=True mode not tested.

## Files Changed
| File | Change |
|---|---|
| `backend/app/services/subtitle_engine.py` | Corrected offset in `slice_srt()` line 142 |

## Verification Result
Command: `/test dev`
Result: pass
Output:
```
check_health: pass
check_render_route: pass
check_jobs_route: pass
check_subtitle_slice: pass
4/4 checks passed
```

## Residual Risk
- word_timestamps=True mode not tested — may have same offset issue.
- Segment starting at exactly 0s not tested in isolation.

## Next Recommended Step
- Manual render test with word_timestamps=True to confirm subtitle alignment.
```

---

## Investigation Output Example

```markdown
## Summary
Root cause identified: session cleanup runs before render_report.xlsx is written,
causing file-not-found on the report writer.

## Assumptions
- Based on reading orchestration/render_pipeline.py steps 9–10 only.
- Did not read report_service.py in detail.

## Files Changed
None — investigation only. No patch applied.

## Proposed Fix
Move cleanup_session_fn() call to after write_render_report() in render_pipeline.py line 287.
One-line change. Low risk.

## Next Recommended Step
- Confirm fix plan before applying.
- After applying: run /test and one manual render to verify report is written.
```
