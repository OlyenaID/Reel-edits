---
name: script-reel
description: Write a reel script before filming, or plan a week of reels, using Olga's own reel-script skill and writing style, then hand the script to the editing engine. Use when the user asks for reel ideas, hooks, a script, or "what should I post this week".
---

# Script a reel

The script itself is written by Olga's own skills, not by this one:
- **`reel-script`**: her tested template (brief, lane, hook, body, door, checks) and option codes.
- **`my-writing-style`**: her voice for anything she'll say or post as herself.

This skill only connects them to the reels engine.

## 1. Write it
Invoke the `reel-script` skill (and `my-writing-style` for her voice) and follow it fully: its steps,
its checks and its option-code logging. Don't swap in other templates or hook lists.

If `reel-script` isn't available in this Claude Code session, say so plainly and ask whether to continue
with the fallback hook ideas in `scripting/hooks.md`. Don't silently imitate her template.

## 2. Save it for filming and editing
Save the finished script as `scripts/YYYY-MM-DD-<slug>.md`, keeping:
- the option codes `reel-script` assigned, so results can be logged against them later
- the on-screen hook text (≤ 7 words, for edit.json `hook`)
- bracketed visual notes per line where a look would help, e.g. `[headline: "Mistake #1"]`,
  `[counter: 800+ people inside]`, `[takeover: "STOP"]`, `[image: screenshot of …]`

## 3. After filming
When the footage for this script goes through `/edit-reel`, read the saved script first: use its hook,
turn the bracketed notes into `looks` on the matching words, and copy its option codes into
`projects/<name>/script-codes.txt` so the reel can be traced back to the test.

## A week of reels
Use `scripting/week-plan.md` for the mix of days, and write every reel in it with `reel-script`.
Save as `scripts/week-YYYY-MM-DD.md`.
