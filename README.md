# Reel Editor (free, DIY)

Your style. Your footage. Minus the editing hours. Built with free tools, running on your own computer.
There's nothing to buy and no API keys.

**Double-click, drop in your video (or several clips, which get joined in the order you choose), and the
editor walks you through it:**

1. **Words**: fix anything that was misheard (names, brand words), one by one or everywhere at once
2. **Best takes**: every line you said more than once, side by side. Listen, keep your favourite.
3. **Trim**: edit the script to edit the video. Select words, press Delete, and they're cut. Ctrl+Z undoes.
4. **Look**: style, hook, word-by-word captions, zooms
5. **Visuals**: headline, count-up counter, full-screen moment, label or image on any words
6. **Sound**: music under your voice, little sound effects
7. **Make it**: the finished 9:16 reel and a cover, plus a carousel, stories, 3 trial reels and CapCut layers

The preview updates instantly as you edit. Nothing renders until you press **Make my reel**.

## Start it

- **Windows**: double-click **`Reel Editor.bat`**
- **Mac**: double-click **`Reel Editor.command`** (the first time, right-click it → **Open** → **Open**)

A small black window opens. Keep it open while you edit; it's what runs the editor. Your browser opens
the home screen at http://127.0.0.1:8765. Everything stays on your computer.

The very first time, the launcher installs what it needs (ffmpeg, Python and two Python packages),
which takes a few minutes. The first video you add also downloads the speech model (~500 MB). After
that it works offline.

## With Claude Code (optional)

Open Claude Code in this folder and talk to it while the editor is open. Your preview updates by itself.

| Say | What happens |
|---|---|
| "Edit my new reel: *(drag a video in)*" | transcribes it, proposes cuts, best takes and a hook |
| "cut the part about my old job" / "tighter" / "one word at a time" | edits the reel; watch the preview change |
| "add a counter for 800 members when I say it" | adds a count-up on those words |
| `/style-pack` | builds your brand look for every reel |
| `/repurpose` | writes your carousel, stories and 3 trial hooks |
| `/separate-layers` | exports layers to finish in CapCut |
| `/script-reel` | writes the script with your own `reel-script` skill before you film |

## Manual setup (if the launcher can't do it)

**Windows** (PowerShell)
```powershell
winget install Gyan.FFmpeg
winget install Python.Python.3.12
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned    # lets the next lines run
cd <this folder>
python -m venv .venv
.venv\Scripts\activate
pip install faster-whisper pillow
python reel.py check     # everything should say ok
```

**Mac** (Terminal; install [Homebrew](https://brew.sh) first)
```bash
brew install ffmpeg python
cd <this folder>
python3 -m venv .venv
source .venv/bin/activate
pip install faster-whisper pillow
python reel.py check
```

## By hand (for the curious)
```bash
python reel.py app                    # the editor app
python reel.py new myreel ~/Desktop/IMG_4821.MOV --prompt "names, brand words"
python reel.py takes myreel           # lines said more than once
python reel.py render myreel          # final reel + cover
python reel.py repurpose myreel       # carousel, stories, trial reels
python reel.py layers myreel          # CapCut layers
```
Everything lands in `projects/<name>/out/`. `CLAUDE.md` documents every edit option.

## Tips

- In the home screen's **Options**, type the names and brand words you say. They'll be spelled right.
- Free music: YouTube Audio Library, Pixabay Music. Free sound effects: Pixabay, freesound.org.
  Put your own sounds in `sfx/`, or upload music and images straight in the editor.
- Custom fonts: see `fonts/README.md`.
- Post the trial reels with Instagram's Trial Reels feature to test hooks on non-followers.
