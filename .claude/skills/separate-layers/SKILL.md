---
name: separate-layers
description: Export the reel as separate layers (clean video + transparent captions, hook and looks) to finish or tweak in CapCut, Premiere or Final Cut. Use when the user wants to move or restyle one piece in another editor.
---

# Separate layers

Ask which pieces they want on their own layer. A checklist helps: captions, hook, every look together,
or each look separately.

    python reel.py layers <name>                 # base + captions + hook + looks
    python reel.py layers <name> --split-looks   # base + captions + hook + one file per look

Output in `projects/<name>/out/layers/`:
- `base.mp4`: cut, zoomed, sound-mixed video with no text
- `captions.mov`, `hook.mov`, `looks.mov` or `look_01_headline.mov`…: transparent overlays, full length
- `captions.srt`: plain captions, if they'd rather use CapCut's own caption styles

Tell them: in CapCut, put `base.mp4` on the main track and each `.mov` on its own overlay track,
all starting at 0:00. Each layer can then be moved, resized, or deleted on its own.
