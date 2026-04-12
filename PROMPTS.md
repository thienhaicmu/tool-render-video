# PROMPTS.md

## Global Output Rules
- JSON only.
- No markdown/prose outside JSON.
- Time units: seconds (`float`).
- No invented files/assets.

## 1) Highlight Extraction
```text
ROLE: Short-video segment selector.
INPUT: video_title, duration_sec, transcript_chunks, scenes[{start,end,score?}], target_min_sec, target_max_sec, max_segments.
RULES: obey duration bounds; prefer first-3s hook, clarity, payoff; avoid overlap unless needed; rank by viral potential.
OUTPUT JSON: {"segments":[{"start":0.0,"end":0.0,"score":0.0,"reason":"hook|emotion|novelty|clarity"}]}
```

## 2) TikTok Short Plan
```text
ROLE: Render planner.
INPUT: selected_segments, aspect_ratio(9:16|3:4|1:1), render_profile(fast|balanced|quality|best), style, constraints.
RULES: one item per part; preserve source order unless requested; set subtitle/title flags; keep ffmpeg-compatible values.
OUTPUT JSON: {"parts":[{"part_no":1,"start":0.0,"end":0.0,"add_subtitle":true,"add_title_overlay":false,"effect_preset":"slay_soft_01","render_profile":"quality"}]}
```

## 3) Subtitle Generation
```text
ROLE: Mobile subtitle formatter.
INPUT: language, words[{word,start,end}], style(tiktok_bounce_v1|pro_karaoke|clean), max_chars_per_line.
RULES: keep chronological order; short readable lines; remove filler only if meaning unchanged; enforce start<end.
OUTPUT JSON: {"captions":[{"start":0.0,"end":0.0,"text":"sample subtitle"}]}
```
