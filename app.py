"""Swap Studio - remplace un visage dans une vidéo par un avatar.
ENGINE=mock (démo, sans GPU) ou ENGINE=facefusion (réel, GPU conseillé)."""
import os, uuid, queue, threading, subprocess, subprocess as sp
import cv2, numpy as np
from flask import Flask, request, jsonify, send_from_directory, abort

DATA = os.environ.get("DATA_DIR", "data")
ENGINE = os.environ.get("ENGINE", "mock")
os.makedirs(DATA, exist_ok=True)
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_MB", 100)) * 2**20
JOBS, Q = {}, queue.Queue()

def run(cmd, cwd=None):
    sp.run(cmd, check=True, capture_output=True, cwd=cwd)

def paste(f, av, b):
    x, y, w, h = map(int, b); p = int(w * .15)
    x, y, w, h = x - p, y - p, w + 2 * p, h + 2 * p
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, f.shape[1]), min(y + h, f.shape[0])
    if x1 <= x0 or y1 <= y0: return f
    a = cv2.resize(av, (w, h)).astype(np.float32)
    m = np.zeros((h, w), np.float32)
    cv2.ellipse(m, (w // 2, h // 2), (w // 2 - 2, h // 2 - 2), 0, 0, 360, 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), max(w / 12, 1))[..., None]
    a, m = a[y0 - y:y1 - y, x0 - x:x1 - x], m[y0 - y:y1 - y, x0 - x:x1 - x]
    r = f[y0:y1, x0:x1].astype(np.float32)
    f[y0:y1, x0:x1] = (a * m + r * (1 - m)).astype(np.uint8)
    return f

def mock_swap(video, avatar, out, progress):
    """Simulation : détecte le visage et colle l'avatar. Pas de vrai face swap."""
    av = cv2.imread(avatar); cap = cv2.VideoCapture(video)
    fps, n = cap.get(5) or 25, int(cap.get(7)) or 1
    w, h = int(cap.get(3)), int(cap.get(4))
    wr = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    s = int(h * .4); box = ((w - s) // 2, (h - s) // 2, s, s); i = 0
    while True:
        ok, f = cap.read()
        if not ok: break
        fs = det.detectMultiScale(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(40, 40))
        if len(fs): box = max(fs, key=lambda b: b[2] * b[3])
        wr.write(paste(f, av, box)); i += 1; progress(i / n)
    wr.release()

def ff_swap(video, avatar, out, progress):
    """Vrai face swap via FaceFusion (https://github.com/facefusion/facefusion)."""
    cmd = os.environ.get("FF_CMD", "python facefusion.py headless-run").split()
    run(cmd + ["-s", avatar, "-t", video, "-o", out], cwd=os.environ.get("FF_DIR", "facefusion"))
    progress(1)

def finalize(raw, orig, out):
    """Remet le son d'origine, encode en H.264 et ajoute la mention IA."""
    base = ["ffmpeg", "-y", "-i", raw, "-i", orig, "-map", "0:v", "-map", "1:a?"]
    end = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", out]
    wm = "drawtext=text='Généré par IA':x=w-tw-12:y=h-th-12:fontsize=h/32:fontcolor=white:box=1:boxcolor=black@0.45:boxborderw=6"
    try: run(base + ["-vf", wm] + end)
    except sp.CalledProcessError: run(base + end)

def worker():
    while True:
        jid = Q.get(); j = JOBS[jid]; d = os.path.join(DATA, jid)
        try:
            j.update(status="processing")
            run(["ffmpeg", "-y", "-i", f"{d}/in", "-t", "30", "-vf", "scale=-2:'min(720,ih)'",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", f"{d}/orig.mp4"])
            fn = mock_swap if ENGINE == "mock" else ff_swap
            fn(f"{d}/orig.mp4", f"{d}/avatar", f"{d}/raw.mp4", lambda p: j.update(progress=round(p * .9, 3)))
            finalize(f"{d}/raw.mp4", f"{d}/orig.mp4", f"{d}/result.mp4")
            j.update(status="done", progress=1)
        except Exception as e:
            msg = getattr(e, "stderr", b"") or str(e).encode()
            j.update(status="error", error=msg.decode(errors="ignore")[-300:])

threading.Thread(target=worker, daemon=True).start()

@app.get("/")
def index(): return app.send_static_file("index.html")

@app.post("/api/jobs")
def create():
    if request.form.get("consent") != "1":
        return jsonify(error="Le consentement est obligatoire."), 400
    v, a = request.files.get("video"), request.files.get("avatar")
    if not v or not a: return jsonify(error="Ajoute une vidéo et un avatar."), 400
    jid = uuid.uuid4().hex; d = os.path.join(DATA, jid); os.makedirs(d)
    v.save(f"{d}/in"); a.save(f"{d}/avatar")
    if cv2.imread(f"{d}/avatar") is None:
        return jsonify(error="L'avatar doit être une image (JPG, PNG)."), 400
    JOBS[jid] = dict(status="queued", progress=0)
    Q.put(jid); return jsonify(id=jid)

@app.get("/api/jobs/<jid>")
def status(jid):
    j = JOBS.get(jid) or abort(404)
    return jsonify({**j, "position": list(Q.queue).index(jid) + 1 if jid in Q.queue else 0})

@app.get("/files/<jid>/<name>")
def files(jid, name):
    if jid not in JOBS or name not in ("orig.mp4", "result.mp4"): abort(404)
    return send_from_directory(os.path.join(DATA, jid), name, conditional=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
