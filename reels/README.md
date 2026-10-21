# Reels Editing Engine (free, DIY)

Drop in talking-head footage, chat with Claude Code, and get back:

- a **9:16 reel** with retakes, filler words and dead air cut, word-by-word animated captions,
  a hook title, punch-in zooms, loudness-normalised audio and optional background music
- a **cover image**
- a **carousel** (1080×1350 slides)
- **story clips** (split at natural cut points)
- **trial reels**: same video, different hooks / cold opens, to A/B test

All of it is in a **style pack** (`styles/*.json`) so every reel looks like yours.
Everything runs on your own computer with free tools. There's nothing to buy and no API keys.

## Setup (once)

You need Claude Code (included in a Claude Pro/Max plan), Python 3.10+, and ffmpeg.

**Mac**
```bash
brew install ffmpeg python
pip3 install faster-whisper pillow
```

**Windows**
```powershell
winget install Gyan.FFmpeg
winget install Python.Python.3.12
pip install faster-whisper pillow
```
(Gyan's ffmpeg build includes libass, which the captions need.)

Then:
```bash
cd reels
python reel.py check     # everything should say ok
claude                   # start Claude Code in this folder
```

The first transcription downloads the Whisper speech model (~500 MB for `small`). After that it works offline.

## Using it

In Claude Code, just say something like:

> Edit my new reel: ~/Desktop/IMG_4821.MOV

Claude transcribes it, shows you the transcript to fix misheard words, proposes cuts and a hook,
renders a preview, and iterates with you. Then: "make the carousel, stories and 3 trial reels".

Or drive it by hand:
```bash
python reel.py new myreel ~/Desktop/IMG_4821.MOV --prompt "names, brand words"
# edit projects/myreel/edit.json (see CLAUDE.md for every option)
python reel.py render myreel --preview
python reel.py render myreel
python reel.py repurpose myreel
```

Outputs land in `projects/myreel/out/`.

## Style packs

`styles/default.json` lists every setting. `soft-pastel` and `bold-punchy` are examples that only override
a few keys. Ask Claude "make me a style pack with my brand colours #… and #…", or copy one and edit it.
Custom fonts: see `fonts/README.md`.

## Tips

- Whisper sizes: `--model base` is faster, `--model medium` more accurate. `small` is a good default.
- Free music: YouTube Audio Library, Pixabay Music. Put the file in the project folder and set `"music": "track.mp3"`.
- Instagram's own trial reels feature is where you post the `trial_N.mp4` variants.
