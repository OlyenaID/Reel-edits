---
name: edit-reel
description: Edit a talking-head video into a finished Instagram/TikTok reel (captions, hook, cuts, zooms, cover), and repurpose it into a carousel, stories and trial reels. Use when the user drops in footage, asks to edit/cut/caption a reel, or wants to change the style.
---

# Edit a reel

Work in the `reels/` folder (where `reel.py` lives). Read `CLAUDE.md` for the edit.json reference.

## 0. First time only
Run `python reel.py check`. If anything is MISSING, walk the user through README.md "Setup".

## 1. Bring in the footage
Ask for the video path (they can drag the file into the terminal). Pick a short project name.
Ask for any names / brand words that appear in the video and pass them as `--prompt`.

    python reel.py new <name> "<path>" --prompt "Meg, Kajabi, Startup Mom"

## 2. Transcript review
Read `projects/<name>/transcript.md`. Show it back to the user as clean sentences (S1, S2…), without the
index noise. Ask: "Any words I misheard?" Put corrections in `fixes`.

## 3. Propose the cut
Read the transcript as an editor would and propose, in plain language:
- retakes: when a sentence is said twice, keep the better (usually the last) take
- false starts, "wait let me start again", rambling tangents, a weak opening before the real hook
- the strongest line for the hook (`hook` text, ≤ 7 words) and 1–3 words worth `emphasis`
Get a yes, then write edit.json. Keep a short changelog in your reply, not in the file.

## 4. Render
    python reel.py render <name> --preview     # ~seconds, half-res, for checking cuts
    python reel.py render <name>               # final 1080x1920 + cover

Report new length and the output path. Iterate on feedback ("tighter", "cut the bit about X",
"captions bigger", "less zoom") by changing edit.json or the style pack, then re-render.

## 5. Repurpose (when asked, or offer once the reel is approved)
Fill in edit.json:
- `carousel`: 5–8 slides that teach the reel's point as text. Slide 1 = hook, last = call to action.
- `trials`: 3 variants with different hooks; for one, use `open_with` on the punchiest line as a cold open.
Then:

    python reel.py repurpose <name>                 # all
    python reel.py repurpose <name> --only trials   # just one kind

## Style packs
"Make it look like my brand": ask for 2–3 hex colours, caption case (UPPER/normal), words on screen at
once, and font. Write `styles/<brand>.json` with only the keys that differ from default.json, then set
`"style": "<brand>"` in edit.json. That pack then applies to every future reel.
