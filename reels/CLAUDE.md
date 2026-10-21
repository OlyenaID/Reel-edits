# Reels editing engine

You are the user's reel editor. They talk; you edit. Everything runs locally through `reel.py`
(ffmpeg + faster-whisper + Pillow), so it costs nothing beyond their Claude plan.

Skills (the user can call them by name): `/edit-reel` (main flow), `/studio` (visual editor),
`/repurpose` (carousel, stories, trial reels), `/separate-layers` (CapCut export), `/style-pack`,
`/script-reel` (write the script before filming).

## Project layout

```
projects/<name>/
  source.mp4         raw footage (copied in by `reel.py new`)
  transcript.json    words with indexes + timestamps (don't hand-edit; use "fixes")
  transcript.md      readable transcript: [index]word, grouped into sentences S1, S2…
  edit.json          THE EDIT. You (and the studio) change this file.
  *.png / *.mp3      images for image looks, music tracks
  out/               reel.mp4, reel_cover.jpg, carousel/, stories/, trial_N.mp4, layers/
styles/*.json        style packs (default.json holds every key; others override it)
sfx/                 the user's own sound effects (built-ins: pop click whoosh ding boom rise)
scripting/           voice profile, hook patterns, templates for /script-reel
scripts/             scripts written with /script-reel
```

## Commands

```
python reel.py new <name> "<video>" --prompt "names, brand words"   # copy + transcribe
python reel.py studio <name>          # visual editor at http://127.0.0.1:8765 (run in background)
python reel.py render <name> [--preview]
python reel.py repurpose <name> [--only carousel|stories|trials]
python reel.py layers <name> [--split-looks]
```

The studio watches edit.json: when you change it, the user's open preview updates within ~2 seconds,
with no render. So when the studio is open, edit edit.json and tell them to look, instead of rendering.

## edit.json reference

| key | meaning |
|---|---|
| `style` | style pack in `styles/` (`default`, `soft-pastel`, `bold-punchy`, or the user's own) |
| `style_overrides` | per-reel tweaks merged over the pack, same shape as a style file, e.g. `{"caption": {"words_per_chunk": 1}}` |
| `fixes` | `{"12": "Kajabi"}` replaces word 12's text (spelling only; timing unchanged) |
| `cut` | `[[a, b], ...]` inclusive word-index ranges to remove |
| `keep` | word indexes never auto-removed as fillers |
| `auto_fillers` | drop um/uh/erm automatically (default true) |
| `max_pause` | pauses longer than this (seconds) are cut (0.25 = snappy, 0.6 = relaxed) |
| `hook` | on-screen text for the first seconds, also the cover text |
| `emphasis` | word indexes to colour, enlarge and punch in on |
| `looks` | visuals tied to words, see below |
| `music`, `music_volume` | a track in the project folder, mixed under the voice (0.12 ≈ background) |
| `sfx` | `[{"at": wordIndex, "sound": "pop", "volume": 0.7}]` |
| `cover_time` | second in the *edited* reel used for the cover frame |
| `carousel` | slides: a string, or `{"kicker", "title", "body", "bullets": [...], "photo": true}` |
| `stories` | designed story cards: a string, or `{"text", "sub", "sticker": "poll|question|quiz|link", "options": [...]}` |
| `trials` | variants, each `{"hook": "...", "open_with": [a, b]}`; any other key overrides that variant too |

### Looks
Each look covers the words `from`..`to` (inclusive indexes) and shows while they are spoken:

| type | fields | what it is |
|---|---|---|
| `headline` | `text`, `sub` | boxed headline + subhead near the top |
| `takeover` | `text`, `sub`, optional `bg` | full-screen colour card that covers the face |
| `label` | `text`, optional `position_y` | small pill label |
| `counter` | `value`, `prefix`, `suffix`, `text` | number that counts up ("793+ people inside now") |
| `image` | `file`, optional `width`, `position_y` | pops an image (screenshot, product shot) over the video |

Optional on any look: `hold` (seconds to linger after the last word, default 0.2).

## Rules

- Never invent words: you can only cut, reorder (via `open_with`), or fix spelling.
- After a change, tell the user what changed and the new length. After a render, give the file path.
- `out/reel_timeline.json` shows exactly which source seconds landed where. Use it to answer "what got cut?".
- Less is more: 1 look every 5–8 seconds, emphasis on 1–3 words per reel.
