# Platforms: where things are

Twitch and Kick change their layout. If a link or button isn't where this says, find it
with `find` / `read_page` instead of guessing.

## Twitch

| What | Link |
|------|------|
| Past broadcasts | `https://www.twitch.tv/<login>/videos?filter=archive&sort=time` |
| Highlights (saved by the streamer) | `https://www.twitch.tv/<login>/videos?filter=highlights&sort=time` |
| Viewer clips, last 7 days | `https://www.twitch.tv/<login>/clips?filter=clips&range=7d` |
| Last 30 days / all time | `range=30d` / `range=all` |
| VOD at a time | `https://www.twitch.tv/videos/<id>?t=1h02m03s` |

- VODs are kept 7-60 days depending on the streamer; old ones disappear.
- Some streamers make VODs subscriber-only: the player shows a lock screen. Tell the
  user; do not work around it.
- Chat replay lines usually start with the VOD timestamp; the recorder uses it, which
  is more accurate than player time at 4x.
- Emotes (KEKW, OMEGALUL…) are images; the recorder reads their `alt`, so emote-only
  messages still count as laughter.
- Ads at the start and mid-VOD pause the video. `status().next` will say so; wait them
  out.
- The "Start watching" age gate can be clicked; that is not bypassing anything.

## Kick

| What | Link |
|------|------|
| VODs | `https://kick.com/<slug>/videos` |
| Clips | `https://kick.com/<slug>/clips` |
| One VOD | `https://kick.com/<slug>/videos/<uuid>` |

- Kick VODs have a chat replay, but it can be collapsed behind a button. Open it before
  `auto()`. The recorder auto-detects Kick's chat list even when its markup changes.
- `?t=` links don't always seek on Kick: always give the timecode as text too.
- If Kick shows a "verify you are human" check, the **user** solves it. Ask and wait.

## Rules

- Only VODs the user can open in their own browser. No third-party downloaders, no
  bypassing subscriber locks or geo-blocks.
- Don't post in chat, follow, like, or create clips on the platform for the user unless
  they explicitly ask.
