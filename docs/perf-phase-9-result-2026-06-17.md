# Phase 9 — Result (2026-06-17)

> Closes Phase 9 (R17 LLM cache key correctness). R26 (provider prompt
> caching) was found to be largely auto-applied — explicitly deferred.

## Outcome

**PASS.** R17 merged + verified. R26 OpenAI/Gemini are auto-applied;
Anthropic gain trivial → deferred.

## Edits made

| File | Tier | Change |
|---|---|---|
| `app/features/render/engine/pipeline/pipeline_cache.py:_llm_plan_cache_key` | HIGH | Replaced `srt_head = srt_content[:8192]` with `srt_full_hash = hashlib.sha256(srt_content.encode("utf-8")).hexdigest()`. Cache key now reflects the full SRT content the LLM saw. Cost: sub-millisecond SHA-256 on a 60 KB SRT. Existing prefix-keyed cache entries become orphans that age out via the 72 h TTL — no migration needed. |

1-file edit. Single-line semantic change (key derivation).

## Rejected (audit triage)

**R26 OpenAI / Gemini** — auto-applied by the providers:
- OpenAI prompt caching since late 2024 (auto on >1024-token prompts)
- Gemini 2.5 Flash/Pro implicit caching automatic on paid tier

**R26 Anthropic** — code change is one-line `system=[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]` but the gain is ~30 tokens per call (system prompt is 127 chars per Phase 0 audit). Below the noise floor — deferred to Phase 11 long-tail items or skipped entirely. The audit's claimed "50–80 % token cost reduction on retry" was overstated; our existing `llm_cache_get/put` already short-circuits identical calls at the file cache, which captures the same wins more reliably than provider prompt caching.

## Verification

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (3 suites) | 39 | **39 / 39 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### Aliasing test ✓

Direct probe with two SRTs sharing the same 8 KB prefix but different
content past byte 8192:

```
SRT 1 len: 9092
SRT 2 len: 9092
Common prefix len: 8192
Key 1: 2083876b57b54aa7...
Key 2: 996e949ee07e13a0...
Keys differ (good = aliasing fixed): True
Same content gives same key: True
```

Pre-Phase-9 these two SRTs would have aliased to the same cache entry
and the second render would have inherited the first's plan. Now the
key reflects the full SRT — different content = different key.

### Acceptance checklist

- [x] py_compile passes
- [x] Focused pytest 39/39 (= baseline)
- [x] Full pytest 1396/1396 (= baseline)
- [x] Aliasing test confirms keys diverge when content past byte 8192 differs
- [x] Idempotent: identical content gives identical key
- [x] Sacred Contracts 1–8 untouched
- [x] Frozen API contracts untouched

## Insight

R17 was the correctness fix R26 wasn't. Provider prompt caching is
mostly auto-applied today (OpenAI + Gemini 2.5), and our existing
file-based `llm_cache_get/put` already captures the cross-render
dedup wins that R26 was supposed to deliver. The actual correctness
hole was the 8 KB prefix key collision — that's now fixed.

For long-form sources (60+ min audio → SRT > 8 KB), this eliminates a
silent correctness bug where two distinct transcripts could share a
cached RenderPlan.

## Rollback path (not needed)

```bash
git checkout backend/app/features/render/engine/pipeline/pipeline_cache.py
```

Existing prefix-keyed cache entries become orphans that age out via
the 72 h TTL — the worst case after rollback is a regen of an entry
that was about to be evicted anyway.

## Time spent

- Triage + mini-plan: ~10 min
- Pytest baseline + edit + py_compile: ~5 min
- Focused + full pytest: ~2 min
- Aliasing verification: ~3 min
- Result doc: ~10 min

**Total: ~30 min** (well within the 30-min budget).
