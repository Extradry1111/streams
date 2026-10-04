# Telling a funny moment from a merely loud one

## What analyze() returns

- `score`: how many times busier chat is here than usual for the surrounding ±5 min,
  with bonuses for laughter (×2), "clip it" (×3) and hype (×0.5).
  Rough guide: < 2 noise · 2-4 worth a look · > 4 something definitely happened.
- `kind`:
  - `funny`: most messages are laughter. The main target.
  - `clip-call`: people ask for a clip. Often funny, sometimes just epic (a great play).
  - `hype`: a spike without laughter: donation, raid, win, jump scare, chat argument.
    Check it, but usually drop it unless the screen shows something clearly funny.
- `laughs`, `clipCalls`, `msgs`: raw counts in the window.
- `url`: VOD link that opens at `start`.

The first and last 5 minutes of the stream are skipped automatically (hello/bye spam);
pass `analyze({ skipEdges: 0 })` if something there matters.

## Drop on sight

- Raids, gifted-sub waves, donation alerts: chat spams the same line. Visible in
  `context()`: identical messages, "welcome raiders", names.
- Giveaways and polls: spam of a command or numbers (`!join`, `1`, `2`).
- Spikes during ads or a "BRB" / "AFK" screen.
- Moments that need 10 minutes of back-story to get.

## What makes a good clip

1. **Clear from the first second**, or within 5-10 s. A Shorts/TikTok viewer doesn't
   know the streamer.
2. **Setup and payoff**: something goes wrong / unexpected line → streamer reacts
   (laughs, yells, freezes) → chat reacts.
3. **Visible reaction**: face on the webcam, jumping up, falling. Pure gameplay with no
   webcam and nothing happening on screen is rarely funny out of context.
4. **No fat**: cut everything before the setup and after the laughter dies. 30-60 s is
   best; up to 120 s only if the story really is that long.
5. Don't cut mid-sentence: start in a pause before the event, end after the reaction.

## Setting the bounds

- Chat reacts 2-8 s after the event, so `analyze()` already starts 20 s before the
  spike. On review, move the start to where the setup actually begins.
- Two spikes within 1-2 min about the same thing → one clip (≤ 120 s). About different
  things → two clips.

## No chat (or almost none)

Less than about one message a minute means the chat signal is useless. Fall back to a
visual pass; tell the user it is slower and less reliable.

1. Viewer clips first; if there are some, they are the main source.
2. Otherwise step through the VOD every 60 s (`seek`, screenshot) and mark frames where
   something unusual happens: streamer jumped up / laughing / face in hands, a death or
   fail on screen, a guest in frame, big on-screen text.
3. Around marked points go denser (every 5-10 s) to find setup and end.
4. Mark in the report that these were found without chat or audio, so confidence is
   lower.
