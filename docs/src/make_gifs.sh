#!/usr/bin/env bash
# Rebuild README GIFs from the e2e test recordings (tests/out/*.webm) and the demo.
# Run `node tests/e2e.js` and `node docs/src/record_demo.js` first.
set -euo pipefail
cd "$(dirname "$0")/../.."
pal='split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle'
# Whole mock-Twitch run (incl. speed reset, ad pause, page reload), sped up ~10x
ffmpeg -hide_banner -loglevel error -y -i tests/out/twitch.webm \
  -vf "setpts=PTS/12,fps=6,scale=640:-1:flags=lanczos,$pal" -loop 0 docs/recording.gif
# Mock-Kick start: unknown chat markup -> auto-detected within seconds, sped up 3x
ffmpeg -hide_banner -loglevel error -y -t 30 -i tests/out/kick.webm \
  -vf "setpts=PTS/3,fps=6,scale=640:-1:flags=lanczos,$pal" -loop 0 docs/autodetect.gif
ffmpeg -hide_banner -loglevel error -y -i docs/src/out/demo.webm \
  -vf "fps=12,scale=800:-1:flags=lanczos,$pal" -loop 0 docs/demo.gif
ls -la docs/*.gif
