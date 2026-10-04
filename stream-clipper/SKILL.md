---
name: stream-clipper
description: Turns Twitch and Kick stream recordings (VODs) into ready-to-post clips. It reads the whole chat replay, finds the funniest 30-120 second moments from spikes of laughter and 'clip it', checks each one on video frames and transcripts, then cuts them in 1080p and renders TikTok-style 9x16 shorts and 16x9 videos with burned-in animated subtitles, hook titles and post titles. Works from a terminal (Claude Code or any session with a shell, with the Descript connector for transcripts) or through the Claude in Chrome extension for finding moments. Use it whenever someone asks to find funny moments, highlights, clips, shorts, TikToks or Reels in a stream, VOD, past broadcast or stream recording, to add subtitles to stream clips, or says 'clip xqc' or 'clip this VOD' for Twitch or Kick, in any language (клипы со стрима, нарезка, смешные моменты, хайлайты, субтитры).
---

# stream-clipper

From one stream recording to finished clips:
**find** moments → **check** them → **cut** in 1080p → **subtitle** → **short (9:16) + wide (16:9)** → **titles**.

A good clip is 30-120 s and funny **on its own**: a TikTok viewer who has never seen the
streamer gets it within 5-10 seconds.

## Pick the mode

- **Toolbox mode** (preferred): you can run shell commands (Claude Code, a cloud
  session). Uses `scripts/clipper.py` + ffmpeg. Does everything, including the finished
  videos. Kick works end to end; Twitch needs `yt-dlp` for video and Chrome mode for chat.
- **Chrome mode**: no shell, but Claude in Chrome is connected. Finds and checks moments
  in the user's browser; can't cut or render. Follow `references/chrome-mode.md`.

Neither available → explain what's needed (README → Install) and stop.

## Inputs

- A VOD link, or a streamer (`clip xqc`, `clip kick.com/somebody`): then take their latest
  finished VOD from the channel's videos page. No streamer named → `streamers.md`; if
  empty, ask once. "clip my streamers" → each streamer in `streamers.md` in turn.
- Defaults unless the user says otherwise: up to 5 finished clips (report up to 10
  candidates), 30-120 s, both formats, captions in the stream's language, report in the
  user's language.

## Toolbox mode

`C=scripts/clipper.py` (relative to this skill folder). Work in a scratch folder.

### 1. VOD and chat

```
python3 $C info <vod url>          # -> vod.json: title, length, start, stream URL
python3 $C chat vod.json           # Kick: whole chat replay -> chat.json (~4 min for 24 h)
python3 $C score chat.json         # -> candidates.json + ranked table
```

`score` counts each chatter once per 5 s so spammers can't fake a spike, skips the first
and last 5 minutes, and labels each window `funny` / `clip-call` / `hype`. How to read it:
`references/signals.md`. Twitch chat can't be downloaded here: get candidates with Chrome
mode, then continue at step 3.

### 2. Check every candidate before cutting anything

For the top ~15, best first:

1. `python3 $C context chat.json <start-20> <end+10>`: what is chat laughing at?
2. `python3 $C sheet vod.json <start> <end> sheets/NN.jpg`, then look at the image
   (12 frames with timecodes). Zoom in on the key moment with `--step 1.5`.
3. Keep, trim, or drop (raids, alerts, intros, chat arguments, moments that need
   back-story). Chat lags the video by ~5-10 s, so the event is usually 5-20 s before
   the chat peak.
4. Reactions to audio with nothing visible → keep as "needs a listen"; the transcript in
   step 4 decides.

Write the report (`references/report-template.md`) and save it as
`clips/<streamer>/<YYYY-MM-DD>-<vod id>.md` if you are in the repo.

If the user only asked for moments, stop here and offer to make the clips.

### 3-6. Make the clips

Follow `references/production.md`:
3. `cut` each kept moment at 1080p (real resolution, never upscaled).
4. Transcribe: faster-whisper, else the **Descript connector** (audio upload → SRT →
   `words`). Read the transcripts: they explain what happened and reveal lines that need
   trimming.
5. `render` each clip twice: `--format short --title "<hook>"` and `--format wide`.
   Look at one frame of each before delivering.
6. Write hooks and post titles; deliver files + a table.

## Rules

- Only VODs the user can open normally. No bypassing subscriber locks, geo-blocks or
  logins. Don't post, follow or create clips on the platform for the user.
- Never invent what was said. Words come from transcripts; events from frames and chat.
- Flag content that can get a clip removed (slurs, hateful or political lines, minors,
  nudity) and trim it, saying what you cut.
- Chat in some communities is toxic. Never quote slurs in reports; describe instead.
