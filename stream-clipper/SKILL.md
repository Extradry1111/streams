---
name: stream-clipper
description: >-
  Finds the funniest moments in Twitch and Kick stream recordings (VODs) and returns
  ready-to-cut clip candidates of 30-120 seconds with exact timecodes and links. Works
  through the Claude in Chrome extension: opens the streamer's channel, picks the VOD,
  plays the whole thing muted at 4x while recording the chat replay, finds the spikes of
  laughter and "clip it" in chat, cross-checks viewer clips, then looks at every candidate
  with screenshots and keeps the best. Use it whenever someone asks to find funny moments,
  highlights, clips, shorts or TikToks in a stream, VOD, past broadcast or stream recording,
  or says "clip xqc" / "clip this VOD" for Twitch or Kick, in any language
  (клипы со стрима, нарезка, смешные моменты, хайлайты).
---

# stream-clipper

Goal: from one stream recording, a ranked list of 5-15 moments, each 30-120 s long and
funny **on its own** (no hour of context needed), with exact start/end and a link that
opens the VOD at that spot.

This stage is finding and picking moments only. Subtitles and titles come later
(`references/next-steps.md`); do not do them unless asked.

## How Claude "watches" a stream (be upfront about this)

Claude sees the page and screenshots but **cannot hear audio**. So watching is done with
three signals that together beat frame-by-frame viewing:

1. **Chat replay.** Viewers react to funny things 2-8 s later: KEKW, LUL, "ахахах",
   "ору", "clip it". `scripts/clip_recorder.js` plays the full VOD muted at 4x and logs
   every chat line against video time. Coverage is tracked in %; the job is not done
   until it is ~100%.
2. **Viewer clips** of this VOD. Already-confirmed moments; most viewed first.
3. **Visual check.** Every candidate is reviewed with screenshots + the chat in that
   window.

A joke that is funny only by sound may be missed or impossible to judge. Mark such
moments **"needs a listen"** and say so. Never invent what someone said.

## Inputs

- **Who / what.** A streamer (`clip xqc`, `clip kick.com/somebody`) or a VOD link.
  No streamer named → use `streamers.md`; if it is empty, ask once.
  "clip all my streamers" → go through `streamers.md` one streamer at a time.
- **Which VOD.** Default: the latest finished one. Accept "yesterday's", "the one
  with <game>", or a link.
- Options the user may give: number of clips (default up to 10), length range
  (default 30-120 s), language of the report (default: the user's language).

## Step 0. Browser

Read the **chrome-browser** skill (anthropic-skills:chrome-browser) and load the
`mcp__claude-in-chrome__*` tools with one ToolSearch call. If the extension is not
connected, tell the user to install/enable Claude in Chrome and stop.

Open a **new tab** for the work and keep it the visible tab while the VOD plays: Chrome
throttles video in background tabs. Tell the user once: "Please leave this tab in front
while I watch; you can use other windows."

## Step 1. Find the VOD

Links and quirks: `references/platforms.md`.

- Twitch: `https://www.twitch.tv/<login>/videos?filter=archive&sort=time` → first card.
- Kick: `https://kick.com/<slug>/videos` → first card.

Note title, date, length, link. No VODs (deleted or subscriber-only) → tell the user
and offer another VOD/streamer. Never try to get around access restrictions.

## Step 2. Viewer clips (fast signal, optional)

Open the channel's clips for the period of the stream (Twitch `/clips?filter=clips&range=7d`,
Kick `/<slug>/clips`). For clips **from this VOD**, note title, views and VOD timecode
(Twitch clip pages link to the full video with `?t=`). Top 20 by views at most. If there
are none, skip.

## Step 3. Watch the whole VOD

1. Open the VOD and let the player load. Clear overlays: age gate ("Start watching" is
   fine to click), "resume from…", wait out pre-roll ads (never click ads).
2. Make sure the chat replay panel is open and visible (expand it if collapsed).
3. Run the **entire** contents of `scripts/clip_recorder.js` with the Chrome
   JavaScript tool. Expected reply: `installed on twitch|kick; call __clipRec.auto()`.
4. Run `__clipRec.auto()`.
5. Then loop: wait ~2-3 min (do not touch the page), run `__clipRec.status()`, and do
   exactly what its `next` field says. It covers every case:
   - `Watching… ~N min left` → keep waiting.
   - `Looking for the chat…` → check again in 15 s (it auto-detects unknown layouts).
   - `Video has been paused…` → screenshot; wait out an ad or close the prompt; check again.
   - `Chat replay not found…` → follow the hint; if the VOD truly has no chat replay,
     use "No chat" in `references/signals.md`.
   - `Finished.` → go to step 4.

   The script handles the rest by itself: it re-applies 4x when the player resets the
   speed, resumes after short pauses, reattaches when chat re-renders, slows to 2x if
   chat can't keep up, fills unwatched gaps at the end, and saves progress so a page
   reload loses nothing (paste the script again and call `auto()` to resume).

A 4-hour VOD takes about an hour. Give the user the ETA from `status().etaMin` once,
not on every check.

## Step 4. Candidates

`__clipRec.analyze()` returns up to 15 windows:
`{startTc, endTc, len, score, kind, laughs, clipCalls, url}`, already cut to 30-120 s
with ~20 s of setup before the chat reaction. Pass options if the user asked for
something else: `analyze({ top: 20, minLen: 20, maxLen: 60 })`.

Merge with viewer clips: a clip within ±60 s of a candidate makes it stronger; a
viewer clip with no chat spike is still a candidate.

How to read `score` / `kind` and what to drop on sight: `references/signals.md`.

## Step 5. Check every candidate yourself

Best score first, until you have enough good ones:

1. `__clipRec.context(start - 30, end + 15)` and read **what** chat is laughing at.
   Chat often names it ("he fell off the bridge", "the cat").
2. `__clipRec.pause()`, `__clipRec.setRate(1)`, `__clipRec.seek(start)`, then 5-8
   screenshots ~10-15 s apart until `end`. Look at the webcam (face, jumping up,
   covering face), the game, on-screen text.
3. Decide with the checklist in `references/signals.md`: understandable without
   back-story? where does the setup really start and the reaction end? Adjust the
   bounds (stay within the length range). Drop ads, alerts, BRB screens, raids.
4. Chat reacted to sound and nothing is visible → keep it marked "needs a listen".

## Step 6. Report

Use `references/report-template.md`: a table, best first, with timecode, length, what
happens, why it's funny, signals, link. "What happens" = only what you saw on
screenshots and read in chat. Finish with one line: % watched, chat lines processed,
how many candidates were dropped and why.

If file tools are available, also save it to `clips/<streamer>/<YYYY-MM-DD>-<vod id>.md`
with the raw `analyze()` output next to it as `.json`.

Then ask which moments to take further (subtitles, titles) and stop.
