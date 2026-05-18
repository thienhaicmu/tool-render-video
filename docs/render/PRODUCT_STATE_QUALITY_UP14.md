# PRODUCT STATE — QUALITY-UP14: Platform-Aware Editing

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): platform-aware editing`
**Status:** Shipped

---

## Summary

The editor now makes small, purposeful adjustments based on the creator's target
distribution platform — TikTok, YouTube Shorts, or Instagram Reels. Not a different
render engine. Not trend prediction. Just lightweight editorial bias that matches
platform viewer behavior: hook strength, pacing, and subtitle tone.

No LLM. No API calls. No rewrite. No creator overwhelm.
One dropdown. Three options.

---

## Part A — Platform Profiles

Three profiles. Each applies small, transparent adjustments to segment selection,
subtitle style, and playback speed.

### TikTok
- **Speed delta:** +0.04 (e.g. 1.07 → 1.11)
- **Hook sort bonus:** +6pts to hook-strong clips in initial selection
- **Subtitle bias:** `viral` for interview/commentary/vlog/tutorial; `gaming` for montage

### YouTube Shorts (default)
- **Speed delta:** 0.00 (no change — existing defaults already tuned for YT)
- **Hook sort bonus:** 0
- **Subtitle bias:** inherit content-type defaults (clean/story/viral/gaming)

### Instagram Reels
- **Speed delta:** −0.03 (e.g. 1.07 → 1.04)
- **Hook sort bonus:** 0
- **Subtitle bias:** `clean` for interview/commentary/vlog/tutorial; `gaming` for montage

---

## Part B — Decision Hierarchy

Platform is guidance, not override. Creator intent always wins.

```
1. Variant subtitle style (UP13 multi-variant explicit intent)
2. Creator's subtitle_style (explicit UI choice)
3. Platform sub_bias[content_type]          ← UP14 NEW
4. Content-type default (_CONTENT_TYPE_SUB_DEFAULTS)
5. "tiktok_bounce_v1" fallback
```

Speed:
```
1. variant_playback_speed (UP13 variant already bakes its own speed)
2. payload.playback_speed + platform speed_delta   ← UP14 NEW (only for non-variant)
```

Clip selection (initial sort):
```
viral_score + motion_boost + (hook_score × platform_hook_bonus / 100)
```
TikTok adds up to 6 extra points for hook-strong clips. YouTube Shorts and Instagram
add 0 — their selection is unchanged.

---

## Part C — Compatibility with UP13 Multi-Variant

Platform and multi-variant are orthogonal. Both can be active simultaneously.

When `multi_variant=True`:
- Variant subtitle style is set by `_VARIANT_AGGRESSIVE_SUB` / `_VARIANT_STORY_SUB`
  maps — **platform sub_bias is not applied** (variant intent takes precedence, hierarchy step 1)
- Variant playback speed is already set with variant delta — **platform speed delta is
  not applied** (variant_playback_speed present → `or` short-circuits before platform delta)
- Hook sort bonus **is applied** in the initial pool sort before variant selection —
  TikTok will bias the pool toward hook-strong segments for all three variants

---

## Part D — Output Experience

### Platform dropdown
Located in editor render settings, after the Multi-variant checkbox.
- Default: YouTube Shorts
- Options: YouTube Shorts · TikTok · Instagram Reels

### Output panel
When a non-default platform is selected, a subtle banner appears above the clip
cards: "Optimized for: TikTok" (or the selected platform name).
Not shown for YouTube Shorts (the default) to avoid visual noise.

---

## Part E — Observability

A `platform_bias_applied` event is emitted after pool sorting:
```
event: platform_bias_applied
context: {
  target_platform: "tiktok",
  hook_sort_bonus: 6,
  speed_delta: 0.04
}
```

Subtitle source (from existing `subtitle_style_applied` event):
```
subtitle_style_source: "auto"  → content-type or platform bias was used
subtitle_style_source: "explicit" → creator or variant set it explicitly
```

Grep: `platform_bias_applied` in job log for QA.

---

## Schema Changes

`backend/app/models/schemas.py`:
```python
target_platform: str = "youtube_shorts"  # UP14 — guidance only
```

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/models/schemas.py` | `target_platform: str = "youtube_shorts"` added |
| `backend/app/orchestration/render_pipeline.py` | `_PLATFORM_PROFILES`; `_target_platform` + `_platform_hook_bonus` before sort; sort key hook bonus; `platform_bias_applied` event; subtitle sub_bias tier; speed delta for non-variant |
| `backend/static/index.html` | Platform dropdown (YouTube Shorts / TikTok / Instagram Reels) |
| `backend/static/js/editor-view.js` | `payload.target_platform` from dropdown |
| `backend/static/js/render-ui.js` | `targetPlatform` in `_rankMap`; platform banner above clip cards |
| `backend/static/css/app.css` | `.clipCardVariantBadge` (UP13 catch-up) + `.clipsPlatformBanner` |
| `docs/render/PRODUCT_STATE_QUALITY_UP14.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Per-platform aspect ratio enforcement | Creator owns aspect ratio — platform hint is not a constraint |
| Per-platform duration guidance | Already covered by min/max_part_sec; platform shouldn't change clip length |
| Platform-specific CRF/quality | UP11 content-type CRF already covers quality; platform doesn't change codec |
| Trend-scraping / social API | Explicitly excluded from scope |
| Per-variant platform override | Platform+variant both active = platform biases pool; variant handles its own style |
| "Auto-detect platform from URL" | Creator intent signal is too weak; manual is correct |

---

## Manual QA Checklist

### Toggle
- [ ] Editor render settings shows "Platform" dropdown with YouTube Shorts / TikTok / Instagram Reels
- [ ] Default selection is YouTube Shorts
- [ ] Dropdown label shows "Subtle editorial bias per platform" hint

### No regression (YouTube Shorts default)
- [ ] With platform = YouTube Shorts: render output identical to pre-UP14 behavior
- [ ] Log shows `platform_bias_applied` with `target_platform=youtube_shorts hook_sort_bonus=0 speed_delta=0.0`

### TikTok
- [ ] Log shows `platform_bias_applied` with `target_platform=tiktok hook_sort_bonus=6 speed_delta=0.04`
- [ ] Output clip(s) have `variant_playback_speed` ≈ base + 0.04 (or combined with variant delta)
- [ ] Log `subtitle_style_applied` shows `viral` style for vlog/commentary content (when no explicit style set)
- [ ] Output panel shows "Optimized for: TikTok" banner

### Instagram Reels
- [ ] Log shows `platform_bias_applied` with `target_platform=instagram_reels speed_delta=-0.03`
- [ ] Output clip(s) have speed ≈ base − 0.03
- [ ] Log `subtitle_style_applied` shows `clean` for interview/vlog content (when no explicit style set)
- [ ] Output panel shows "Optimized for: Instagram Reels" banner

### Creator override always wins
- [ ] Set explicit subtitle_style in UI → platform sub_bias NOT applied (`subtitle_style_source=explicit`)
- [ ] Multi-variant + TikTok → variant badge style used (not platform bias)
- [ ] Multi-variant + TikTok → hook sort bonus applied to pool; variant still selects its own segment

### Performance
- [ ] Platform logic adds no measurable render overhead (pure dict lookup + arithmetic)
- [ ] Cancel / resume / retry unaffected
- [ ] Queue concurrent renders unaffected
