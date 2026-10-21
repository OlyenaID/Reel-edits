---
name: repurpose
description: Turn a finished reel into a carousel, designed stories, story clips and 3 trial reels in the user's style pack. Use after a reel is approved, or when the user asks for carousels, stories or trial reels.
---

# Film once, post six ways

Read the project's transcript and edit.json. Draft everything in chat first, then write it to edit.json
on approval.

## Carousel (`carousel`)
5–8 slides that teach the reel's point as text. They should make sense without the video.
- Slide 1: the hook, over a photo: `{"title": "3 mistakes killing your reels", "photo": true}`
- Middle slides, one idea each: `{"kicker": "reason one: your", "title": "hook", "bullets": ["say who it's for", "make a promise", "do it in 2 seconds"]}`
  (kicker ≤ 5 words, title 1–4 words, 2–4 bullets of ≤ 6 words)
- Last slide: one call to action ("Save this for your next reel", "Comment GUIDE and I'll send it").

## Stories (`stories`)
3–5 cards that warm people up for the reel:
1. a teaser question with a poll: `{"text": "Do you script your reels?", "sticker": "poll", "options": ["Always", "Never"]}`
2. a behind-the-scenes line: `{"text": "Filmed this in one take at nap time", "sub": "new reel tonight"}`
3. the share: `{"text": "New reel is up ↓", "sticker": "link"}`
The sticker box is a placeholder; tell them to add the real Instagram sticker on top.
`repurpose` also splits the reel into story-length clips.

## Trial reels (`trials`)
Three variants of the same reel to test hooks on non-followers (Instagram's Trial Reels):
- A: a different hook text with the same opening
- B: a curiosity or contrarian hook
- C: a cold open: `"open_with": [a, b]` plays the punchiest line (word indexes) first, then the reel
Hooks ≤ 7 words. Pull ideas from `scripting/hooks.md`.

## Run
    python reel.py repurpose <name>                  # everything
    python reel.py repurpose <name> --only carousel  # or stories / trials

Outputs: `out/carousel/slide_NN.png`, `out/stories/card_NN.png` + `story_NN.mp4`, `out/trial_N.mp4`.
