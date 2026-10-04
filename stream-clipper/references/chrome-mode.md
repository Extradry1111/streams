# Chrome mode: finding moments with Claude in Chrome

Use this when there is **no shell** (claude.ai, the Claude app) but the Claude in Chrome
extension is connected, or for **Twitch**, where chat can't be downloaded directly.

## Setup

Read the **chrome-browser** skill (anthropic-skills:chrome-browser) and load the
`mcp__claude-in-chrome__*` tools with one ToolSearch call. If the extension is not
connected, tell the user to install/enable Claude in Chrome and stop.

Open a **new tab** and keep it the visible tab while the VOD plays: Chrome throttles video
in background tabs. Tell the user once: "Please leave this tab in front while I watch;
you can use other windows."

## Find the VOD

- Twitch: `https://www.twitch.tv/<login>/videos?filter=archive&sort=time` → first card.
- Kick: `https://kick.com/<slug>/videos` → first card.

Note title, date, length, link. Subscriber-only or deleted → tell the user, don't work
around it. More in `platforms.md`.

## Viewer clips (optional, fast)

Twitch `/clips?filter=clips&range=7d`, Kick `/<slug>/clips`. For clips from this VOD, note
title, views and VOD timecode. Top 20 by views at most.

## Watch the whole VOD

1. Open the VOD, let the player load. Clear overlays: age gate ("Start watching" is fine),
   "resume from…", wait out ads (never click them). Open the chat replay panel.
2. Run the **entire** contents of `scripts/clip_recorder.js` with the Chrome JavaScript
   tool. Expected reply: `installed on twitch|kick; call __clipRec.auto()`.
3. Run `__clipRec.auto()`.
4. Loop: wait ~2-3 min without touching the page, run `__clipRec.status()`, do what its
   `next` field says (keep waiting / check again in 15 s / deal with a paused video /
   open the chat panel / finished).

The script re-applies 4x when the player resets it, resumes after pauses, reattaches to a
re-rendered chat, slows to 2x if chat can't keep up, fills unwatched gaps and survives
reloads (paste it again and call `auto()`). A 4-hour VOD takes about an hour.

## Candidates and review

- `__clipRec.analyze()` → `{startTc, endTc, len, score, kind, laughs, clipCalls, url}`.
- For each, best first: `__clipRec.context(start - 30, end + 15)`, then
  `__clipRec.pause()`, `setRate(1)`, `seek(start)` and 5-8 screenshots ~10-15 s apart.
- Judge with `signals.md`.

## Making the clips

Cutting, subtitles and shorts need the toolbox (`scripts/clipper.py`, ffmpeg), which runs
in Claude Code or any session with a shell. In Chrome-only mode, deliver the report with
timecodes and say: "To get the actual 1080p clips with subtitles, run me in Claude Code
(or a session with a terminal) and say: make the clips from this report."
