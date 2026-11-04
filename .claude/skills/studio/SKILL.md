---
name: studio
description: Open the visual reel editor in the browser, with live preview, cut by the word, looks, sound and export buttons. Use when the user wants to see, scrub or click-edit their reel.
---

# Open the studio

1. Pick the project (ask if there are several in `projects/`).
2. Start it in the background so the conversation stays free:

       python reel.py studio <name>      # or `python reel.py app` for the home screen with every reel

   It opens http://127.0.0.1:8765/edit/<name> (use `--port` if that's taken). Next time they can just
   double-click `Reel Editor.bat` (Windows) or `Reel Editor.command` (Mac) instead.
3. Tell the user it walks them through 7 steps:
   1. **Words**: click a word to fix its spelling; "Fix it everywhere" for names.
   2. **Best takes**: lines said more than once, listen to each, keep one.
   3. **Trim**: select words like in a document and press Delete to cut them. Ctrl+Z undoes.
   4. **Look**: style, hook, captions, zoom.
   5. **Visuals**: select words → Headline / Counter / Full screen / Label / Image / Highlight.
   6. **Sound**: music and sound effects.
   7. **Make it**: render, download, carousel / trial reels / stories, CapCut layers.
4. While it is open, keep editing edit.json when they ask you for changes. Their preview updates by
   itself within ~2 seconds ("updated by Claude"). Don't render unless they ask for the file.
