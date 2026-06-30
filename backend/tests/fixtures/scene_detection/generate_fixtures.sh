#!/usr/bin/env bash
# D-2-motion Phase 2 — regenerate the 3 synthetic scene-detection fixtures.
#
# .mp4 files are gitignored (binary artifacts). This script lets the
# Phase 2 engineer regenerate them locally before running the benchmark.
# Run from this directory; depends on FFmpeg in PATH.
#
# See README.md for what each fixture represents and what each detector
# is expected to find.

set -euo pipefail

cd "$(dirname "$0")"

echo "Generating three_shot_cuts.mp4 (15s, 2 hard cuts at t=5,10)..."
ffmpeg -y \
  -f lavfi -i "testsrc=duration=5:size=320x240:rate=30" \
  -f lavfi -i "testsrc2=duration=5:size=320x240:rate=30" \
  -f lavfi -i "smptebars=duration=5:size=320x240:rate=30" \
  -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1:a=0" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  three_shot_cuts.mp4 -loglevel error

echo "Generating single_shot_static.mp4 (10s, 0 cuts)..."
ffmpeg -y \
  -f lavfi -i "color=blue:duration=10:size=320x240:rate=30" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  single_shot_static.mp4 -loglevel error

echo "Generating music_video_fast_cuts.mp4 (12s, 5 cuts every 2s)..."
ffmpeg -y \
  -f lavfi -i "testsrc=duration=2:size=320x240:rate=30" \
  -f lavfi -i "testsrc2=duration=2:size=320x240:rate=30" \
  -filter_complex "[0:v][1:v][0:v][1:v][0:v][1:v]concat=n=6:v=1:a=0" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  music_video_fast_cuts.mp4 -loglevel error

echo "Done. Fixtures regenerated in $(pwd):"
ls -la *.mp4
