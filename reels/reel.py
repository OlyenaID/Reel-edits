#!/usr/bin/env python3
"""Reels editing engine: transcript-driven talking-head reel editor.

Free, local pipeline: faster-whisper (transcription) + ffmpeg (editing) + Pillow (covers/carousels).
Claude Code drives it by editing projects/<name>/edit.json; see CLAUDE.md.

  python reel.py check
  python reel.py new <name> <video>          # copy footage in + transcribe
  python reel.py transcribe <name>
  python reel.py render <name> [--preview]   # -> out/reel.mp4 + out/cover.jpg
  python reel.py repurpose <name>            # -> carousel, stories, trial reels
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
STYLES = ROOT / "styles"

FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "hmm", "mm", "mhm"}
SENTENCE_END = re.compile(r"[.!?]$")

DEFAULT_EDIT = {
    "style": "default",
    "fixes": {},
    "cut": [],
    "auto_fillers": True,
    "max_pause": 0.35,
    "hook": "",
    "emphasis": [],
    "music": None,
    "cover_time": 0.5,
    "carousel": [],
    "trials": [],
}


# ---------- helpers ----------

def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        die("command failed: " + " ".join(map(str, cmd)) + "\n" + proc.stderr[-3000:])
    return proc.stdout


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is None:
            die(f"missing {path}")
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def project_dir(name):
    d = PROJECTS / name
    if not d.exists():
        die(f"no project '{name}' in {PROJECTS}")
    return d


def find_source(d):
    for f in sorted(d.iterdir()):
        if f.stem == "source" and f.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
            return f
    die(f"no source video in {d} (expected source.mp4/.mov)")


def load_style(name):
    style = load_json(STYLES / "default.json")
    if name and name != "default":
        style = deep_merge(style, load_json(STYLES / f"{name}.json"))
    return style


def fmt_time(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def norm(word):
    return re.sub(r"[^\w']", "", word.lower())


def probe(path):
    out = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                          "-show_format", str(path)]))
    v = next((s for s in out["streams"] if s["codec_type"] == "video"), None)
    if not v:
        die(f"{path} has no video stream")
    w, h = int(v["width"]), int(v["height"])
    rot = int(v.get("tags", {}).get("rotate", 0))
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {
        "w": w, "h": h,
        "duration": float(out["format"]["duration"]),
        "audio": any(s["codec_type"] == "audio" for s in out["streams"]),
    }


def find_font(style_font_file=None):
    candidates = [style_font_file] if style_font_file else []
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout:
            candidates.append(out.stdout.strip())
    except FileNotFoundError:
        pass
    candidates += [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


# ---------- transcription ----------

def transcribe(name, model_size="small", language=None, prompt=None):
    d = project_dir(name)
    src = find_source(d)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die("faster-whisper not installed: pip install faster-whisper")
    print(f"transcribing {src.name} with whisper '{model_size}' (first run downloads the model)...")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, info = model.transcribe(str(src), word_timestamps=True, language=language,
                                      initial_prompt=prompt, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"i": len(words), "w": text, "s": round(w.start, 3), "e": round(w.end, 3)})
    save_json(d / "transcript.json", {"language": info.language, "duration": info.duration, "words": words})
    write_transcript_md(d, words)
    if not (d / "edit.json").exists():
        save_json(d / "edit.json", DEFAULT_EDIT)
    print(f"{len(words)} words -> {d / 'transcript.md'}")


def sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if SENTENCE_END.search(w["w"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def write_transcript_md(d, words):
    lines = ["# Transcript", "",
             "Each word is prefixed with its index. Cut/fix/emphasis in edit.json refer to these indexes.", ""]
    for n, sent in enumerate(sentences(words), 1):
        lines.append(f"**S{n}** `{fmt_time(sent[0]['s'])}–{fmt_time(sent[-1]['e'])}`  ")
        lines.append(" ".join(f"[{w['i']}]{w['w']}" for w in sent))
        lines.append("")
    (d / "transcript.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- edit planning ----------

def plan(words, edit, duration, open_with=None):
    """Return list of segments: {s, e, words:[...]} in output order."""
    words = [dict(w) for w in words]
    for idx, text in edit.get("fixes", {}).items():
        if 0 <= int(idx) < len(words):
            words[int(idx)]["w"] = text
    cut = set()
    for a, b in edit.get("cut", []):
        cut.update(range(int(a), int(b) + 1))
    if edit.get("auto_fillers", True):
        cut.update(w["i"] for w in words if norm(w["w"]) in FILLERS)
    emphasis = set(int(i) for i in edit.get("emphasis", []))
    for w in words:
        w["emph"] = w["i"] in emphasis

    max_pause = float(edit.get("max_pause", 0.35))
    pad = 0.08

    def build(selected):
        segs = []
        prev = None
        for w in selected:
            joinable = (prev is not None and w["i"] == prev["i"] + 1
                        and w["s"] - prev["e"] <= max_pause)
            if joinable:
                segs[-1]["e"] = min(w["e"] + pad, duration)
                segs[-1]["words"].append(w)
            else:
                segs.append({"s": max(w["s"] - pad, 0.0), "e": min(w["e"] + pad, duration), "words": [w]})
            prev = w
        # keep chronological segments from overlapping each other
        for a, b in zip(segs, segs[1:]):
            if b["s"] < a["e"] and b["words"][0]["i"] > a["words"][-1]["i"]:
                mid = (a["words"][-1]["e"] + b["words"][0]["s"]) / 2
                a["e"], b["s"] = mid, mid
        return [s for s in segs if s["e"] - s["s"] > 0.05]

    kept = [w for w in words if w["i"] not in cut]
    segs = build(kept)
    if open_with:
        a, b = int(open_with[0]), int(open_with[1])
        teaser = build([w for w in kept if a <= w["i"] <= b])
        segs = teaser + segs

    t = 0.0
    for seg in segs:
        seg["out"] = t
        for w in seg["words"]:
            w["os"] = t + (w["s"] - seg["s"])
            w["oe"] = t + (w["e"] - seg["s"])
        t += seg["e"] - seg["s"]
    return segs


# ---------- captions (ASS) ----------

def ass_color(hex_color, alpha=0):
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def ass_time(t):
    t = max(t, 0)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def build_ass(segs, style, hook, total):
    W, H = style["width"], style["height"]
    c, hk = style["caption"], style["hook"]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{c['font']},{c['size']},{ass_color(c['color'])},{ass_color(c['highlight'])},{ass_color(c['outline'])},{ass_color('#000000', 128)},{-1 if c['bold'] else 0},0,0,0,100,100,0,0,1,{c['outline_width']},{c['shadow']},5,60,60,0,1
Style: Hook,{hk['font']},{hk['size']},{ass_color(hk['color'])},{ass_color(hk['color'])},{ass_color(hk['box'])},{ass_color(hk['box'])},-1,0,0,0,100,100,0,0,3,18,0,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if hook:
        y = int(H * hk["position_y"])
        events.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(hk['duration'], total))},Hook,,0,0,0,,"
                      f"{{\\an5\\pos({W // 2},{y})\\fad(150,200)}}{ass_escape(hook)}")

    words = [w for seg in segs for w in seg["words"]]
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= c["words_per_chunk"] or w["os"] - cur[-1]["oe"] > 0.6):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if SENTENCE_END.search(w["w"]) or w["w"].endswith(","):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    y = int(H * c["position_y"])
    hi, emph = ass_color(c["highlight"]), ass_color(c.get("emphasis", c["highlight"]))
    for chunk in chunks:
        for k, w in enumerate(chunk):
            start = w["os"]
            end = chunk[k + 1]["os"] if k + 1 < len(chunk) else w["oe"] + 0.15
            parts = []
            for j, x in enumerate(chunk):
                txt = ass_escape(x["w"].upper() if c["uppercase"] else x["w"])
                if not c.get("keep_punctuation", False):
                    txt = txt.rstrip(".,;:")
                if j == k:
                    scale = 118 if x["emph"] else (108 if c["pop"] else 100)
                    col = emph if x["emph"] else hi
                    parts.append(f"{{\\c{col}\\fscx{scale}\\fscy{scale}}}{txt}{{\\r}}")
                elif x["emph"]:
                    parts.append(f"{{\\c{emph}}}{txt}{{\\r}}")
                else:
                    parts.append(txt)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,"
                          f"{{\\an5\\pos({W // 2},{y})}}" + " ".join(parts))
    return header + "\n".join(events) + "\n"


# ---------- rendering ----------

def crop_filter(info, style, zoom):
    W, H = style["width"], style["height"]
    target = W / H
    sw, sh = info["w"], info["h"]
    if sw / sh > target:
        cw, ch = sh * target, sh
    else:
        cw, ch = sw, sw / target
    cw, ch = cw / zoom, ch / zoom
    cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2
    x = (sw - cw) / 2
    y = (sh - ch) * style["zoom"].get("focus_y", 0.4)
    return f"crop={cw}:{ch}:{int(x)}:{int(y)},scale={W}:{H}:flags=lanczos,setsar=1,fps={style['fps']}"


def render(name, preview=False, edit_over=None, out_name="reel", make_cover=True):
    d = project_dir(name)
    src = find_source(d)
    tr = load_json(d / "transcript.json")
    edit = deep_merge(DEFAULT_EDIT, load_json(d / "edit.json", DEFAULT_EDIT))
    if edit_over:
        edit = deep_merge(edit, edit_over)
    style = load_style(edit.get("style"))
    if preview:
        style = deep_merge(style, {"width": style["width"] // 2, "height": style["height"] // 2})
        style["caption"]["size"] //= 2
        style["caption"]["outline_width"] = max(1, style["caption"]["outline_width"] // 2)
        style["hook"]["size"] //= 2
    info = probe(src)
    segs = plan(tr["words"], edit, info["duration"], edit.get("open_with"))
    if not segs:
        die("edit removes every word; nothing to render")

    out_dir = d / "out"
    out_dir.mkdir(exist_ok=True)
    total = sum(s["e"] - s["s"] for s in segs)
    print(f"{len(segs)} segments, {info['duration']:.1f}s -> {total:.1f}s")

    z = style["zoom"]
    emph_ids = set(int(i) for i in edit.get("emphasis", []))
    enc = ["-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-crf", "28" if preview else "18",
           "-pix_fmt", "yuv420p"]

    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        tmp = Path(tmp)
        listing = []
        for i, seg in enumerate(segs):
            zoom = 1.0
            if z.get("alternate") and i % 2 == 1:
                zoom = z["punch_in"]
            if any(w["i"] in emph_ids for w in seg["words"]):
                zoom = z.get("emphasis_zoom", z["punch_in"])
            part = tmp / f"p{i:04d}.mkv"
            dur = seg["e"] - seg["s"]
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{seg['s']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                   "-vf", crop_filter(info, style, zoom)]
            if info["audio"]:
                fade = min(0.015, dur / 4)
                cmd += ["-af", f"aresample=48000,afade=t=in:d={fade},afade=t=out:st={max(dur - fade, 0):.3f}:d={fade}",
                        "-c:a", "pcm_s16le", "-ac", "2"]
            else:
                cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                        "-map", "0:v", "-map", "1:a", "-c:a", "pcm_s16le"]
            run(cmd + enc + [str(part)])
            listing.append(f"file '{part.name}'")
            print(f"\r  cut {i + 1}/{len(segs)}", end="", flush=True)
        print()
        (tmp / "list.txt").write_text("\n".join(listing) + "\n")
        joined = tmp / "joined.mkv"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
             joined.name], cwd=tmp)

        (tmp / "captions.ass").write_text(build_ass(segs, style, edit.get("hook", ""), total), encoding="utf-8")
        vf = "ass=captions.ass"
        font_file = style["caption"].get("font_file")
        if font_file:
            fdir = tmp / "fonts"
            fdir.mkdir()
            shutil.copy(ROOT / font_file if not Path(font_file).is_absolute() else font_file, fdir)
            vf += ":fontsdir=fonts"

        inputs = ["-i", joined.name]
        audio = style["audio"]
        af = ["loudnorm=I=-14:TP=-1.5:LRA=11" if audio.get("loudnorm") else "anull"]
        music = edit.get("music")
        if music:
            mpath = Path(music) if Path(music).is_absolute() else d / music
            inputs += ["-stream_loop", "-1", "-i", str(mpath)]
            fc = (f"[0:v]{vf}[v];[0:a]{af[0]}[voice];[1:a]volume={audio['music_volume']},"
                  f"afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[m];"
                  f"[voice][m]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            fc = f"[0:v]{vf}[v];[0:a]{af[0]}[a]"
        final = out_dir / f"{out_name}.mp4"
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             *enc, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
             "-t", f"{total:.3f}", str(final.resolve())], cwd=tmp)

        if make_cover and not preview:
            # clean frame (no captions) is kept for the carousel's first slide
            frame = out_dir / f"{out_name}_frame.png"
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{min(float(edit['cover_time']), total - 0.1):.2f}",
                 "-i", joined.name, "-frames:v", "1", str(frame.resolve())], cwd=tmp)
            make_cover_image(frame, edit.get("hook", ""), style, out_dir / f"{out_name}_cover.jpg")

    save_json(out_dir / f"{out_name}_timeline.json", [
        {"src": [round(s["s"], 3), round(s["e"], 3)], "out": round(s["out"], 3),
         "text": " ".join(w["w"] for w in s["words"])} for s in segs])
    print(f"done -> {final}")
    return final, segs


# ---------- images (cover + carousel) ----------

def wrap_text(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = (cur + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def get_font(style_block, size):
    from PIL import ImageFont
    path = style_block.get("font_file")
    path = str(ROOT / path) if path and not Path(path).is_absolute() else path
    path = find_font(path)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


def draw_block(img, text, font, color, box, center_y, max_w, line_gap=1.2):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    lines = wrap_text(draw, text, font, max_w)
    lh = int(font.size * line_gap)
    y = int(center_y - lh * len(lines) / 2)
    for line in lines:
        tw = draw.textlength(line, font=font)
        x = (img.width - tw) / 2
        if box:
            p = font.size * 0.25
            draw.rounded_rectangle([x - p, y - p * 0.6, x + tw + p, y + lh - p * 0.2], radius=int(p), fill=box)
        draw.text((x, y), line, font=font, fill=color)
        y += lh


def make_cover_image(frame, hook, style, out):
    from PIL import Image
    img = Image.open(frame).convert("RGB")
    if hook:
        hk = style["hook"]
        font = get_font(style["caption"], int(img.width * 0.085))
        draw_block(img, hook, font, hk["color"], hk["box"], img.height * 0.45, img.width * 0.82)
    img.save(out, quality=92)


def make_carousel(d, slides, style, frame=None):
    from PIL import Image, ImageDraw
    cs = style["carousel"]
    W, H = cs["width"], cs["height"]
    out = d / "out" / "carousel"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("slide_*.png"):
        old.unlink()
    body = get_font(cs, cs["size"])
    small = get_font(cs, int(cs["size"] * 0.45))
    for n, text in enumerate(slides, 1):
        if n == 1 and frame and Path(frame).exists():
            bg = Image.open(frame).convert("RGB")
            scale = max(W / bg.width, H / bg.height)
            bg = bg.resize((int(bg.width * scale), int(bg.height * scale)))
            left, top = (bg.width - W) // 2, int((bg.height - H) * 0.4)
            img = bg.crop((left, top, left + W, top + H))
            img = Image.blend(img, Image.new("RGB", (W, H), "#000000"), 0.45)
            font = get_font(cs, int(cs["size"] * 1.25))
        else:
            img = Image.new("RGB", (W, H), cs["bg"])
            font = body
        draw = ImageDraw.Draw(img)
        draw.rectangle([80, 110, 200, 122], fill=cs["accent"])
        draw_block(img, text, font, cs["text"], None, H * 0.5, W - 180)
        draw.text((W - 80, H - 80), f"{n}/{len(slides)}", font=small, fill=cs["accent"], anchor="rs")
        if n < len(slides):
            draw.text((80, H - 80), "swipe →", font=small, fill=cs["text"], anchor="ls")
        img.save(out / f"slide_{n:02d}.png")
    print(f"carousel: {len(slides)} slides -> {out}")


# ---------- repurposing ----------

def make_stories(d, reel, segs, max_len):
    out = d / "out" / "stories"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("story_*.mp4"):
        old.unlink()
    total = sum(s["e"] - s["s"] for s in segs)
    bounds = [s["out"] for s in segs[1:]] + [total]
    starts, t = [0.0], 0.0
    while total - t > max_len:
        fits = [b for b in bounds if t + 3 < b <= t + max_len]
        t = max(fits) if fits else t + max_len
        starts.append(t)
    starts.append(total)
    for n, (a, b) in enumerate(zip(starts, starts[1:]), 1):
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", str(reel), "-t", f"{b - a:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out / f"story_{n:02d}.mp4")])
    print(f"stories: {len(starts) - 1} clips -> {out}")


def repurpose(name, only=None):
    d = project_dir(name)
    edit = deep_merge(DEFAULT_EDIT, load_json(d / "edit.json", DEFAULT_EDIT))
    style = load_style(edit.get("style"))
    reel = d / "out" / "reel.mp4"
    if not reel.exists() or not (d / "out" / "reel_frame.png").exists():
        render(name)
    tr = load_json(d / "transcript.json")
    segs = plan(tr["words"], edit, probe(find_source(d))["duration"])

    if only in (None, "carousel"):
        if edit.get("carousel"):
            make_carousel(d, edit["carousel"], style, d / "out" / "reel_frame.png")
        else:
            print("carousel: skipped (edit.json 'carousel' is empty)")
    if only in (None, "stories"):
        make_stories(d, reel, segs, style["stories"]["max_len"])
    if only in (None, "trials"):
        trials = edit.get("trials") or []
        if not trials:
            print("trials: skipped (edit.json 'trials' is empty)")
        for n, trial in enumerate(trials, 1):
            print(f"trial reel {n}: {trial.get('hook', '')!r}")
            render(name, edit_over=trial, out_name=f"trial_{n}")


# ---------- setup ----------

def check():
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        print(f"{tool:15} {'ok' if found else 'MISSING'}")
        ok &= bool(found)
    if shutil.which("ffmpeg"):
        filters = run(["ffmpeg", "-hide_banner", "-filters"])
        has_ass = re.search(r"\sass\s", filters) is not None
        print(f"{'libass':15} {'ok' if has_ass else 'MISSING (need an ffmpeg build with libass for captions)'}")
        ok &= has_ass
    for mod, pip in (("faster_whisper", "faster-whisper"), ("PIL", "pillow")):
        try:
            __import__(mod)
            print(f"{pip:15} ok")
        except ImportError:
            print(f"{pip:15} MISSING  (pip install {pip})")
            ok = False
    print("ready." if ok else "fix the MISSING items above (see README.md).")


def new(name, video):
    d = PROJECTS / name
    d.mkdir(parents=True, exist_ok=True)
    video = Path(video).expanduser()
    if not video.exists():
        die(f"{video} not found")
    shutil.copy(video, d / ("source" + video.suffix.lower()))
    print(f"project {d}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p_new = sub.add_parser("new")
    p_new.add_argument("name")
    p_new.add_argument("video")
    p_new.add_argument("--no-transcribe", action="store_true")
    p_tr = sub.add_parser("transcribe")
    p_tr.add_argument("name")
    for p in (p_new, p_tr):
        p.add_argument("--model", default="small", help="whisper size: tiny/base/small/medium/large-v3")
        p.add_argument("--language", default=None)
        p.add_argument("--prompt", default=None, help="names/jargon to help spelling, e.g. 'Meg, Kajabi'")
    p = sub.add_parser("render")
    p.add_argument("name")
    p.add_argument("--preview", action="store_true", help="fast half-res render without cover")
    p = sub.add_parser("repurpose")
    p.add_argument("name")
    p.add_argument("--only", choices=["carousel", "stories", "trials"])
    a = ap.parse_args()

    if a.cmd == "check":
        check()
    elif a.cmd == "new":
        new(a.name, a.video)
        if not a.no_transcribe:
            transcribe(a.name, a.model, a.language, a.prompt)
    elif a.cmd == "transcribe":
        transcribe(a.name, a.model, a.language, a.prompt)
    elif a.cmd == "render":
        render(a.name, preview=a.preview, out_name="preview" if a.preview else "reel")
    elif a.cmd == "repurpose":
        repurpose(a.name, a.only)


if __name__ == "__main__":
    main()
