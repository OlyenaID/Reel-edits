#!/usr/bin/env python3
"""Reels editing engine: transcript-driven talking-head reel editor.

Free, local pipeline: faster-whisper (transcription) + ffmpeg (editing) + Pillow (covers/carousels).
Claude Code drives it by editing projects/<name>/edit.json; see CLAUDE.md.

  python reel.py check
  python reel.py new <name> <video> [more...] # copy footage in (several clips are joined) + transcribe
  python reel.py transcribe <name>
  python reel.py app                         # the editor app in your browser (home screen + all reels)
  python reel.py studio <name>               # open one reel straight in the editor
  python reel.py takes <name>                # lines said more than once, best take marked *
  python reel.py render <name> [--preview]   # -> out/reel.mp4 + out/reel_cover.jpg
  python reel.py repurpose <name>            # -> carousel, stories, trial reels
  python reel.py layers <name>               # -> transparent caption/hook/look layers for CapCut
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
STYLES = ROOT / "styles"
SFX_DIR = ROOT / "sfx"

FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "hmm", "mm", "mhm"}
SENTENCE_END = re.compile(r"[.!?]$")
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
LOOK_TYPES = ("headline", "takeover", "label", "counter", "image")

DEFAULT_EDIT = {
    "style": "default",
    "style_overrides": {},
    "fixes": {},
    "cut": [],
    "keep": [],
    "auto_fillers": True,
    "max_pause": 0.35,
    "hook": "",
    "emphasis": [],
    "looks": [],
    "music": None,
    "sfx": [],
    "cover_time": 0.5,
    "carousel": [],
    "stories": [],
    "trials": [],
}

# Built-in sound effects, synthesised by ffmpeg on first use (no downloads, no licences).
BUILTIN_SFX = {
    "pop": "sine=f=880:d=0.09,afade=t=out:st=0.02:d=0.07,volume=0.9",
    "click": "anoisesrc=d=0.025:c=white:a=0.6,highpass=f=2000,afade=t=out:d=0.025",
    "whoosh": "anoisesrc=d=0.5:c=pink:a=0.8,bandpass=f=1200:w=900,afade=t=in:d=0.22,afade=t=out:st=0.22:d=0.28",
    "ding": "sine=f=1318:d=0.7,afade=t=out:st=0.03:d=0.67:curve=exp,volume=0.7",
    "boom": "sine=f=55:d=0.6,afade=t=out:st=0.05:d=0.55:curve=exp,volume=1.6",
    "rise": "aevalsrc=0.5*sin(2*PI*(300+900*t)*t):d=0.6,afade=t=in:d=0.4,afade=t=out:st=0.5:d=0.1",
}


# ---------- helpers ----------

class ReelError(Exception):
    pass


def die(msg):
    raise ReelError(msg)


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
        if f.stem == "source" and f.suffix.lower() in VIDEO_EXT:
            return f
    die(f"no source video in {d} (expected source.mp4/.mov)")


def style_names():
    return sorted(p.stem for p in STYLES.glob("*.json"))


def load_style(name):
    style = load_json(STYLES / "default.json")
    if name and name != "default":
        style = deep_merge(style, load_json(STYLES / f"{name}.json"))
    return style


def load_edit(d, over=None):
    edit = deep_merge(DEFAULT_EDIT, load_json(d / "edit.json", DEFAULT_EDIT))
    return deep_merge(edit, over) if over else edit


def style_for(edit):
    return deep_merge(load_style(edit.get("style")), edit.get("style_overrides") or {})


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


def sfx_path(name):
    """Path to a sound effect: a file in sfx/ (any audio type) or a built-in, generated on first use."""
    SFX_DIR.mkdir(exist_ok=True)
    for f in SFX_DIR.iterdir():
        if f.is_file() and f.stem == name and f.suffix.lower() in AUDIO_EXT:
            return f
    if name not in BUILTIN_SFX:
        die(f"unknown sound '{name}': built-ins are {', '.join(BUILTIN_SFX)}, or drop a file in sfx/")
    out = SFX_DIR / ".builtin" / f"{name}.wav"
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    src, _, chain = BUILTIN_SFX[name].partition(",")
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-af", chain + ",aformat=channel_layouts=stereo",
         "-ar", "48000", str(out)])
    return out


def sfx_names():
    SFX_DIR.mkdir(exist_ok=True)
    return sorted(set(BUILTIN_SFX) | {f.stem for f in SFX_DIR.iterdir() if f.suffix.lower() in AUDIO_EXT})


# ---------- transcription ----------

def load_audio(src):
    """The video's sound as 16 kHz mono float32, decoded by ffmpeg.

    faster-whisper's own decoder (PyAV) breaks whenever PyAV changes its API (e.g. PyAV 15+ dropped the
    `metadata_errors` option faster-whisper 1.2 passes), so we hand Whisper samples instead of a file.
    """
    import numpy as np
    if not probe(src)["audio"]:
        die("this video has no sound track, so there's nothing to transcribe")
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                           "-f", "f32le", "-"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        die("couldn't read the sound in this video: " + proc.stderr.decode(errors="replace")[-500:])
    return np.frombuffer(proc.stdout, np.float32)


def join_clips(d):
    """Turn projects/<name>/clips/* (in name order) into one source video.

    One clip is just moved into place. Several are scaled/padded to the first clip's frame and joined,
    so clips filmed in different orientations or frame rates still line up.
    """
    clips = sorted(f for f in (d / "clips").iterdir() if f.suffix.lower() in VIDEO_EXT) \
        if (d / "clips").exists() else []
    if not clips:
        return
    if len(clips) == 1:
        clips[0].replace(d / ("source" + clips[0].suffix.lower()))
    else:
        print(f"joining {len(clips)} clips...", flush=True)
        infos = [probe(c) for c in clips]
        W, H = infos[0]["w"] // 2 * 2, infos[0]["h"] // 2 * 2
        inputs, filters, pairs = [], [], []
        for c in clips:
            inputs += ["-i", str(c)]
        for n, (c, info) in enumerate(zip(clips, infos)):
            filters.append(f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                           f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{n}]")
            if info["audio"]:
                filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo[a{n}]")
            else:
                k = inputs.count("-i")
                inputs += ["-f", "lavfi", "-t", f"{info['duration']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                filters.append(f"[{k}:a]anull[a{n}]")
            pairs.append(f"[v{n}][a{n}]")
        filters.append("".join(pairs) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
        out = d / "source.mp4"
        tmp = d / "tmp_source.mp4"
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[v]",
             "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(tmp)])
        tmp.replace(out)
        for c in clips:
            c.unlink()
    shutil.rmtree(d / "clips", ignore_errors=True)


def transcribe(name, model_size="small", language=None, prompt=None):
    d = project_dir(name)
    join_clips(d)
    src = find_source(d)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die("faster-whisper not installed: pip install faster-whisper")
    audio = load_audio(src)
    print(f"transcribing {src.name} with whisper '{model_size}' (first run downloads the model)...")
    try:
        model = WhisperModel(model_size, device="auto", compute_type="int8")
    except Exception as e:
        die("couldn't get the speech model. The first time, it downloads (~500 MB), so check your internet "
            f"connection, VPN or ad blocker and try again. ({type(e).__name__})")
    try:
        segments, info = model.transcribe(audio, word_timestamps=True, language=language,
                                          initial_prompt=prompt, vad_filter=True)
    except Exception as e:
        die(f"couldn't transcribe this video ({type(e).__name__}: {e})")
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"i": len(words), "w": text, "s": round(w.start, 3), "e": round(w.end, 3)})
        if info.duration:
            print(f"progress {min(seg.end / info.duration, 1):.3f}", flush=True)
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
             "Each word is prefixed with its index. Cut/fix/emphasis/looks in edit.json refer to these indexes.", ""]
    for n, sent in enumerate(sentences(words), 1):
        lines.append(f"**S{n}** `{fmt_time(sent[0]['s'])}–{fmt_time(sent[-1]['e'])}`  ")
        lines.append(" ".join(f"[{w['i']}]{w['w']}" for w in sent))
        lines.append("")
    (d / "transcript.md").write_text("\n".join(lines), encoding="utf-8")


def find_takes(words, window=4, threshold=0.65):
    """Group sentences that are retakes of each other: the same line said again, or a false start.

    Returns [{"takes": [{"from", "to", "text", "s", "e"}...], "suggested": index}], earliest group first.
    """
    sents = sentences(words)
    toks = [[norm(w["w"]) for w in s if norm(w["w"]) and norm(w["w"]) not in FILLERS] for s in sents]
    parent = list(range(len(sents)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(sents)):
        for j in range(i + 1, min(len(sents), i + 1 + window)):
            a, b = toks[i], toks[j]
            if len(a) < 3 or len(b) < 3:
                continue
            similar = difflib.SequenceMatcher(None, a, b).ratio() >= threshold
            # a false start: the earlier line is (roughly) the opening of the later one
            short, long_ = (a, b) if len(a) < len(b) else (b, a)
            false_start = (len(short) < len(long_) and
                           difflib.SequenceMatcher(None, short, long_[:len(short)]).ratio() >= 0.8)
            if similar or false_start:
                parent[root(j)] = root(i)

    groups = {}
    for i in range(len(sents)):
        groups.setdefault(root(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        takes = [{"from": sents[i][0]["i"], "to": sents[i][-1]["i"], "s": sents[i][0]["s"], "e": sents[i][-1]["e"],
                  "text": " ".join(w["w"] for w in sents[i]), "words": len(toks[i])} for i in members]
        longest = max(t["words"] for t in takes)
        # people usually nail it on the last full attempt; fragments don't count
        full = [k for k, t in enumerate(takes) if t["words"] >= 0.8 * longest]
        out.append({"takes": takes, "suggested": full[-1]})
    return sorted(out, key=lambda g: g["takes"][0]["from"])


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:40] or "reel"
    n, base = 2, slug
    while (PROJECTS / slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


# ---------- edit planning ----------

def removed_words(words, edit):
    """Word index -> reason ('cut' or 'filler') for every word the edit drops."""
    gone = {}
    keep = set(int(i) for i in edit.get("keep", []))
    if edit.get("auto_fillers", True):
        for w in words:
            if norm(w["w"]) in FILLERS and w["i"] not in keep:
                gone[w["i"]] = "filler"
    for a, b in edit.get("cut", []):
        for i in range(int(a), int(b) + 1):
            gone[i] = "cut"
    return gone


def plan(words, edit, duration, open_with=None):
    """Return list of segments: {s, e, out, words:[...]} in output order."""
    words = [dict(w) for w in words]
    for idx, text in edit.get("fixes", {}).items():
        if 0 <= int(idx) < len(words):
            words[int(idx)]["w"] = text
    gone = removed_words(words, edit)
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

    kept = [w for w in words if w["i"] not in gone]
    segs = build(kept)
    if open_with:
        a, b = int(open_with[0]), int(open_with[1])
        teaser = build([dict(w) for w in kept if a <= w["i"] <= b])
        for seg in teaser:
            seg["teaser"] = True
        segs = teaser + segs

    t = 0.0
    for seg in segs:
        seg["out"] = t
        for w in seg["words"]:
            w["os"] = t + (w["s"] - seg["s"])
            w["oe"] = t + (w["e"] - seg["s"])
        t += seg["e"] - seg["s"]
    return segs


def seg_zoom(i, seg, style, emph_ids):
    z = style["zoom"]
    zoom = z["punch_in"] if z.get("alternate") and i % 2 == 1 else 1.0
    if any(w["i"] in emph_ids for w in seg["words"]):
        zoom = z.get("emphasis_zoom", z["punch_in"])
    return zoom


def word_times(segs):
    """Word index -> (out_start, out_end); the main body wins over a teaser copy."""
    times = {}
    for seg in segs:
        for w in seg["words"]:
            if not seg.get("teaser") or w["i"] not in times:
                times[w["i"]] = (w["os"], w["oe"])
    return times


def span_times(times, a, b):
    inside = [times[i] for i in range(int(a), int(b) + 1) if i in times]
    if not inside:
        return None
    return min(t[0] for t in inside), max(t[1] for t in inside)


def resolve_looks(edit, segs):
    times = word_times(segs)
    out = []
    for n, look in enumerate(edit.get("looks", [])):
        span = span_times(times, look.get("from", 0), look.get("to", look.get("from", 0)))
        if span and look.get("type") in LOOK_TYPES:
            # a look on a single word would flash by; keep every look up long enough to read
            end = max(span[1] + float(look.get("hold", 0.2)), span[0] + float(look.get("min_seconds", 1.5)))
            out.append(dict(look, n=n, start=span[0], end=end))
    return out


def resolve_sfx(edit, style, segs, looks):
    times = word_times(segs)
    snd = style.get("sound", {})
    out = []
    for fx in edit.get("sfx", []):
        if int(fx["at"]) in times:
            out.append({"t": times[int(fx["at"])][0], "sound": fx["sound"], "volume": float(fx.get("volume", 0.7))})
    if snd.get("look_sfx"):
        out += [{"t": lk["start"], "sound": snd["look_sfx"], "volume": snd.get("look_sfx_volume", 0.5)}
                for lk in looks if lk["type"] != "image" or snd.get("image_sfx", True)]
    if snd.get("emphasis_sfx"):
        out += [{"t": times[int(i)][0], "sound": snd["emphasis_sfx"], "volume": snd.get("emphasis_sfx_volume", 0.5)}
                for i in edit.get("emphasis", []) if int(i) in times]
    return sorted(out, key=lambda x: x["t"])


def caption_chunks(segs, style):
    c = style["caption"]
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
    return chunks


def timeline(d, edit, info=None, words=None):
    """Everything a renderer (ffmpeg or the studio preview) needs, in output time."""
    words = words or load_json(d / "transcript.json")["words"]
    info = info or probe(find_source(d))
    style = style_for(edit)
    segs = plan(words, edit, info["duration"], edit.get("open_with"))
    emph_ids = set(int(i) for i in edit.get("emphasis", []))
    for i, seg in enumerate(segs):
        seg["zoom"] = seg_zoom(i, seg, style, emph_ids)
    total = sum(s["e"] - s["s"] for s in segs)
    looks = resolve_looks(edit, segs)
    return {
        "style": style, "segs": segs, "total": total, "looks": looks,
        "sfx": resolve_sfx(edit, style, segs, looks),
        "chunks": caption_chunks(segs, style),
        "removed": removed_words(words, edit),
    }


# ---------- captions + looks (ASS) ----------

def ass_color(hex_color, alpha=0):
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_escape(text):
    return str(text).replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_time(t):
    t = max(t, 0)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def ass_style(name, font, size, primary, outline, back, bold, border_style, outline_w, shadow):
    return (f"Style: {name},{font},{size},{ass_color(primary)},{ass_color(primary)},{ass_color(outline)},"
            f"{back},{-1 if bold else 0},0,0,0,100,100,0,0,{border_style},{outline_w},{shadow},5,70,70,0,1")


def counter_text(look, value):
    return f"{look.get('prefix', '')}{int(round(value)):,}{look.get('suffix', '')}"


def build_ass(tl, style, hook, parts=("captions", "hook", "looks"), only_look=None):
    W, H = style["width"], style["height"]
    c, hk, lk = style["caption"], style["hook"], style["looks"]
    total = tl["total"]
    styles = [
        ass_style("Cap", c["font"], c["size"], c["color"], c["outline"], ass_color("#000000", 128), c["bold"], 1,
                  c["outline_width"], c["shadow"]),
        ass_style("Hook", hk["font"], hk["size"], hk["color"], hk["box"], ass_color(hk["box"]), True, 3, 18, 0),
        ass_style("Head", lk["font"], lk["headline"]["size"], lk["headline"]["color"], lk["headline"]["box"],
                  ass_color(lk["headline"]["box"]), True, 3, 16, 0),
        ass_style("Sub", lk["font"], lk["headline"]["sub_size"], lk["headline"]["sub_color"],
                  lk["headline"]["sub_box"], ass_color(lk["headline"]["sub_box"]), False, 3, 10, 0),
        ass_style("Take", lk["font"], lk["takeover"]["size"], lk["takeover"]["color"], "#000000",
                  ass_color("#000000", 255), True, 1, 0, 0),
        ass_style("Label", lk["font"], lk["label"]["size"], lk["label"]["color"], lk["label"]["box"],
                  ass_color(lk["label"]["box"]), True, 3, 12, 0),
        ass_style("Count", lk["font"], lk["counter"]["size"], lk["counter"]["color"], lk["counter"]["box"],
                  ass_color(lk["counter"]["box"]), True, 3, 30, 0),
        ass_style("CountSub", lk["font"], lk["counter"]["sub_size"], lk["counter"]["sub_color"],
                  lk["counter"]["box"], ass_color(lk["counter"]["box"]), False, 3, 10, 0),
    ]
    header = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n"
              f"ScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
              f"SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
              f"Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
              + "\n".join(styles) +
              "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    events = []

    def ev(layer, a, b, sty, text):
        events.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(min(b, total))},{sty},,0,0,0,,{text}")

    if "hook" in parts and hook:
        ev(3, 0, hk["duration"], "Hook", f"{{\\an5\\pos({W // 2},{int(H * hk['position_y'])})\\fad(150,200)}}"
           + ass_escape(hook))

    if "captions" in parts:
        y = int(H * c["position_y"])
        hi, emph = ass_color(c["highlight"]), ass_color(c.get("emphasis", c["highlight"]))
        for chunk in tl["chunks"]:
            for k, w in enumerate(chunk):
                end = chunk[k + 1]["os"] if k + 1 < len(chunk) else w["oe"] + 0.15
                parts_txt = []
                for j, x in enumerate(chunk):
                    txt = ass_escape(x["w"].upper() if c["uppercase"] else x["w"])
                    if not c.get("keep_punctuation", False):
                        txt = txt.rstrip(".,;:")
                    if j == k:
                        scale = 118 if x["emph"] else (108 if c["pop"] else 100)
                        col = emph if x["emph"] else hi
                        parts_txt.append(f"{{\\c{col}\\fscx{scale}\\fscy{scale}}}{txt}{{\\r}}")
                    elif x["emph"]:
                        parts_txt.append(f"{{\\c{emph}}}{txt}{{\\r}}")
                    else:
                        parts_txt.append(txt)
                ev(0, w["os"], end, "Cap", f"{{\\an5\\pos({W // 2},{y})}}" + " ".join(parts_txt))

    if "looks" in parts:
        for look in tl["looks"]:
            if only_look is not None and look["n"] != only_look:
                continue
            a, b, kind = look["start"], look["end"], look["type"]
            text = ass_escape(look.get("text", ""))
            sub = ass_escape(look.get("sub", ""))
            if kind == "headline":
                y = int(H * lk["headline"]["position_y"])
                ev(2, a, b, "Head", f"{{\\an5\\pos({W // 2},{y})\\fad(120,120)}}{text}")
                if sub:
                    ev(2, a, b, "Sub", f"{{\\an5\\pos({W // 2},{y + int(lk['headline']['size'] * 1.35)})"
                                       f"\\fad(120,120)}}{sub}")
            elif kind == "takeover":
                bg = ass_color(look.get("bg", lk["takeover"]["bg"]))
                ev(4, a, b, "Take", f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{bg}\\fad(80,80)}}"
                                    f"m 0 0 l {W} 0 {W} {H} 0 {H}{{\\p0}}")
                ev(5, a, b, "Take", f"{{\\an5\\pos({W // 2},{H // 2})\\fad(80,80)}}{text}")
                if sub:
                    ev(5, a, b, "Label", f"{{\\an5\\pos({W // 2},{H // 2 + int(lk['takeover']['size'] * 1.6)})"
                                         f"\\fad(80,80)}}{sub}")
            elif kind == "label":
                y = int(H * float(look.get("position_y", lk["label"]["position_y"])))
                ev(2, a, b, "Label", f"{{\\an5\\pos({W // 2},{y})\\fad(100,100)}}{text}")
            elif kind == "counter":
                cnt = lk["counter"]
                y = int(H * cnt["position_y"])
                target = float(look.get("value", 0))
                ramp = min(float(cnt["count_seconds"]), max(b - a - 0.3, 0.2))
                steps = max(int(ramp * 20), 1)
                for s in range(steps + 1):
                    t0 = a + ramp * s / steps
                    t1 = a + ramp * (s + 1) / steps if s < steps else b
                    p = 1 - (1 - s / steps) ** 3
                    ev(6, t0, t1, "Count", f"{{\\an5\\pos({W // 2},{y})}}" + ass_escape(counter_text(look, target * p)))
                if text:
                    ev(6, a, b, "CountSub", f"{{\\an5\\pos({W // 2},{y + int(cnt['size'] * 0.95)})}}{text}")
    return header + "\n".join(events) + "\n"


def to_srt(tl, style):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d},{ms % 1000:03d}"
    out = []
    for n, chunk in enumerate(tl["chunks"], 1):
        text = " ".join(w["w"] for w in chunk)
        out.append(f"{n}\n{ts(chunk[0]['os'])} --> {ts(chunk[-1]['oe'] + 0.15)}\n"
                   f"{text.upper() if style['caption']['uppercase'] else text}\n")
    return "\n".join(out)


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


def preview_style(style):
    style = deep_merge(style, {"width": style["width"] // 2, "height": style["height"] // 2})
    for block, keys in (("caption", ("size", "outline_width")), ("hook", ("size",))):
        for k in keys:
            style[block][k] = max(1, style[block][k] // 2)
    for block in ("headline", "takeover", "label", "counter"):
        for k in ("size", "sub_size"):
            if k in style["looks"][block]:
                style["looks"][block][k] //= 2
    return style


def cut_and_join(src, info, tl, style, tmp, preview):
    enc = encoder(preview)
    listing = []
    for i, seg in enumerate(tl["segs"]):
        part = tmp / f"p{i:04d}.mkv"
        dur = seg["e"] - seg["s"]
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{seg['s']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
               "-vf", crop_filter(info, style, seg["zoom"])]
        if info["audio"]:
            fade = min(0.015, dur / 4)
            cmd += ["-af", f"aresample=48000,afade=t=in:d={fade},afade=t=out:st={max(dur - fade, 0):.3f}:d={fade}",
                    "-c:a", "pcm_s16le", "-ac", "2"]
        else:
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                    "-map", "0:v", "-map", "1:a", "-c:a", "pcm_s16le"]
        run(cmd + enc + [str(part)])
        listing.append(f"file '{part.name}'")
        print(f"\r  cut {i + 1}/{len(tl['segs'])}", end="", flush=True)
    print()
    (tmp / "list.txt").write_text("\n".join(listing) + "\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
         "joined.mkv"], cwd=tmp)
    return tmp / "joined.mkv"


def encoder(preview):
    return ["-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-crf", "28" if preview else "18",
            "-pix_fmt", "yuv420p"]


def image_looks(d, tl):
    out = []
    for look in tl["looks"]:
        if look["type"] == "image" and look.get("file"):
            path = d / look["file"]
            if not path.exists():
                die(f"image look file not found: {path}")
            out.append((look, path))
    return out


def ass_filter(tmp, ass_name, style):
    vf = f"ass={ass_name}"
    font_file = style["caption"].get("font_file")
    if font_file:
        fdir = tmp / "fonts"
        fdir.mkdir(exist_ok=True)
        shutil.copy(ROOT / font_file if not Path(font_file).is_absolute() else font_file, fdir)
        vf += ":fontsdir=fonts"
    return vf


def overlay_images(chain, images, sources, style, label, filters):
    """Append overlay filters for image looks (inputs named in `sources`); returns the last video label."""
    W, H = style["width"], style["height"]
    img = style["looks"]["image"]
    for n, ((look, _), src) in enumerate(zip(images, sources)):
        w = int(W * float(look.get("width", img["width"])))
        y = int(H * float(look.get("position_y", img["position_y"])))
        filters.append(f"{src}scale={w}:-1,format=rgba[{label}i{n}]")
        filters.append(f"{chain}[{label}i{n}]overlay=x=(W-w)/2:y={y}-h/2:"
                       f"enable='between(t,{look['start']:.3f},{look['end']:.3f})'[{label}o{n}]")
        chain = f"[{label}o{n}]"
    return chain


def render(name, preview=False, edit_over=None, out_name="reel", make_cover=True, overlays=True):
    d = project_dir(name)
    src = find_source(d)
    edit = load_edit(d, edit_over)
    info = probe(src)
    tl = timeline(d, edit, info)
    style = preview_style(tl["style"]) if preview else tl["style"]
    if not tl["segs"]:
        die("edit removes every word; nothing to render")
    total = tl["total"]
    out_dir = d / "out"
    final = out_dir / f"{out_name}.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    print(f"{len(tl['segs'])} segments, {info['duration']:.1f}s -> {total:.1f}s")

    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        tmp = Path(tmp)
        joined = cut_and_join(src, info, tl, style, tmp, preview)
        inputs, filters, mix = ["-i", joined.name], [], ["[voice]"]
        chain = "[0:v]"
        if overlays:
            images = image_looks(d, tl)
            for _, path in images:
                inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(path.resolve())]
            chain = overlay_images(chain, images, [f"[{1 + n}:v]" for n in range(len(images))], style, "v", filters)
            (tmp / "captions.ass").write_text(build_ass(tl, style, edit.get("hook", "")), encoding="utf-8")
            filters.append(f"{chain}{ass_filter(tmp, 'captions.ass', style)}[v]")
        else:
            filters.append(f"{chain}null[v]")

        audio = style["audio"]
        filters.append(f"[0:a]{'loudnorm=I=-14:TP=-1.5:LRA=11' if audio.get('loudnorm') else 'anull'}[voice]")
        if edit.get("music"):
            music = edit["music"]
            mpath = Path(music) if Path(music).is_absolute() else d / music
            idx = inputs.count("-i")
            inputs += ["-stream_loop", "-1", "-i", str(mpath.resolve())]
            vol = edit.get("music_volume", audio["music_volume"])
            filters.append(f"[{idx}:a]volume={vol},afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[m]")
            mix.append("[m]")
        for n, fx in enumerate(tl["sfx"]):
            idx = inputs.count("-i")
            inputs += ["-i", str(sfx_path(fx["sound"]).resolve())]
            ms = int(fx["t"] * 1000)
            filters.append(f"[{idx}:a]adelay={ms}:all=1,volume={fx['volume']}[s{n}]")
            mix.append(f"[s{n}]")
        filters.append("".join(mix) + (f"amix=inputs={len(mix)}:duration=first:normalize=0[a]" if len(mix) > 1
                                       else "anull[a]"))
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[v]",
             "-map", "[a]", *encoder(preview), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", "-t", f"{total:.3f}", str(final.resolve())], cwd=tmp)

        if make_cover and not preview and overlays:
            # clean frame (no captions) is kept for the carousel's first slide
            frame = out_dir / f"{out_name}_frame.png"
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{min(float(edit['cover_time']), total - 0.1):.2f}",
                 "-i", joined.name, "-frames:v", "1", str(frame.resolve())], cwd=tmp)
            make_cover_image(frame, edit.get("hook", ""), style, out_dir / f"{out_name}_cover.jpg")

    save_json(out_dir / f"{out_name}_timeline.json", [
        {"src": [round(s["s"], 3), round(s["e"], 3)], "out": round(s["out"], 3),
         "text": " ".join(w["w"] for w in s["words"])} for s in tl["segs"]])
    print(f"done -> {final}")
    return final, tl


# ---------- CapCut layers ----------

def export_overlay(ass_text, images, tl, style, path, tmp):
    """Render overlays onto a transparent QuickTime Animation .mov (CapCut, Premiere, Final Cut read it).

    libass ignores alpha, so draw everything on black and on white and recover alpha from the difference.
    """
    W, H, fps, total = style["width"], style["height"], style["fps"], tl["total"]
    (tmp / "layer.ass").write_text(ass_text, encoding="utf-8")
    inputs = []
    for colour in ("black", "white"):
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s={W}x{H}:r={fps}:d={total:.3f}"]
    for _, img in images:
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(img.resolve())]
    filters = []
    vf = ass_filter(tmp, "layer.ass", style)
    for n in range(len(images)):
        filters.append(f"[{2 + n}:v]split=2[bsrc{n}][wsrc{n}]")
    for k, label in enumerate(("b", "w")):
        chain = overlay_images(f"[{k}:v]", images, [f"[{label}src{n}]" for n in range(len(images))],
                               style, label, filters)
        filters.append(f"{chain}format=rgb24,{vf},format=gbrp[{label}]")
    filters.append("[b]split[b1][b2];[w][b1]blend=all_mode=difference,extractplanes=g,negate[al]")
    filters.append("[b2][al]alphamerge,unpremultiply=inplace=1,format=argb[o]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[o]",
         "-c:v", "qtrle", str(path.resolve())], cwd=tmp)


def layers(name, split_looks=False):
    d = project_dir(name)
    edit = load_edit(d)
    out = d / "out" / "layers"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        old.unlink()
    print("base video (cuts, zooms, audio, no text)...")
    _, tl = render(name, out_name="layers/base", make_cover=False, overlays=False)
    style = tl["style"]
    (out / "captions.srt").write_text(to_srt(tl, style), encoding="utf-8")
    images = image_looks(d, tl)
    jobs = [("captions", build_ass(tl, style, "", parts=("captions",)), [])]
    if edit.get("hook"):
        jobs.append(("hook", build_ass(tl, style, edit["hook"], parts=("hook",)), []))
    if split_looks:
        for look in tl["looks"]:
            imgs = [(lk, p) for lk, p in images if lk["n"] == look["n"]]
            jobs.append((f"look_{look['n'] + 1:02d}_{look['type']}",
                         build_ass(tl, style, "", parts=("looks",), only_look=look["n"]), imgs))
    elif tl["looks"]:
        jobs.append(("looks", build_ass(tl, style, "", parts=("looks",)), images))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        for label, ass_text, imgs in jobs:
            print(f"layer: {label}")
            export_overlay(ass_text, imgs, tl, style, out / f"{label}.mov", Path(tmp))
    print(f"layers -> {out}  (put base.mp4 on the main track, every .mov above it, all starting at 0:00)")


# ---------- images (cover, carousel, story cards) ----------

def wrap_text(draw, text, font, max_w):
    lines = []
    for para in str(text).split("\n"):
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


def draw_block(img, text, font, color, box, center_y, max_w, line_gap=1.2, align="center", left=0):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    lines = wrap_text(draw, text, font, max_w)
    lh = int(font.size * line_gap)
    y = int(center_y - lh * len(lines) / 2)
    for line in lines:
        tw = draw.textlength(line, font=font)
        x = (img.width - tw) / 2 if align == "center" else left
        if box:
            p = font.size * 0.25
            draw.rounded_rectangle([x - p, y - p * 0.6, x + tw + p, y + lh - p * 0.2], radius=int(p), fill=box)
        draw.text((x, y), line, font=font, fill=color)
        y += lh
    return y


def text_height(img, text, font, max_w, line_gap=1.2):
    from PIL import ImageDraw
    return int(font.size * line_gap) * len(wrap_text(ImageDraw.Draw(img), text, font, max_w))


def make_cover_image(frame, hook, style, out):
    from PIL import Image
    img = Image.open(frame).convert("RGB")
    if hook:
        hk = style["hook"]
        font = get_font(style["caption"], int(img.width * 0.085))
        draw_block(img, hook, font, hk["color"], hk["box"], img.height * 0.45, img.width * 0.82)
    img.save(out, quality=92)


def photo_bg(frame, W, H, dim):
    from PIL import Image
    bg = Image.open(frame).convert("RGB")
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * scale), int(bg.height * scale)))
    left, top = (bg.width - W) // 2, int((bg.height - H) * 0.4)
    img = bg.crop((left, top, left + W, top + H))
    return Image.blend(img, Image.new("RGB", (W, H), "#000000"), dim)


def clean_frames(d, edit, tl, n, tmp):
    """n caption-free frames spread across the edited reel, grabbed straight from the source."""
    src = find_source(d)
    info = probe(src)
    frames = []
    segs = [s for s in tl["segs"] if not s.get("teaser")]
    for k in range(n):
        t = tl["total"] * (k + 0.5) / n
        seg = next((s for s in segs if s["out"] <= t < s["out"] + s["e"] - s["s"]), segs[-1])
        path = Path(tmp) / f"frame_{k:02d}.png"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{seg['s'] + (t - seg['out']):.3f}", "-i", str(src),
             "-frames:v", "1", "-vf", crop_filter(info, tl["style"], 1.0), str(path)])
        frames.append(path)
    return frames


def make_carousel(d, slides, style, frames):
    """Slides are plain strings, or {"kicker", "title", "body", "bullets": [...], "photo": bool}."""
    from PIL import Image, ImageDraw
    cs = style["carousel"]
    W, H = cs["width"], cs["height"]
    out = d / "out" / "carousel"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("slide_*.png"):
        old.unlink()
    small = get_font(cs, int(cs["size"] * 0.45))
    margin = 90
    for n, slide in enumerate(slides, 1):
        slide = {"title": slide} if isinstance(slide, str) else dict(slide)
        photo = slide.get("photo", n == 1 or cs.get("photo_every_slide", False))
        if photo and frames:
            img = photo_bg(frames[(n - 1) % len(frames)], W, H, cs.get("photo_dim", 0.45))
        else:
            img = Image.new("RGB", (W, H), cs["bg"])
        draw = ImageDraw.Draw(img)
        kicker = get_font(cs, int(cs["size"] * 0.55))
        title_font = get_font(cs, int(cs["size"] * (1.7 if slide.get("bullets") or slide.get("kicker") else 1.15)))
        body_font = get_font(cs, int(cs["size"] * 0.6))
        bullet_font = get_font(cs, int(cs["size"] * 0.5))
        bullets = slide.get("bullets", [])
        blocks = []  # (height, draw-fn)
        if slide.get("kicker"):
            blocks.append((text_height(img, slide["kicker"], kicker, W - 2 * margin),
                           lambda y, t=slide["kicker"]: draw_block(img, t, kicker, cs["text"], None, y, W - 2 * margin,
                                                                   align="left", left=margin)))
        th = text_height(img, slide.get("title", ""), title_font, W - 2 * margin, 1.05)
        blocks.append((th, lambda y: draw_block(img, slide.get("title", ""), title_font,
                                                cs["accent"] if bullets or slide.get("kicker") else cs["text"],
                                                None, y, W - 2 * margin, 1.05,
                                                align="left" if bullets or slide.get("kicker") else "center",
                                                left=margin)))
        if slide.get("body"):
            blocks.append((text_height(img, slide["body"], body_font, W - 2 * margin) + 30,
                           lambda y: draw_block(img, slide["body"], body_font, cs["text"], None, y + 30,
                                                W - 2 * margin, align="left", left=margin)))
        pill_h = int(bullet_font.size * 2.0)
        for b in bullets:
            def pill(y, b=b):
                top = y - pill_h // 2 + 14
                draw.rounded_rectangle([margin, top, W - margin, top + pill_h], radius=pill_h // 2, fill=cs["pill"])
                dot = pill_h * 0.18
                cy = top + pill_h / 2
                draw.ellipse([margin + 34 - dot, cy - dot, margin + 34 + dot, cy + dot], fill=cs["accent"])
                draw.text((margin + 70, cy), b, font=bullet_font, fill=cs["pill_text"], anchor="lm")
            blocks.append((pill_h + 22, pill))
        total_h = sum(h for h, _ in blocks)
        y = H * 0.5 - total_h / 2 if not bullets else H * 0.56 - total_h / 2
        for h, fn in blocks:
            fn(y + h / 2)
            y += h
        draw.rectangle([margin, 110, margin + 120, 122], fill=cs["accent"])
        draw.text((W - margin, H - 80), f"{n}/{len(slides)}", font=small, fill=cs["accent"], anchor="rs")
        if n < len(slides):
            draw.text((margin, H - 80), "swipe →", font=small, fill=cs["text"], anchor="ls")
        img.save(out / f"slide_{n:02d}.png")
    print(f"carousel: {len(slides)} slides -> {out}")


def make_story_cards(d, cards, style, frames):
    """Designed story frames: {"text", "sub", "sticker": "poll|question|link|quiz|none"}."""
    from PIL import ImageDraw
    st, cs = style["stories"], style["carousel"]
    W, H = 1080, 1920
    out = d / "out" / "stories"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("card_*.png"):
        old.unlink()
    title = get_font(cs, 84)
    sub = get_font(cs, 46)
    hint = get_font(cs, 38)
    for n, card in enumerate(cards, 1):
        card = {"text": card} if isinstance(card, str) else card
        img = photo_bg(frames[(n - 1) % len(frames)], W, H, st.get("photo_dim", 0.35))
        draw = ImageDraw.Draw(img)
        y = draw_block(img, card.get("text", ""), title, st["text"], st["box"], H * 0.3, W - 200)
        if card.get("sub"):
            draw_block(img, card["sub"], sub, st["text"], None, y + 80, W - 220)
        sticker = card.get("sticker")
        if sticker and sticker != "none":
            top, bottom = int(H * 0.56), int(H * 0.56) + 260
            draw.rounded_rectangle([170, top, W - 170, bottom], radius=40, outline=st["text"], width=5)
            label = f"add your {sticker.upper()} sticker here"
            if card.get("options"):
                label += "\n" + "  /  ".join(card["options"])
            draw_block(img, label, hint, st["text"], None, (top + bottom) / 2, W - 400)
        img.save(out / f"card_{n:02d}.png")
    print(f"story cards: {len(cards)} -> {out}")


# ---------- repurposing ----------

def make_stories(d, reel, tl, max_len):
    out = d / "out" / "stories"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("story_*.mp4"):
        old.unlink()
    total = tl["total"]
    bounds = [s["out"] for s in tl["segs"][1:]] + [total]
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
    edit = load_edit(d)
    reel = d / "out" / "reel.mp4"
    if not reel.exists():
        render(name)
    tl = timeline(d, edit)
    style = tl["style"]

    with tempfile.TemporaryDirectory(dir=d / "out") as tmp:
        need_frames = (only in (None, "carousel") and edit.get("carousel")) or \
                      (only in (None, "stories") and edit.get("stories"))
        frames = clean_frames(d, edit, tl, 8, tmp) if need_frames else []
        if only in (None, "carousel"):
            if edit.get("carousel"):
                make_carousel(d, edit["carousel"], style, frames)
            else:
                print("carousel: skipped (edit.json 'carousel' is empty)")
        if only in (None, "stories"):
            make_stories(d, reel, tl, style["stories"]["max_len"])
            if edit.get("stories"):
                make_story_cards(d, edit["stories"], style, frames)
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


def new(name, videos):
    """Copy one or more videos into a new project (several are joined in the order given)."""
    d = PROJECTS / name
    (d / "clips").mkdir(parents=True, exist_ok=True)
    for n, video in enumerate(videos, 1):
        video = Path(video).expanduser()
        if not video.exists():
            die(f"{video} not found")
        shutil.copy(video, d / "clips" / f"{n:03d}_{video.name}")
    join_clips(d)
    print(f"project {d}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p_new = sub.add_parser("new")
    p_new.add_argument("name")
    p_new.add_argument("video", nargs="+", help="one video, or several clips to join in this order")
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
    p = sub.add_parser("layers")
    p.add_argument("name")
    p.add_argument("--split-looks", action="store_true", help="one .mov per look instead of one for all")
    p = sub.add_parser("takes", help="list lines said more than once (retakes)")
    p.add_argument("name")
    for cmd in ("studio", "app"):
        p = sub.add_parser(cmd)
        if cmd == "studio":
            p.add_argument("name")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    try:
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
        elif a.cmd == "layers":
            layers(a.name, a.split_looks)
        elif a.cmd == "takes":
            words = load_json(project_dir(a.name) / "transcript.json")["words"]
            for g in find_takes(words):
                print(f"said {len(g['takes'])} times:")
                for k, t in enumerate(g["takes"]):
                    mark = "*" if k == g["suggested"] else " "
                    print(f"  {mark} [{t['from']}-{t['to']}] {t['text']}")
        elif a.cmd in ("studio", "app"):
            from studio import serve
            serve(getattr(a, "name", None), a.port, not a.no_browser)
    except ReelError as e:
        print("error: " + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
