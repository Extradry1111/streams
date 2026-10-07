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
- `--style` picks the caption look (preview: `docs/caption-styles.jpg` in the repo):
  - `classic`: white bold caps, yellow word highlight, white title box (default).
  - `beast`: huge 1-2 word caps, green highlight, big bounce, red title box.
  - `neon`: white caps with a cyan glow, pink highlight, black title with cyan text.
  - `minimal`: clean sentence case on a soft dark box, up to 5 words (podcasts, talk).
  - `comic`: yellow caps, thick outline, white highlight, slight tilt, yellow title box.
  Use the style the user or the chat was set up with, the same for every clip of a
  creator, so their channel looks consistent.
- Swear words are masked (F*CK) unless `--no-censor`; the audio is never changed.
- `--trim START END` (times inside the clip) to drop a bad line or dead air.
- `--max-mb 29` when the file has to fit an upload limit (e.g. sending in chat, 30 MB);
  otherwise quality-based (`--crf 19`). `--preset fast` renders ~2× quicker.

Check one frame of each render (mid-sentence) before delivering: caption readable, title
not cut off, nothing important cropped out of the 4:3 window. If the action happens at
the edges of the frame, use `--format wide` for that clip and say why.

## 3b. Preview (cover) for each short

```
clipper.py cover hd/01.mp4 8 "His mugshot was *AI* the whole time" covers/01.jpg --logo logo.png
```

1080×1920 TikTok cover: the frame at that time in the short's layout, the hook in big
caps (`*word*` turns yellow), optional round logo badge. Pick the frame from a strip of
8 frames across the clip: a face reacting or the key object, never a blurry transition.
Send all covers plus one grid of them so the user can compare at a glance.

## 4. Post text (name, description, hashtags)

For every clip write a `NN-slug.post.md` next to the videos, ready to copy-paste:

```
# 01 · <short name of the clip>

## TikTok
Caption: <hook line, max ~100 characters, can use 1-2 emoji>
Hashtags: #creator #platform #topic #niche #fyp   (5-8 tags, most specific first)

## YouTube Shorts
Title: <max 70 characters, no clickbait lies>
Description: <1-2 sentences: who, where, what happens, without spoiling the payoff>
  + "From <creator>'s stream on <platform>, <date>."
Hashtags: #shorts #creator #topic

## YouTube / X (wide)
Title: <max 70 characters>
Description: <2-3 sentences + source line>
```

Rules: the burned-in hook (`--title`) is max ~8 words, uppercase, no emoji (the font has
none). Write in the audience's language. Tags: creator name, platform (#kick/#twitch),
what happens (#fail, #rizz, #prank…), the community (#looksmax…), then 1-2 broad tags
(#fyp, #streamclips). Never put slurs or the censored words back into post text. Also
collect all post files into one `posts.md` for the user.

## 5. Deliver

- Send files if the channel allows (respect size limits; `--max-mb`), otherwise give
  paths. Order: shorts first, then wide.
- A table: file, length, hook, anything trimmed and why, plus `posts.md`.
