"""
Logica condivisa: download YouTube con yt-dlp e ritaglio portrait 9:16 con zoom.
Usato da app Flask e dal bot Telegram.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

ZOOM_PCT_MAX = 30
MAX_DURATION = 600
YT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w-]+(?:\&[^\s]*)?"
)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ytdlp_cmd() -> list[str]:
    for cmd in (["yt-dlp"], [os.environ.get("PYTHON", "python"), "-m", "yt_dlp"]):
        try:
            subprocess.run(cmd + ["--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return []


def normalize_youtube_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    match = YT_PATTERN.search(url)
    if not match:
        return ""
    u = match.group(0)
    return u if u.startswith("http") else "https://" + u


def download_youtube(
    url: str,
    out_dir: str,
    out_basename: str,
    progress_callback: None = None,
) -> tuple[bool, str | None]:
    """Scarica solo video con yt-dlp. progress_callback(0..50) opzionale."""
    ytdlp = _ytdlp_cmd()
    if not ytdlp:
        return (False, "yt-dlp non disponibile. Esegui: pip install yt-dlp")
    out_tpl = os.path.join(out_dir, out_basename + ".%(ext)s")
    try:
        if progress_callback:
            progress_callback(5.0)
        # Due tentativi: prima formato di qualità, poi "best" se il formato non è disponibile
        format_specs = [
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/bestvideo/best",
            "best",
        ]
        last_err = ""
        proxy = (os.environ.get("YT_PROXY") or os.environ.get("TELEGRAM_YT_PROXY") or "").strip()
        proxy_args = ["--proxy", proxy] if proxy else []
        for client in ("tv_simply", "android_vr"):
            for format_spec in format_specs:
                cmd = ytdlp + [
                    "--no-warnings",
                    "--no-playlist",
                    "--extractor-args", f"youtube:player_client={client}",
                    "-f", format_spec,
                    "--merge-output-format", "mp4",
                    "-o", out_tpl,
                ] + proxy_args + [url]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=600,
                    text=True,
                    cwd=out_dir,
                )
                if progress_callback:
                    progress_callback(50.0)
                if result.returncode == 0:
                    path = get_downloaded_path(out_dir, out_basename)
                    if path and Path(path).stat().st_size:
                        return (True, None)
                last_err = (result.stderr or result.stdout or "").strip()
                if "not available" in last_err.lower() or "requested format" in last_err.lower():
                    continue  # prova formato successivo
                if "bot" in last_err.lower() or "blocked" in last_err.lower() or "403" in last_err or "Sign in" in last_err:
                    break  # passa al prossimo client
                return (False, last_err[:500] or "Download fallito")
        path = get_downloaded_path(out_dir, out_basename)
        if path and Path(path).stat().st_size:
            return (True, None)
        return (False, last_err[:500] if last_err else "YouTube ha bloccato la richiesta. Riprova più tardi.")
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
    z = round(1 - zoom_pct / 100.0, 6)
    return (
        f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
        f"crop=iw*{z}:ih*{z}:(iw-iw*{z})/2:(ih-ih*{z})/2,"
        f"scale=iw/{z}:ih/{z}"
    )


def crop_to_portrait(input_path: str, output_path: str, zoom_pct: float = 7) -> bool:
    # Scala a max 720p per ridurre dimensione file e upload più veloce (evita NetworkError)
    crop_filter = _zoom_filter(zoom_pct) + ",scale=-2:720"
    # -threads 2 riduce uso RAM/CPU su hosting con risorse limitate (es. Railway)
    cmd = [
        "ffmpeg", "-y", "-threads", "2", "-i", input_path,
        "-vf", crop_filter, "-an", "-movflags", "+faststart",
        "-crf", "28",
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


def download_for_preview(url: str) -> tuple[str | None, str | None]:
    """Scarica il video in una cartella temporanea per anteprima/crop. Ritorna (tmpdir, None) o (None, errore)."""
    tmpdir = tempfile.mkdtemp()
    ok, err = download_youtube(url, tmpdir, "video")
    if not ok:
        try:
            for f in Path(tmpdir).iterdir():
                f.unlink(missing_ok=True)
            os.rmdir(tmpdir)
        except OSError:
            pass
        return (None, err)
    return (tmpdir, None)


def run_download_and_crop(
    url: str,
    zoom_pct: float = 7,
    progress_callback=None,
) -> tuple[bool, str | None, str | None]:
    """
    Scarica il video da url, ritaglia in portrait con zoom, restituisce path del file finale.
    progress_callback(stage: str, progress: float) opzionale.
    Ritorna (ok, error_message, output_path). output_path è in una cartella temporanea.
    """
    tmpdir = tempfile.mkdtemp()
    base_name = "video"
    try:
        if progress_callback:
            progress_callback("download", 0)
        ok, err = download_youtube(
            url, tmpdir, base_name,
            progress_callback=lambda p: progress_callback("download", p) if progress_callback else None,
        )
        if not ok:
            return (False, err, None)
        if progress_callback:
            progress_callback("elaborazione", 50)
        input_path = get_downloaded_path(tmpdir, base_name)
        if not input_path:
            return (False, "Errore file scaricato", None)
        if ffmpeg_available():
            if progress_callback:
                progress_callback("ritaglio portrait", 70)
            portrait_path = os.path.join(tmpdir, "portrait.mp4")
            if crop_to_portrait(input_path, portrait_path, zoom_pct=zoom_pct):
                if progress_callback:
                    progress_callback("completato", 100)
                return (True, None, portrait_path)
        if progress_callback:
            progress_callback("completato", 100)
        return (True, None, input_path)
    except Exception as e:
        return (False, str(e)[:500], None)
