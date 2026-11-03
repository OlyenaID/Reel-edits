"""Local web studio for a reel project: live preview, cut by the word, looks, sound, export.

Started by `python reel.py studio <name>`. Serves studio/index.html and a tiny JSON API on 127.0.0.1.
Everything it changes lands in projects/<name>/edit.json, so Claude Code and the studio can edit the
same reel at the same time: the page picks up Claude's edits within a couple of seconds.
"""
import json
import mimetypes
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import reel

STUDIO_HTML = reel.ROOT / "studio" / "index.html"
JOB_COMMANDS = {
    "preview": ["render", "--preview"],
    "render": ["render"],
    "repurpose": ["repurpose"],
    "carousel": ["repurpose", "--only", "carousel"],
    "stories": ["repurpose", "--only", "stories"],
    "trials": ["repurpose", "--only", "trials"],
    "layers": ["layers"],
    "layers-split": ["layers", "--split-looks"],
}


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.name, self.log, self.running, self.ok = None, "", False, None

    def start(self, project, kind):
        with self.lock:
            if self.running:
                return False
            self.name, self.log, self.running, self.ok = kind, "", True, None
        cmd = [sys.executable, "-u", str(reel.ROOT / "reel.py"), JOB_COMMANDS[kind][0], project,
               *JOB_COMMANDS[kind][1:]]
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def _run(self, cmd):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=reel.ROOT)
        for line in proc.stdout:
            with self.lock:
                self.log = (self.log + line.replace("\r", "\n"))[-20000:]
        proc.wait()
        with self.lock:
            self.running, self.ok = False, proc.returncode == 0

    def state(self):
        with self.lock:
            return {"name": self.name, "log": self.log, "running": self.running, "ok": self.ok}


def ensure_proxy(d, src, fmt):
    """Small, seek-friendly copy of the footage for the browser (keyframe every 0.5s)."""
    out = d / ".studio" / f"proxy.{fmt}"
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    out.parent.mkdir(exist_ok=True)
    print(f"preparing {fmt} preview copy of the footage (one time)...")
    scale = "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'"
    codec = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac",
              "-movflags", "+faststart"] if fmt == "mp4" else
             ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "1500k", "-c:a", "libopus"])
    tmp = out.with_name("tmp_" + out.name)
    reel.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", scale, "-g", "15", "-keyint_min", "15",
              *codec, str(tmp)])
    tmp.replace(out)
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
        out["outputs"] = sorted(str(p.relative_to(d)) for p in (d / "out").rglob("*")
                                if p.is_file() and not p.name.startswith("tmp") and "/tmp" not in str(p))
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


def serve(name, port=8765, open_browser=True):
    d = reel.project_dir(name)
    src = reel.find_source(d)
    info = reel.probe(src)
    words = reel.load_json(d / "transcript.json")["words"]
    edit_path = d / "edit.json"
    if not edit_path.exists():
        reel.save_json(edit_path, reel.DEFAULT_EDIT)
    job = Job()
    ensure_proxy(d, src, "mp4")

    def mtime():
        return edit_path.stat().st_mtime_ns

    def state():
        edit = reel.load_edit(d)
        return {
            "name": name, "words": words, "info": info, "source": src.name, "edit": edit,
            "mtime": mtime(), "plan": plan_payload(d, edit, info, words),
            "styles": reel.style_names(), "sfx_names": reel.sfx_names(), "files": project_files(d),
            "look_types": reel.LOOK_TYPES, "job": job.state(),
        }

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

        def send_file(self, path):
            if not path.is_file():
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

        def safe(self, base, rel):
            path = (base / unquote(rel)).resolve()
            return path if base.resolve() in path.parents or path == base.resolve() else None

        def do_GET(self):
            url = urlparse(self.path)
            p = url.path
            try:
                if p == "/":
                    return self.send_file(STUDIO_HTML)
                if p == "/api/state":
                    return self.send_json(state())
                if p == "/api/poll":
                    return self.send_json({"mtime": mtime(), "job": job.state(), "files": project_files(d)})
                if p in ("/proxy.mp4", "/proxy.webm"):
                    return self.send_file(ensure_proxy(d, src, p.rsplit(".", 1)[1]))
                if p.startswith("/media/"):
                    path = self.safe(d, p[len("/media/"):])
                    return self.send_file(path) if path else self.send_error(403)
                if p.startswith("/sfx/"):
                    return self.send_file(reel.sfx_path(unquote(p[len("/sfx/"):])))
                self.send_error(404)
            except reel.ReelError as e:
                self.send_json({"error": str(e)}, 400)

        def do_POST(self):
            p = urlparse(self.path).path
            try:
                if p == "/api/plan":
                    edit = reel.deep_merge(reel.DEFAULT_EDIT, self.read_json())
                    return self.send_json(plan_payload(d, edit, info, words))
                if p == "/api/save":
                    edit = reel.deep_merge(reel.DEFAULT_EDIT, self.read_json())
                    reel.save_json(edit_path, edit)
                    return self.send_json({"mtime": mtime(), "plan": plan_payload(d, edit, info, words)})
                if p == "/api/job":
                    kind = self.read_json().get("kind")
                    if kind not in JOB_COMMANDS:
                        return self.send_json({"error": "unknown job"}, 400)
                    return self.send_json({"started": job.start(name, kind), "job": job.state()})
                if p == "/api/save-style":
                    body = self.read_json()
                    style_name = "".join(ch for ch in body["name"].lower().replace(" ", "-")
                                         if ch.isalnum() or ch == "-")
                    if not style_name or style_name == "default":
                        return self.send_json({"error": "pick another name"}, 400)
                    edit = reel.load_edit(d)
                    base = {} if edit["style"] == "default" else reel.load_json(reel.STYLES / f"{edit['style']}.json")
                    pack = reel.deep_merge(base, edit.get("style_overrides") or {})
                    pack["name"] = style_name
                    reel.save_json(reel.STYLES / f"{style_name}.json", pack)
                    edit["style"], edit["style_overrides"] = style_name, {}
                    reel.save_json(edit_path, edit)
                    return self.send_json({"style": style_name})
                if p == "/api/upload":
                    fname = Path(unquote(self.headers.get("X-Filename", ""))).name
                    if Path(fname).suffix.lower() not in reel.AUDIO_EXT | reel.IMAGE_EXT:
                        return self.send_json({"error": "only images and audio"}, 400)
                    n = int(self.headers.get("Content-Length", 0))
                    (d / fname).write_bytes(self.rfile.read(n))
                    return self.send_json({"file": fname})
                self.send_error(404)
            except reel.ReelError as e:
                self.send_json({"error": str(e)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"studio for '{name}' -> {url}   (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstudio stopped")
