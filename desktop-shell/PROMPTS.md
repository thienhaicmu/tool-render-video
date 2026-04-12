# Prompt Pack (Compact)

## Common Format
- `ROLE`
- `INPUT`
- `RULES`
- `OUTPUT` (JSON only)

## 1) Highlight Extraction
- `ROLE`: select high-viral candidate segments.
- `INPUT`: `video_title`, `duration_sec`, optional `transcript`, `scene_list(start,end,transition_score)`, `target_min_sec`, `target_max_sec`, `max_segments`.
- `RULES`: keep segment duration bounds; prefer strong first-3s hook; prefer clean cuts; avoid overlap unless requested.
- `OUTPUT`:
```json
{"segments":[{"start":0.0,"end":0.0,"reason":"hook|pace|emotion|clarity","confidence":0.0}]}
```

## 2) TikTok Short Plan
- `ROLE`: produce executable render plan for selected segments.
- `INPUT`: `segments`, `aspect_ratio(9:16|3:4|1:1)`, `subtitle_style`, `add_title_overlay`, `effect_preset`, `render_profile(fast|balanced|quality|best)`.
- `RULES`: ffmpeg-compatible only; no invented assets; include per-part subtitle decision.
- `OUTPUT`:
```json
{"parts":[{"part_no":1,"start":0.0,"end":0.0,"subtitle":true,"title_overlay":true,"effect_preset":"slay_soft_01","render_profile":"quality"}]}
```

## 3) Subtitle Generation
- `ROLE`: convert word timestamps to mobile-readable subtitle lines.
- `INPUT`: `language`, `words[{word,start,end}]`, `style(tiktok_bounce_v1|pro_karaoke|clean)`, `max_chars_per_line`.
- `RULES`: preserve timing order; keep concise readable lines; remove filler/noise where safe.
- `OUTPUT`:
```json
{"captions":[{"start":0.0,"end":0.0,"text":"..."}]}
```
