---
name: style-pack
description: Create or change the user's style pack (caption look, colours, hook box, looks, zoom, carousel colours, auto sound effects) so every reel matches their brand. Use when they say "make it look like my brand" or want a new look.
---

# Style pack

`styles/default.json` lists every setting. A pack only contains the keys that differ from it.

1. Ask, one or two at a time:
   - 2–3 brand colours (hex, or describe them and you suggest hex values)
   - captions: one word at a time or 2–4 words? UPPERCASE? big and bold, or clean and small?
   - punch-in zooms: none, subtle (1.08), or punchy (1.15+)?
   - sound effects on looks/emphasis: none, whoosh, pop?
   - a font? (free Google Font, put the file in `fonts/`, see fonts/README.md)
2. Write `styles/<their-brand>.json` with only the changed keys, e.g.:
   ```json
   {"name": "my-brand",
    "caption": {"words_per_chunk": 1, "uppercase": true, "highlight": "#F2B5C8"},
    "hook": {"box": "#2E2A27", "color": "#FFFFFF"},
    "looks": {"takeover": {"bg": "#2E2A27"}, "label": {"box": "#F2B5C8"}},
    "carousel": {"bg": "#2E2A27", "accent": "#F2B5C8"},
    "sound": {"look_sfx": "whoosh"}}
   ```
3. Set `"style": "<their-brand>"` in the current reel's edit.json and show it (studio or preview render).
4. Tweaks made in the studio's Visuals tab live in `style_overrides`. "Save my look as a style pack"
   in the studio turns them into a pack file.
