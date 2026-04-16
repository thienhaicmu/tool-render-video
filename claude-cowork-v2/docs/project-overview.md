# Project Overview

## Purpose

This project is an AI-assisted engineering platform that processes long-form
video content into short-form social media clips with subtitles, overlays,
and automated upload workflows.

## Core Value Proposition

- Engineers submit a video source (YouTube URL or local file)
- The system downloads, transcribes, segments, and renders clips automatically
- Output is upload-ready TikTok/YouTube Shorts content with subtitles
- All operations are auditable, resumable, and configurable

## Primary Users

- **Content Operators**: Submit videos, configure channels, review output
- **Backend Engineers**: Maintain render pipeline, add features, fix bugs
- **Platform Engineers**: Manage infra, deployments, scaling

## System Components

| Component | Role |
|-----------|------|
| FastAPI backend | REST API + WebSocket job streaming |
| Electron desktop shell | Local GUI wrapping the web frontend |
| SQLite (WAL mode) | Persistent job state |
| yt-dlp | YouTube download engine |
| Whisper | Audio transcription |
| FFmpeg | Video processing |
| Playwright | Browser automation for upload |

## Non-Goals

- This system does NOT manage content rights or licensing
- This system does NOT replace human review of output content
- This system does NOT operate as a multi-tenant SaaS (single-operator, local)

## Success Criteria

1. A render job completes end-to-end without manual intervention
2. Output video quality matches or exceeds 1080p source
3. Subtitles are correctly timed and styled
4. Job progress is visible in real time via the UI
5. Failed jobs are retryable without restarting from scratch
