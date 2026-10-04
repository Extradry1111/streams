# Report template

Write the report in the user's language.

```markdown
# <Streamer> — <stream title>

<Platform> · <date> · <length> · <VOD link>
Watched: <coveragePct>% · chat lines: <N> · viewer clips used: <K>

| # | Timecode | Length | What happens | Why it's funny | Signals | Link |
|---|----------|--------|--------------|----------------|---------|------|
| 1 | 1:02:03–1:02:58 | 55 s | Explains his "pro strategy" and falls off the bridge the same second | "I'm a pro" → instant fail, jumps out of his chair | score 9.1, 140 laughs, 12× "clip it", viewer clip 3.4k views | https://www.twitch.tv/videos/123?t=1h02m03s |
| 2 | ... | | | | | |

Needs a listen (chat laughed at audio, nothing visible):
- 2:14:40–2:15:30 — chat: "his voice LMAO", nothing on screen

Dropped: 7 (raid ×2, donation alerts ×3, stream intro, needs back-story).
```

Rules:
- Best first; the number is the priority.
- "What happens": only what you saw on screenshots and read in chat.
- Signals: numbers from `analyze()` and viewer clips, so the user sees how well each
  moment is confirmed.
