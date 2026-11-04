---
name: edit-reel
description: Edit a talking-head video into a finished Instagram/TikTok reel (cuts, captions, hook, looks, sound, cover). Use when the user drops in footage or asks to edit, cut or caption a reel, or to change one.
---

# Edit a reel

Work in the repo root (where `reel.py` lives). `CLAUDE.md` has the full edit.json reference.

## 0. First time only
Run `python reel.py check`. If anything is MISSING, walk the user through README.md "Setup".

## 1. Bring in the footage
Ask for the video path (they can drag the file into the terminal). Pick a short project name.
Ask for names / brand words that appear in the video and pass them as `--prompt`.

    python reel.py new <name> "<path>" --prompt "Meg, Kajabi, Startup Mom"
    python reel.py new <name> "<clip1>" "<clip2>" "<clip3>" --prompt "..."   # several clips, joined in this order

Ask if this footage was filmed from a script in `scripts/` (written with `/script-reel`). If so, read it:
its hook, bracketed look notes and option codes are the starting point (see the script-reel skill, step 3).

## 2. Transcript review
Read `projects/<name>/transcript.md`. Show it back as clean numbered sentences (no index noise).
Ask: "Any words I misheard?" Put corrections in `fixes`.

## 3. Rough cut
Run `python reel.py takes <name>` first: it lists every line said more than once, with the suggested take
marked `*`. Then propose, in plain language:
- retakes: for each group, keep the better (usually the last full) take and cut the rest
- false starts, "let me start again", tangents, a slow warm-up before the real first line
- a hook (≤ 7 words, from the strongest line), and 1–3 emphasis words
Get a yes, write edit.json.

## 4. Look at it
Offer the studio (`/studio`): live preview, no render, and they can click words to cut themselves.
Otherwise: `python reel.py render <name> --preview` (fast, half-res).

## 5. Visuals and sound
Suggest 2–5 looks where they help the viewer: a headline on each new point, a counter for a number,
a takeover for the punchline, an image when they mention something visual (ask them for the file).
Suggest music (ask for a royalty-free file) and sound effects (whoosh on looks, pop on emphasis).
Apply only what they agree to.

## 6. Requests in plain words
"tighter" → lower `max_pause` / cut more; "captions bigger" → `style_overrides.caption.size`;
"one word at a time" → `words_per_chunk: 1`; "cut the bit about X" → find it in transcript.md, add to `cut`;
"move the counter earlier" → change that look's `from`/`to`; "less zoom" → `zoom.punch_in` lower.

## 7. Finish
    python reel.py render <name>

Report length and `projects/<name>/out/reel.mp4` + `reel_cover.jpg`. Then offer `/repurpose`
(carousel, stories, 3 trial reels) and `/separate-layers` (to finish in CapCut).
