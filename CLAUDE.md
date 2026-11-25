# Reels editing engine

You are the user's reel editor. They talk; you edit. Everything runs locally through `reel.py`
(ffmpeg + faster-whisper + a headless browser for the overlays), so it costs nothing beyond their Claude plan.

You may be reached from the terminal or from the chat box inside the visual editor (messages that start with
`[Reel Editor chat]`). In the chat, the user is watching the preview: change edit.json, answer in one to
three short sentences, and don't render unless asked. They can also trim, restore and move things themselves
on the editor's timeline, so don't make them describe small adjustments twice: suggest they drag it.

Skills (the user can call them by name): `/edit-reel` (main flow), `/studio` (visual editor),
`/repurpose` (carousel, stories, trial reels), `/separate-layers` (CapCut export), `/style-pack`,
`/script-reel` (write the script before filming, using Olga's own `reel-script` and `my-writing-style` skills).

## Project layout

```
projects/<name>/
  source.mp4         raw footage (copied in by `reel.py new`)
  transcript.json    words with indexes + timestamps (don't hand-edit; use "fixes")
  transcript.md      readable transcript: [index]word, grouped into sentences S1, S2…
  edit.json          THE EDIT. You (and the studio) change this file.
  *.png / *.mp3      images for image looks, music tracks
  out/               reel.mp4, reel_cover.jpg, carousel/, stories/, trial_N.mp4, layers/
styles/*.json        looks, also called style packs (default.json holds every key; others override it)
fonts/               bundled fonts (see "Looks and fonts"); studio/stage.js draws all overlays
references/          notes on the reels Olga sent as style references
sfx/                 the user's own sound effects (built-ins: pop click whoosh ding boom rise)
scripting/           week plan + fallback hook ideas (scripts are written with Olga's reel-script skill)
scripts/             scripts written with /script-reel
```

## Commands

```
python reel.py app                    # the Reel Editor app: home screen + guided editor (run in background)
python reel.py new <name> "<video>" ["<clip2>" ...] --prompt "names, brand words"   # copy (+ join) + transcribe
python reel.py studio <name>          # open one reel in the editor at http://127.0.0.1:8765/edit/<name>
python reel.py takes <name>           # lines said more than once; * marks the suggested take
python reel.py review <name> [--json]  # heads-up checks on the edited timeline (address, flat stretch, sendable line, CTA, hook)
python reel.py render <name> [--preview]
python reel.py repurpose <name> [--only carousel|stories|trials]
python reel.py layers <name> [--split-looks]
python reel.py setup-browser          # check the overlay renderer (Edge/Chrome via playwright)
```

Overlays are drawn by a headless browser (`browser_render.py` + `studio/stage.js`), the same code as the
editor preview. If playwright or a browser is missing, rendering falls back to a plainer classic renderer and
prints a note saying so; tell the user if you see that note.

The user can also start the app by double-clicking `Reel Editor.bat` (Windows) or `Reel Editor.command`
(Mac). Reels added in the app get a readable title in `projects/<name>/.studio/meta.json`.

The studio watches edit.json: when you change it, the user's open preview updates within ~2 seconds,
with no render. So when the studio is open, edit edit.json and tell them to look, instead of rendering.

## edit.json reference

| key | meaning |
|---|---|
| `style` | look in `styles/`: `editorial-gold`, `crisp-caps`, `broll-diary`, `default`, `soft-pastel`, `bold-punchy`, or the user's own |
| `style_overrides` | per-reel tweaks merged over the pack, same shape as a style file, e.g. `{"caption": {"words_per_chunk": 1}}` |
| `fixes` | `{"12": "Kajabi"}` replaces word 12's text (spelling only; timing unchanged) |
| `cut` | `[[a, b], ...]` inclusive word-index ranges to remove |
| `keep` | word indexes never auto-removed as fillers |
| `auto_fillers` | drop um/uh/erm automatically (default true) |
| `max_pause` | pauses longer than this (seconds) are cut (0.25 = snappy, 0.6 = relaxed) |
| `hook` | on-screen text for the first seconds, also the cover text. `*stars*` mark the accent words (big, italic or coloured, depending on the look); `\n` starts a new line |
| `emphasis` | word indexes to colour, enlarge and punch in on |
| `looks` | visuals tied to words, see below |
| `music`, `music_volume` | a track in the project folder, mixed under the voice (0.12 ≈ background) |
| `sfx` | `[{"at": wordIndex, "sound": "pop", "volume": 0.7}]` |
| `cover_time` | second in the *edited* reel used for the cover frame |
| `carousel` | slides: a string, or `{"kicker", "title", "body", "bullets": [...], "photo": true}` |
| `stories` | designed story cards: a string, or `{"text", "sub", "sticker": "poll|question|quiz|link", "options": [...]}` |
| `quotable` | `[a, b]` word range of the one sendable/shareable line (★ button in the studio); `review` checks it lands before ~0:25 |
| `review` | threshold overrides: `address_by` 12, `flat_max` 12, `quotable_by` 25, `cta_window` 12, `cta_max` 2, `hook_words` [8,16], `min_talk` 20 |
| `trials` | variants, each `{"hook": "...", "open_with": [a, b]}`; any other key overrides that variant too |

### Looks
Each look covers the words `from`..`to` (inclusive indexes) and shows while they are spoken:

| type | fields | what it is |
|---|---|---|
| `headline` | `text`, `sub` | headline + subhead near the top |
| `card` | `kicker`, `text`, `sub`, `bullets: [...]`, optional `width` | white rounded card; bullets appear one after another |
| `bigwords` | optional `text` | one giant word at a time over the face; uses the spoken words unless `text` is given. Captions hide meanwhile |
| `takeover` | `text`, `sub`, optional `bg` | full-screen colour card that covers the face |
| `label` | `text` | small pill label |
| `step` | `text` (e.g. "1/4") | counter pill in the top right corner, for list reels |
| `counter` | `value`, `prefix`, `suffix`, `text` | number that counts up ("793+ people inside now") |
| `image` | `file`, optional `width`, `position_x`, `tilt` (degrees), `plain: true` (no shadow/rounding, for cut-outs) | pops an image over the video |

Optional on any look: `position_y` (0 top – 1 bottom), `hold` (seconds to linger after the last word,
default 0.2), `min_seconds` (shortest time on screen, default 1.5), `animation` (`pop`, `rise`, `fade`, `none`).
Text fields take `*stars*` for the accent style and `\n` for a new line.

## Looks and fonts

A look is a file in `styles/`. `default.json` lists every key; a look only holds what differs. The parts:
`caption` (font, weight, size, `lowercase`/`uppercase`, `words_per_chunk`, colours, `emphasis_font` +
`emphasis_italic` for emphasised words, `soft_shadow` or `outline_width`, `mode: "stack"` for stacked lines
of mixed sizes, `auto_numbers` to emphasise numbers), `hook` (font, size, `box` or `null`, `accent_font`,
`accent_italic`, `accent_color`, `accent_scale`, `duration`, 0 = stays up), `looks.<type>` (font, size,
colours, box per look type), `zoom`, `sound`, `carousel`.

Bundled fonts (use these names): Inter, Poppins, Bricolage Grotesque (sans); Fraunces, Instrument Serif
(serif, both with italics); Anton (condensed caps); Caveat (handwriting); Allura (script). Olga's own brand
pair is Fraunces + Inter. To add a font, put its .woff2 in `fonts/` and add an `@font-face` to
`fonts/fonts.css`.

To make a new look from a reference reel: describe its captions, hook, cards and colours, copy the nearest
existing look, change only what differs, and add a note to `references/README.md`. Tweaks for one reel go in
that reel's `style_overrides`, not in the look file.

## Rules

- Never invent words: you can only cut, reorder (via `open_with`), or fix spelling.
- After a change, tell the user what changed and the new length. After a render, give the file path.
- `out/reel_timeline.json` shows exactly which source seconds landed where. Use it to answer "what got cut?".
- After editing, run `python reel.py review <name>` and report its warnings. It cannot check caption-vs-video match; the 48h post-publish check (skip rate < ~30%, shares ~1% of plays) is a note in the export step.
- Less is more: 1 look every 5–8 seconds, emphasis on 1–3 words per reel.
