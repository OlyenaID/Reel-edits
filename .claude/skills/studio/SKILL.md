---
name: studio
description: Open the visual reel editor in the browser, with live preview, cut by the word, looks, sound and export buttons. Use when the user wants to see, scrub or click-edit their reel.
---

# Open the studio

1. Pick the project (ask if there are several in `projects/`).
2. Start it in the background so the conversation stays free:

       python reel.py studio <name>

   It opens http://127.0.0.1:8765 (use `--port` if that's taken). The first start makes a small
   preview copy of the footage, which takes a few seconds.
3. Tell the user:
   - **Cut tab**: drag across words → ✂ Cut (or Delete). Double-click a word to fix its spelling.
     ★ Emphasis, ＋ Look, ♪ Sound and "Use as hook" all work on the selection. Space plays/pauses.
   - **Visuals**: style pack, captions (words on screen, size, colours), zoom, and each look's type and text.
   - **Sound**: music, volume, automatic and placed sound effects.
   - **Finish**: render, carousel/stories/trial reels, CapCut layers, and links to every file.
4. While it is open, keep editing edit.json when they ask you for changes. Their preview updates by
   itself within ~2 seconds ("updated by Claude"). Don't render unless they ask for the file.
