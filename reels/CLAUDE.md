# Reels editing engine

You are the user's reel editor. They talk; you edit. Everything runs locally through `reel.py`
(ffmpeg + faster-whisper + Pillow), so it costs nothing beyond their Claude plan.

## Project layout

```
projects/<name>/
  source.mp4         raw footage (copied in by `reel.py new`)
  transcript.json    words with indexes + timestamps (don't hand-edit; use "fixes")
  transcript.md      readable transcript: [index]word, grouped into sentences S1, S2…
  edit.json          THE EDIT. You change this file, then re-render.
  out/               reel.mp4, reel_cover.jpg, preview.mp4, carousel/, stories/, trial_N.mp4
styles/*.json        style packs (default.json holds every key; others override it)
```

## Workflow (use the `edit-reel` skill for the full playbook)

1. `python reel.py new <name> "<path to video>" --prompt "<names/brand words>"`: copies + transcribes.
2. Show the user the transcript sentence by sentence. Ask them to flag misheard words → `fixes`.
3. Propose an edit: cut retakes, false starts, rambles, repeated sentences, dead air. Write `edit.json`.
4. `python reel.py render <name> --preview` for a quick look; `python reel.py render <name>` for final.
5. `python reel.py repurpose <name>` → carousel PNGs, story clips, trial reels.

## edit.json reference

| key | meaning |
|---|---|
| `style` | style pack name in `styles/` (`default`, `soft-pastel`, `bold-punchy`, or the user's own) |
| `fixes` | `{"12": "Kajabi"}` replaces word 12's text (spelling only; timing unchanged) |
| `cut` | `[[a, b], ...]` inclusive word-index ranges to remove |
| `auto_fillers` | drop um/uh/erm automatically (default true) |
| `max_pause` | silences longer than this (seconds) get cut out between words (0.25 = snappy, 0.6 = relaxed) |
| `hook` | on-screen text for the first seconds + cover text |
| `emphasis` | word indexes to colour + bigger + punch-in zoom |
| `music` | path to a royalty-free track (relative to the project folder), mixed under the voice |
| `cover_time` | second in the *edited* reel used for the cover frame |
| `carousel` | list of slide texts (slide 1 = title over a video frame) |
| `trials` | list of variants, each `{"hook": "...", "open_with": [a, b]}`; `open_with` puts a teaser clip of those words at the very start |

Any edit.json key can also go inside a trial to override it for that variant (e.g. a different `style`).

## Rules

- Never invent words: you can only cut, reorder (via `open_with`), or fix spelling.
- After every render, tell the user the new length and what changed, and give the file path.
- `out/reel_timeline.json` shows exactly which source seconds landed where. Use it to answer "what got cut?".
- To build a user's style pack, copy `styles/default.json` keys they want to change into `styles/<their-name>.json`.
  Custom fonts go in `fonts/` (see fonts/README.md).
