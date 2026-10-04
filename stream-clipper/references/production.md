# Production: 1080p clips, subtitles, shorts, titles

All commands are `python3 scripts/clipper.py ...` (path relative to the skill folder).
Needs ffmpeg with libass; fonts ship in `assets/fonts` (Montserrat, OFL licensed).

## 1. Cut at full quality

```
clipper.py cut vod.json 10:53:40 10:54:25 hd/01-van-faceplant.mp4
```

- Picks the best stream rendition up to `--height` (default 1080), keeps the source frame
  rate (usually 60), downloads only the segments around the clip. Never upscale: if the
  VOD only has 720p, say so.
- Name files `NN-short-slug.mp4` in report order.
- Before rendering, check the moment is really inside: `ffmpeg -ss <s> -i clip.mp4 -frames:v 1 x.jpg`
  at the second where the event should be, and look at it.

## 2. Transcribe (word timings)

Pick the first that works:

1. **faster-whisper installed** (`pip install faster-whisper`, needs model download access):
   `clipper.py transcribe hd/01.mp4 subs/01.words.json --lang en`
2. **Descript connector** (`mcp__Descript__*`), usually available:
   1. `clipper.py audio hd/01.mp4 audio/01.m4a` for each clip (small uploads).
   2. `import_media` with one project, each audio as a direct upload
      (`content_type: audio/mp4`, `file_size`, `language`) and one composition per clip
      (`add_compositions`). PUT each file to its `upload_url` with
      `Content-Type: application/octet-stream`. `wait_for_job` until `stopped`.
   3. `export_transcript` per composition with `format: srt`,
      `include_speaker_labels: off`. Save each as `subs/NN.srt`.
   4. `clipper.py words subs/NN.srt subs/NN.words.json`.
   Show the user the Descript project URL.
3. Neither works → render without captions and tell the user why.

Read every transcript. It tells you what actually happened (things chat and frames
missed), and it's where you catch lines that could get a clip removed (slurs, political
or hateful statements). Trim those out with `--trim` and tell the user what you cut.

## 3. Render

```
clipper.py render hd/01.mp4 subs/01.words.json out/01-short.mp4 --format short --title "He was explaining jaw surgery... then this happened"
clipper.py render hd/01.mp4 subs/01.words.json out/01-wide.mp4  --format wide
```

- `short`: 1080×1920 for TikTok/Shorts/Reels. Blurred full-bleed background, the action
  cropped to 4:3 in the middle, hook title in a white box on top, captions below the video.
- `wide`: 1920×1080 for YouTube/X, captions at the bottom.
- Captions: Montserrat Black, uppercase, 1-3 words at a time (shorts), the spoken word
  in yellow with a small pop. Swear words are masked (F*CK) unless `--no-censor`; the
  audio is never changed.
- `--trim START END` (times inside the clip) to drop a bad line or dead air.
- `--max-mb 29` when the file has to fit an upload limit (e.g. sending in chat, 30 MB);
  otherwise quality-based (`--crf 19`). `--preset fast` renders ~2× quicker.

Check one frame of each render (mid-sentence) before delivering: caption readable, title
not cut off, nothing important cropped out of the 4:3 window. If the action happens at
the edges of the frame, use `--format wide` for that clip and say why.

## 4. Titles

For each clip write:
- the **hook** burned into the short (`--title`): max ~8 words, uppercase, curiosity
  without spoiling the payoff ("He was explaining jaw surgery... then this happened");
- **3 post titles** per platform (TikTok, YouTube Shorts, YouTube/X wide), in the
  audience's language, plus 3-5 hashtags (streamer name, platform, topic).
No emoji inside the burned-in title (the font has none); emoji are fine in post titles.

## 5. Deliver

- Send files if the channel allows (respect size limits; `--max-mb`), otherwise give
  paths. Order: shorts first, then wide.
- A table: file, length, hook, post titles, anything trimmed and why.
