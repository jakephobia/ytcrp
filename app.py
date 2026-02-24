"""
Backend per il tool HTML: scarica video da YouTube e ritaglia in portrait 9:16.
Download con yt-dlp (evita bot detection). Ritaglio con ffmpeg se disponibile.
Progress reale via job: POST restituisce job_id, polling su GET /api/status/<id>, download su GET /api/result/<id>.
"""

import os
import re
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, request, send_file, jsonify, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

# Job state: job_id -> { progress: 0..100, stage: str, error: str|None, result_path: str|None, done: bool, tmpdir: str }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Cache anteprima: un solo entry (url -> path video) per riuso senza riscaricare
_preview_cache: dict[str, str] = {}  # url -> tmpdir (con video dentro)
_preview_lock = threading.Lock()

MAX_DURATION = 600  # secondi
ZOOM_PCT_MAX = 30   # zoom/crop massimo (0..30%), usato da download e preview
YT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w-]+"
)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ytdlp_cmd() -> list[str]:
    """Comando per invocare yt-dlp (binario o modulo Python)."""
    for cmd in (["yt-dlp"], [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]):
        try:
            subprocess.run(cmd + ["--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return []


def download_youtube(
    url: str,
    out_dir: str,
    out_basename: str,
    progress_callback: None = None,
) -> tuple[bool, str | None]:
    """Scarica solo video con yt-dlp (evita bot detection). progress_callback(0..50) opzionale."""
    ytdlp = _ytdlp_cmd()
    if not ytdlp:
        return (False, "yt-dlp non disponibile. Esegui: pip install yt-dlp")
    out_tpl = os.path.join(out_dir, out_basename + ".%(ext)s")
    try:
        if progress_callback:
            progress_callback(5.0)
        cmd = ytdlp + [
            "--no-warnings",
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]/bestvideo/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", out_tpl,
            url,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
            text=True,
            cwd=out_dir,
        )
        if progress_callback:
            progress_callback(50.0)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or "Download fallito"
            if "bot" in err.lower() or "blocked" in err.lower() or "403" in err:
                err = "YouTube ha bloccato la richiesta. Riprova più tardi o usa un altro video."
            return (False, err[:500])
        path = get_downloaded_path(out_dir, out_basename)
        if not path or not Path(path).stat().st_size:
            return (False, "File scaricato vuoto.")
        return (True, None)
    except subprocess.TimeoutExpired:
        return (False, "Timeout: video troppo lungo o connessione lenta.")
    except Exception as e:
        return (False, str(e)[:500])


def get_downloaded_path(base_dir: str, base_name: str) -> str | None:
    base = Path(base_dir) / base_name
    if base.exists():
        return str(base)
    for p in Path(base_dir).glob(base_name + "*"):
        if p.is_file():
            return str(p)
    for p in Path(base_dir).iterdir():
        if p.is_file() and p.suffix.lower() in (".mp4", ".webm", ".mkv", ".3gp"):
            return str(p)
    return None


def _zoom_filter(zoom_pct: float) -> str:
    """Filtro ffmpeg per crop 9:16 portrait + zoom (z = 1 - zoom_pct/100)."""
    z = round(1 - zoom_pct / 100.0, 6)  # precisione per evitare drift
    return (
        f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
        f"crop=iw*{z}:ih*{z}:(iw-iw*{z})/2:(ih-ih*{z})/2,"
        f"scale=iw/{z}:ih/{z}"
    )


def _no_cache_headers():
    """Header per evitare cache su risposte immagine/video."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


def crop_to_portrait(input_path: str, output_path: str, zoom_pct: float = 7) -> bool:
    """Crop 9:16 portrait centrato con zoom (es. 7% = taglia ~3.5% per lato e scala)."""
    crop_filter = _zoom_filter(zoom_pct)
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", crop_filter, "-an", "-movflags", "+faststart",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_duration_sec(input_path: str) -> float | None:
    """Durata video in secondi (ffprobe)."""
    cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        if result.returncode != 0:
            return None
        s = (result.stdout or "").strip()
        return float(s) if s else None
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


def extract_preview_frame(input_path: str, zoom_pct: float, output_path: str) -> bool:
    """Estrae un frame a metà video con crop 9:16 + zoom, salva come PNG."""
    dur = _get_duration_sec(input_path)
    t = (dur / 2.0) if dur and dur > 0 else 1.0
    t = max(0.5, t)
    vf = _zoom_filter(zoom_pct)
    # -ss prima di -i per seek veloce
    cmd = [
        "ffmpeg", "-y", "-ss", str(t), "-i", input_path,
        "-vf", vf, "-vframes", "1", output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=90, text=True)
        if result.returncode != 0:
            return False
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _run_job(job_id: str, url: str, zoom_pct: float = 7) -> None:
    def set_progress(progress: float, stage: str = "") -> None:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["progress"] = min(100, max(0, progress))
                if stage:
                    _jobs[job_id]["stage"] = stage

    tmpdir = tempfile.mkdtemp()
    with _jobs_lock:
        _jobs[job_id]["tmpdir"] = tmpdir
    base_name = "video"
    try:
        set_progress(0, "download")
        ok, err = download_youtube(
            url, tmpdir, base_name,
            progress_callback=lambda p: set_progress(p, "download"),
        )
        if not ok:
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["error"] = err or "Impossibile scaricare il video"
                    _jobs[job_id]["done"] = True
            return
        set_progress(50, "elaborazione")
        input_path = get_downloaded_path(tmpdir, base_name)
        if not input_path:
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["error"] = "Errore file scaricato"
                    _jobs[job_id]["done"] = True
            return

        if ffmpeg_available():
            set_progress(60, "ritaglio portrait con zoom")
            portrait_path = os.path.join(tmpdir, "portrait.mp4")
            if crop_to_portrait(input_path, portrait_path, zoom_pct=zoom_pct):
                with _jobs_lock:
                    if job_id in _jobs:
                        _jobs[job_id]["result_path"] = portrait_path
                        _jobs[job_id]["progress"] = 100
                        _jobs[job_id]["stage"] = "completato"
                        _jobs[job_id]["done"] = True
                return
        set_progress(100, "completato")
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["result_path"] = input_path
                _jobs[job_id]["done"] = True
    except Exception as e:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["done"] = True


@app.after_request
def add_headers(resp):
    """CORS e divieto indicizzazione motori di ricerca."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    return resp


@app.route("/robots.txt")
def robots_txt():
    """Impedisce crawling di tutto il sito."""
    return (
        "User-agent: *\nDisallow: /\n",
        200,
        {"Content-Type": "text/plain"},
    )


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory("css", filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory("js", filename)


def _normalize_url(url: str) -> str:
    match = YT_PATTERN.search(url)
    if not match:
        return ""
    u = match.group(0)
    return u if u.startswith("http") else "https://" + u


@app.route("/api/download", methods=["POST", "OPTIONS"])
def download_start():
    if request.method == "OPTIONS":
        return "", 204
    try:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "URL mancante"}), 400
        url = _normalize_url(url)
        if not url:
            return jsonify({"ok": False, "error": "Link YouTube non valido"}), 400

        zoom_pct = 7
        try:
            z = float(data.get("zoom", 7))
            zoom_pct = max(0, min(ZOOM_PCT_MAX, z))
        except (TypeError, ValueError):
            pass

        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {
                "progress": 0,
                "stage": "avvio",
                "error": None,
                "result_path": None,
                "done": False,
                "tmpdir": None,
            }
        thread = threading.Thread(target=_run_job, args=(job_id, url), kwargs={"zoom_pct": zoom_pct}, daemon=True)
        thread.start()
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/preview", methods=["POST", "OPTIONS"])
def preview_frame():
    """Anteprima: un frame a metà video con crop 9:16 + zoom. Ritorna PNG."""
    if request.method == "OPTIONS":
        return "", 204
    try:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "URL mancante"}), 400
        url = _normalize_url(url)
        if not url:
            return jsonify({"ok": False, "error": "Link YouTube non valido"}), 400

        zoom_pct = 7
        try:
            z = float(data.get("zoom", 7))
            zoom_pct = max(0, min(ZOOM_PCT_MAX, z))
        except (TypeError, ValueError):
            pass

        with _preview_lock:
            cached_dir = _preview_cache.get(url)
            if cached_dir and os.path.isdir(cached_dir):
                input_path = get_downloaded_path(cached_dir, "video")
                if input_path and os.path.isfile(input_path):
                    zoom_int = int(round(zoom_pct))
                    zoom_int = max(0, min(ZOOM_PCT_MAX, zoom_int))
                    out_png = os.path.join(cached_dir, f"preview_{zoom_int}.png")
                    if extract_preview_frame(input_path, zoom_pct, out_png):
                        r = send_file(out_png, mimetype="image/png")
                        r.headers.update(_no_cache_headers())
                        return r
                    return jsonify({"ok": False, "error": "Errore estrazione frame"}), 500

            tmpdir = tempfile.mkdtemp()
            ok, err = download_youtube(url, tmpdir, "video")
            if not ok:
                try:
                    for f in Path(tmpdir).iterdir():
                        f.unlink(missing_ok=True)
                    os.rmdir(tmpdir)
                except OSError:
                    pass
                return jsonify({"ok": False, "error": err or "Download fallito"}), 502
            input_path = get_downloaded_path(tmpdir, "video")
            if not input_path:
                try:
                    for f in Path(tmpdir).iterdir():
                        f.unlink(missing_ok=True)
                    os.rmdir(tmpdir)
                except OSError:
                    pass
                return jsonify({"ok": False, "error": "File non trovato"}), 502
            # Sostituisci cache: rimuovi vecchio tmpdir se diverso
            old_dir = _preview_cache.pop(url, None)
            _preview_cache[url] = tmpdir
            if old_dir and old_dir != tmpdir and os.path.isdir(old_dir):
                try:
                    for f in Path(old_dir).iterdir():
                        f.unlink(missing_ok=True)
                    os.rmdir(old_dir)
                except OSError:
                    pass

        if not ffmpeg_available():
            return jsonify({"ok": False, "error": "ffmpeg non disponibile"}), 503
        zoom_int = int(round(zoom_pct))
        zoom_int = max(0, min(ZOOM_PCT_MAX, zoom_int))
        out_png = os.path.join(tmpdir, f"preview_{zoom_int}.png")
        if not extract_preview_frame(input_path, zoom_pct, out_png):
            return jsonify({"ok": False, "error": "Impossibile estrarre il frame (ffmpeg). Riprova."}), 500
        r = send_file(
            out_png,
            mimetype="image/png",
            as_attachment=False,
        )
        r.headers.update(_no_cache_headers())
        return r
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/status/<job_id>")
def download_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job non trovato"}), 404
    out = {
        "ok": True,
        "progress": job["progress"],
        "stage": job["stage"],
        "done": job["done"],
        "error": job["error"],
    }
    if job["done"] and job["result_path"]:
        out["download_url"] = f"/api/result/{job_id}"
    return jsonify(out)


@app.route("/api/result/<job_id>")
def download_result(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job non trovato"}), 404
    path = job.get("result_path")
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "File non disponibile"}), 404
    name = "video_portrait.mp4" if "portrait" in path else "video.mp4"
    try:
        with _jobs_lock:
            _jobs.pop(job_id, None)
        r = send_file(
            path,
            as_attachment=True,
            download_name=name,
            mimetype="video/mp4",
        )
        r.headers.update(_no_cache_headers())
        return r
    finally:
        tmpdir = job.get("tmpdir")
        if tmpdir and os.path.isdir(tmpdir):
            try:
                for f in Path(tmpdir).iterdir():
                    f.unlink(missing_ok=True)
                os.rmdir(tmpdir)
            except OSError:
                pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
