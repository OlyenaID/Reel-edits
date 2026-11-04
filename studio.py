"""Reel Editor app: a local web app for all your reels (home screen, guided editor, live preview).

Started by `python reel.py app` (or the Reel Editor launcher). Serves studio/*.html and a small JSON API on
127.0.0.1 only. Everything the editor changes lands in projects/<name>/edit.json, so Claude Code and the
editor can work on the same reel at the same time: the page picks up Claude's edits within a couple of seconds.
"""
import json
import mimetypes
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import reel

HOME_HTML = reel.ROOT / "studio" / "home.html"
EDITOR_HTML = reel.ROOT / "studio" / "index.html"
JOB_COMMANDS = {
    "transcribe": ["transcribe"],
    "preview": ["render", "--preview"],
    "render": ["render"],
    "repurpose": ["repurpose"],
    "carousel": ["repurpose", "--only", "carousel"],
    "stories": ["repurpose", "--only", "stories"],
    "trials": ["repurpose", "--only", "trials"],
    "layers": ["layers"],
    "layers-split": ["layers", "--split-looks"],
}
MODELS = {"fast": "base", "balanced": "small", "accurate": "medium"}


class Job:
    """One background reel.py command per project, with a rough progress estimate for the page."""

    def __init__(self, project):
        self.project = project
        self.lock = threading.Lock()
        self.name, self.log, self.running, self.ok, self.progress = None, "", False, None, 0.0

    def start(self, kind, extra=()):
        with self.lock:
            if self.running:
                return False
            self.name, self.log, self.running, self.ok, self.progress = kind, "", True, None, 0.0
        cmd = [sys.executable, "-u", str(reel.ROOT / "reel.py"), JOB_COMMANDS[kind][0], self.project,
               *JOB_COMMANDS[kind][1:], *extra]
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def _run(self, cmd):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=reel.ROOT,
                                encoding="utf-8", errors="replace")
        for line in proc.stdout:
            for part in line.replace("\r", "\n").splitlines():
                m = re.match(r"progress ([\d.]+)", part.strip())
                cut = re.match(r"cut (\d+)/(\d+)", part.strip())
                with self.lock:
                    if m:
                        self.progress = float(m.group(1))
                        continue
                    if cut:
                        self.progress = 0.8 * int(cut.group(1)) / int(cut.group(2))
                    self.log = (self.log + part + "\n")[-20000:]
        proc.wait()
        ok = proc.returncode == 0
        if ok and self.name == "transcribe":
            with self.lock:
                self.log += "preparing the preview...\n"
            try:
                d = reel.project_dir(self.project)
                ensure_proxy(d, reel.find_source(d), "mp4")
            except reel.ReelError as e:
                ok = False
                with self.lock:
                    self.log += f"error: {e}\n"
        with self.lock:
            self.running, self.ok, self.progress = False, ok, 1.0 if ok else self.progress

    def state(self):
        with self.lock:
            return {"name": self.name, "log": self.log, "running": self.running, "ok": self.ok,
                    "progress": round(self.progress, 3)}


def ensure_proxy(d, src, fmt):
    """Small, seek-friendly copy of the footage for the browser (keyframe every 0.5s)."""
    out = d / ".studio" / f"proxy.{fmt}"
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    out.parent.mkdir(exist_ok=True)
    scale = "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'"
    codec = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac",
              "-movflags", "+faststart"] if fmt == "mp4" else
             ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "1500k", "-c:a", "libopus"])
    tmp = out.with_name("tmp_" + out.name)
    reel.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", scale, "-g", "15", "-keyint_min", "15",
              *codec, str(tmp)])
    tmp.replace(out)
    return out


def thumbnail(d):
    cover = d / "out" / "reel_cover.jpg"
    if cover.exists():
        return cover
    out = d / ".studio" / "thumb.jpg"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        reel.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(reel.find_source(d)), "-frames:v", "1",
                  "-vf", "scale=360:-2", str(out)])
    return out


def project_files(d):
    out = {"audio": [], "images": [], "outputs": []}
    for f in sorted(d.iterdir()):
        ext = f.suffix.lower()
        if ext in reel.AUDIO_EXT:
            out["audio"].append(f.name)
        elif ext in reel.IMAGE_EXT:
            out["images"].append(f.name)
    if (d / "out").exists():
        out["outputs"] = sorted(p.relative_to(d).as_posix() for p in (d / "out").rglob("*")
                                if p.is_file() and not any(part.startswith("tmp") for part in p.parts))
    return out


def plan_payload(d, edit, info, words):
    tl = reel.timeline(d, edit, info, words)
    slim = lambda w: {"i": w["i"], "w": w["w"], "os": round(w["os"], 3), "oe": round(w["oe"], 3),
                      "emph": w["emph"]}
    return {
        "style": tl["style"], "total": tl["total"],
        "segs": [{"s": s["s"], "e": s["e"], "out": s["out"], "zoom": s["zoom"], "teaser": bool(s.get("teaser"))}
                 for s in tl["segs"]],
        "chunks": [[slim(w) for w in c] for c in tl["chunks"]],
        "looks": tl["looks"], "sfx": tl["sfx"],
        "removed": {str(k): v for k, v in tl["removed"].items()},
    }


class App:
    def __init__(self):
        self.jobs = {}
        self.cache = {}  # project -> (transcript mtime, info, words)
        self.lock = threading.Lock()

    def job(self, name):
        with self.lock:
            return self.jobs.setdefault(name, Job(name))

    def project(self, name):
        d = reel.project_dir(name)
        tr = d / "transcript.json"
        if not tr.exists():
            reel.die("this reel is still being transcribed")
        key = tr.stat().st_mtime_ns
        cached = self.cache.get(name)
        if not cached or cached[0] != key:
            cached = (key, reel.probe(reel.find_source(d)), reel.load_json(tr)["words"])
            self.cache[name] = cached
        if not (d / "edit.json").exists():
            reel.save_json(d / "edit.json", reel.DEFAULT_EDIT)
        return d, cached[1], cached[2]

    def projects(self):
        out = []
        if not reel.PROJECTS.exists():
            return out
        for d in reel.PROJECTS.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            tr = d / "transcript.json"
            meta = reel.load_json(d / ".studio" / "meta.json", {}) if (d / ".studio" / "meta.json").exists() else {}
            item = {"name": d.name, "title": meta.get("title", d.name), "ready": tr.exists(),
                    "job": self.job(d.name).state(), "rendered": (d / "out" / "reel.mp4").exists()}
            edit_path = d / "edit.json"
            item["edited"] = max((p.stat().st_mtime for p in (edit_path, tr, d) if p.exists()), default=0)
            if tr.exists():
                item["duration"] = reel.load_json(tr).get("duration")
            out.append(item)
        return sorted(out, key=lambda p: -p["edited"])

    def state(self, name):
        d, info, words = self.project(name)
        edit = reel.load_edit(d)
        meta = reel.load_json(d / ".studio" / "meta.json", {}) if (d / ".studio" / "meta.json").exists() else {}
        return {
            "name": name, "title": meta.get("title", name), "words": words, "info": info, "edit": edit,
            "mtime": (d / "edit.json").stat().st_mtime_ns, "plan": plan_payload(d, edit, info, words),
            "takes": reel.find_takes(words), "styles": {n: reel.load_style(n) for n in reel.style_names()},
            "sfx_names": reel.sfx_names(), "files": project_files(d), "look_types": reel.LOOK_TYPES,
            "job": self.job(name).state(),
        }


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def save_body(self, path):
            left = int(self.headers.get("Content-Length", 0))
            tmp = path.with_name("tmp_" + path.name)
            with open(tmp, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                tmp.unlink(missing_ok=True)
                reel.die("upload was interrupted")
            tmp.replace(path)

        def send_file(self, path):
            if not path or not path.is_file():
                return self.send_error(404)
            size = path.stat().st_size
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a) if a else max(size - int(b), 0)
                end = min(int(b), size - 1) if a and b else end
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        @staticmethod
        def safe(base, rel):
            path = (base / unquote(rel)).resolve()
            return path if base.resolve() in path.parents else None

        def route(self):
            """Split /api/p/<name>/<rest> and /p/<name>/<rest> into (name, rest)."""
            m = re.match(r"^/(?:api/)?p/([^/]+)/(.*)$", urlparse(self.path).path)
            return (unquote(m.group(1)), m.group(2)) if m else (None, None)

        def do_GET(self):
            p = urlparse(self.path).path
            try:
                if p == "/":
                    return self.send_file(HOME_HTML)
                if p.startswith("/edit/"):
                    return self.send_file(EDITOR_HTML)
                if p == "/api/projects":
                    return self.send_json({"projects": app.projects()})
                if p.startswith("/sfx/"):
                    return self.send_file(reel.sfx_path(unquote(p[len("/sfx/"):])))
                name, rest = self.route()
                if name is None:
                    return self.send_error(404)
                if p.startswith("/api/"):
                    if rest == "state":
                        return self.send_json(app.state(name))
                    if rest == "poll":
                        d = reel.project_dir(name)
                        edit = d / "edit.json"
                        return self.send_json({"mtime": edit.stat().st_mtime_ns if edit.exists() else 0,
                                               "job": app.job(name).state(), "files": project_files(d)})
                    return self.send_error(404)
                d = reel.project_dir(name)
                if rest in ("proxy.mp4", "proxy.webm"):
                    return self.send_file(ensure_proxy(d, reel.find_source(d), rest.rsplit(".", 1)[1]))
                if rest == "thumb.jpg":
                    return self.send_file(thumbnail(d))
                if rest.startswith("media/"):
                    return self.send_file(self.safe(d, rest[len("media/"):]))
                self.send_error(404)
            except reel.ReelError as e:
                self.send_json({"error": str(e)}, 400)

        def do_POST(self):
            p = urlparse(self.path).path
            try:
                if p == "/api/new":
                    return self.new_project()
                name, rest = self.route()
                if name is None:
                    return self.send_error(404)
                if rest == "clip":
                    return self.add_clip(name)
                if rest in ("start", "retry"):
                    d = reel.project_dir(name)
                    meta = reel.load_json(d / ".studio" / "meta.json", {})
                    job = app.job(name)
                    return self.send_json({"started": job.start("transcribe", meta.get("transcribe_args", [])),
                                           "job": job.state()})
                if rest == "job":
                    body = self.read_json()
                    if body.get("kind") not in JOB_COMMANDS or body["kind"] == "transcribe":
                        return self.send_json({"error": "unknown job"}, 400)
                    job = app.job(name)
                    return self.send_json({"started": job.start(body["kind"]), "job": job.state()})
                d, info, words = app.project(name)
                if rest == "save":
                    edit = reel.deep_merge(reel.DEFAULT_EDIT, self.read_json())
                    reel.save_json(d / "edit.json", edit)
                    return self.send_json({"mtime": (d / "edit.json").stat().st_mtime_ns,
                                           "plan": plan_payload(d, edit, info, words)})
                if rest == "plan":
                    edit = reel.deep_merge(reel.DEFAULT_EDIT, self.read_json())
                    return self.send_json(plan_payload(d, edit, info, words))
                if rest == "save-style":
                    return self.save_style(d, self.read_json())
                if rest == "upload":
                    fname = Path(unquote(self.headers.get("X-Filename", ""))).name
                    if Path(fname).suffix.lower() not in reel.AUDIO_EXT | reel.IMAGE_EXT:
                        return self.send_json({"error": "only images and audio files"}, 400)
                    self.save_body(d / fname)
                    return self.send_json({"file": fname})
                self.send_error(404)
            except reel.ReelError as e:
                self.send_json({"error": str(e)}, 400)

        def new_project(self):
            """Create an empty reel; the page then uploads its clips one by one and calls /start."""
            q = parse_qs(urlparse(self.path).query)
            title = q.get("title", [""])[0].strip() or "My reel"
            name = reel.slugify(title)
            d = reel.PROJECTS / name
            (d / ".studio").mkdir(parents=True)
            (d / "clips").mkdir()
            extra = ["--model", MODELS.get(q.get("quality", ["balanced"])[0], "small")]
            if q.get("prompt", [""])[0].strip():
                extra += ["--prompt", q["prompt"][0].strip()]
            reel.save_json(d / ".studio" / "meta.json", {"title": title, "transcribe_args": extra})
            return self.send_json({"name": name})

        def add_clip(self, name):
            d = reel.project_dir(name)
            q = parse_qs(urlparse(self.path).query)
            filename = Path(unquote(self.headers.get("X-Filename", "video.mp4"))).name
            if Path(filename).suffix.lower() not in reel.VIDEO_EXT:
                return self.send_json({"error": f"“{filename}” doesn't look like a video"}, 400)
            n = int(q.get("n", ["1"])[0])
            (d / "clips").mkdir(exist_ok=True)
            self.save_body(d / "clips" / f"{n:03d}_{filename}")
            return self.send_json({"ok": True})

        def save_style(self, d, body):
            style_name = "".join(ch for ch in body.get("name", "").lower().replace(" ", "-")
                                 if ch.isalnum() or ch == "-")
            if not style_name or style_name == "default":
                return self.send_json({"error": "pick another name"}, 400)
            edit = reel.load_edit(d)
            base = {} if edit["style"] == "default" else reel.load_json(reel.STYLES / f"{edit['style']}.json")
            pack = reel.deep_merge(base, edit.get("style_overrides") or {})
            pack["name"] = style_name
            reel.save_json(reel.STYLES / f"{style_name}.json", pack)
            edit["style"], edit["style_overrides"] = style_name, {}
            reel.save_json(d / "edit.json", edit)
            return self.send_json({"style": style_name})

    return Handler


def serve(name=None, port=8765, open_browser=True):
    url = f"http://127.0.0.1:{port}/" + (f"edit/{name}" if name else "")
    if name:
        reel.project_dir(name)
    reel.PROJECTS.mkdir(exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App()))
    except OSError:
        # already running (e.g. the launcher was double-clicked twice): just open it
        print(f"Reel Editor is already running -> {url}")
        if open_browser:
            webbrowser.open(url)
        return
    print(f"Reel Editor is running -> {url}")
    print("Keep this window open while you edit. Close it (or press Ctrl+C) when you're done.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReel Editor stopped")
