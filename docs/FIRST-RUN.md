# First real run: a 15-minute check

The script passes an automated test in real Chromium against pages that imitate Twitch
and Kick (see `tests/`). Real Twitch and Kick haven't been tried yet, so do this once
before relying on it. It shows within a few minutes whether everything works on the
live sites.

## 1. Short Twitch VOD (about 5 min of your time)

1. Install the skill (README → Install) and make sure Claude in Chrome is connected.
2. Pick a streamer whose last VOD is **short (under 1 hour)** and has an active chat.
3. Ask Claude: `clip <streamer>'s last stream on twitch`.
4. Within the first 2 minutes check:

| Look for | Good | If not |
|----------|------|--------|
| The progress panel in the bottom-left of the VOD | Shows `watching 4x` and the chat count goes up | Send Claude a screenshot; it fixes things from `status().next` |
| `chat` in Claude's first status | A selector, not `null` | Open the chat replay panel and tell Claude "try again" |
| The VOD keeps playing at 4x | Timer jumps ~4 s per second | If it stays at 1x, Twitch blocks speed changes on that VOD: tell Claude "use 2x" |

5. When it finishes, open 2-3 links from the report. Each should start a few seconds
   before something happens.

## 2. Short Kick VOD

Same as above with `clip <streamer>'s last stream on kick`. Kick hides the chat replay
behind a button more often; Claude has to open it first.

## 3. If something breaks

Copy what Claude shows for `__clipRec.status()` plus a screenshot of the VOD page, and
open an issue or tell Claude in this repo: "stream-clipper failed on <link>: <status>".
Most failures come down to one CSS selector, which is a one-line fix in
`scripts/clip_recorder.js` (`CHAT_SELECTORS`).

## Known risks, and what already handles them

| Risk | How likely | Already handled by |
|------|------------|--------------------|
| Twitch/Kick renamed their chat markup | High over months | Auto-detect: picks the element that keeps receiving new lines (tested on unknown markup) |
| Player resets speed to 1x | Medium | Re-applied every second (tested) |
| Ads / pauses mid-VOD | High on Twitch | Auto-resume; after 20 s `status().next` asks Claude to look (tested) |
| Chat re-renders after a seek | Medium | Reattach + de-duplication (tested) |
| Page reload / crash | Low | Progress saved every 10 s and on unload; resumes from the first gap (tested) |
| Chat replay can't keep up at 4x | Medium | Slows to 2x on its own when chat goes silent |
| Tab in the background → Chrome slows video | High if you switch tabs | Keep the tab in front; Claude reminds you |
| VOD has no chat replay / chat is dead | Depends on streamer | Fallback: viewer clips + visual pass (lower confidence) |
| Joke that only works by sound | Always possible | Marked "needs a listen" instead of guessed |
