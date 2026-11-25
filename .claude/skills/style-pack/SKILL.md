---
name: style-pack
description: Create or change the user's style pack (caption look, colours, hook box, looks, zoom, carousel colours, auto sound effects) so every reel matches their brand. Use when they say "make it look like my brand" or want a new look.
---

# Looks (style packs)

A look is a file in `styles/`. `styles/default.json` lists every setting; a look holds only what differs.
`CLAUDE.md` ("Looks and fonts") has the keys and the bundled fonts. Existing looks: `editorial-gold`,
`crisp-caps`, `broll-diary`, plus the older `soft-pastel` and `bold-punchy`.

## From a reference reel (what Olga prefers)
She sends a reel she likes instead of picking fonts from a list.
1. Watch it. If the vidIQ connector is available, use its short-form watch tool with a prompt asking for
   caption typeface, case, colours, position, words at once, animation, overlays and pacing. Otherwise ask
   her for two or three screenshots.
2. Write what you saw into `references/README.md` (a few bullets, same shape as the existing entries).
3. Copy the nearest existing look to `styles/<new-name>.json`, give it a `label`, and change only what
   differs. Pick the closest bundled font; say which font you chose and why, in one line.
4. Set it on the open reel (`"style": "<new-name>"`) so she sees it in the preview, and ask what's off.

## From a description
Ask, one or two at a time: 2–3 brand colours, captions (one word or a few; UPPER or lower), zooms
(none / subtle / punchy), sounds on visuals. Then write the look as above.

## Rules
- Tweaks made in the editor's Look step live in the reel's `style_overrides`; "Save this look as my style"
  there turns them into a look file.
- Never hand-edit `default.json` to restyle one reel.
- If something in a reference needs a visual the engine can't draw yet (animated notebook, clothesline,
  light trail…), say so plainly and note it in `references/README.md` as a wish.
