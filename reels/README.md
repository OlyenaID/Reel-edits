# Reels Editing Engine (free, DIY)

Your style. Your footage. Minus the editing hours. Built with free tools, running on your own computer.
There's nothing to buy and no API keys.

Drop in talking-head footage, chat with Claude Code (or click around the studio), and get:

- **A finished 9:16 reel**: retakes, um/uh and dead air cut; word-by-word animated captions; a hook
  title; punch-in zooms; loudness-levelled audio; music; sound effects; a cover image
- **Looks** on any line: headline + subhead, full-screen takeover, label, count-up card
  ("793+ people inside now"), image pop-up
- **The studio**: a visual editor in your browser. Cut your reel by the word, preview instantly with
  no render, and swap looks, captions, colours and sounds. Changes Claude makes show up live too.
- **Post it six ways**: carousel slides, designed story cards + story clips, and 3 trial reels with
  different hooks
- **Separate layers for CapCut**: clean video + transparent caption / hook / look layers
- **Style packs** so every reel looks like you, and **scripts** written with your own `reel-script` skill before you film

## Setup (once, ~10 minutes)

You need Claude Code (included in a Claude Pro/Max plan), Python 3.10+, and ffmpeg.

**Mac** (install [Homebrew](https://brew.sh) first if you don't have it)
```bash
brew install ffmpeg python
pip3 install faster-whisper pillow
```

**Windows** (PowerShell)
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

In Claude Code, just talk:

> Edit my new reel: ~/Desktop/IMG_4821.MOV

Claude transcribes it, shows you the transcript to fix misheard names, proposes cuts and a hook, and
offers to open the studio. Other things to say:

| Say | What happens |
|---|---|
| `/studio` | opens the visual editor in your browser |
| "cut the part about my old job" / "tighter" / "captions one word at a time" | edits the reel, and the studio preview updates live |
| "add a counter for 800 members when I say it" | adds a count-up look on those words |
| `/style-pack` | builds your brand look (colours, captions, zooms, sounds) for every reel |
| `/repurpose` | writes and renders the carousel, stories and 3 trial reels |
| `/separate-layers` | exports layers to finish in CapCut |
| `/script-reel` | writes the script with your own `reel-script` skill and voice, saves it for filming, plans your week |

Or drive it by hand:
```bash
python reel.py new myreel ~/Desktop/IMG_4821.MOV --prompt "names, brand words"
python reel.py studio myreel          # visual editor
python reel.py render myreel          # final reel + cover
python reel.py repurpose myreel       # carousel, stories, trial reels
python reel.py layers myreel          # CapCut layers
```
Everything lands in `projects/myreel/out/`. `CLAUDE.md` documents every edit option.

## Tips

- Whisper sizes: `--model base` is faster, `--model medium` more accurate. `small` is a good default.
- Free music: YouTube Audio Library, Pixabay Music. Free sound effects: Pixabay, freesound.org.
  Put sounds in `sfx/`, and music or images in your project folder (or upload them in the studio).
- Custom fonts: see `fonts/README.md`.
- Post the `trial_N.mp4` files with Instagram's Trial Reels feature to test hooks on non-followers.
