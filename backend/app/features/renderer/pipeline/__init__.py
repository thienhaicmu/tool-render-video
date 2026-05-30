"""Renderer pipeline layers.

Execution order:
  L0  source.py         — validate + preprocess source video
  L1  scene_analysis.py — detect scenes, build + score candidate segments
  L2  ai_analysis.py    — AI selects best segments (Groq / local / hybrid)
  L3  transcription.py  — Whisper full-video transcription + translation
  L4  ai_refinement.py  — AI advisory refinement of selected segments
  L5  render_loop.py    — FFmpeg render loop orchestration
  L6  part_renderer.py  — per-part FFmpeg encoding
  L7  qa.py             — output validation (never bypass)
  L8  ranking.py        — output ranking + best-clip marking
  L9  finalizer.py      — report write + result_json + cleanup
"""
