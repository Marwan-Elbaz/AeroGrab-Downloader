# -*- coding: utf-8 -*-
import os
import urllib.request, urllib.parse, urllib.error
import re


# ----------------------------------------------------------------------------- Helpers
def clean_terminal_text(text):
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(text)).strip() if text else ""



URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)



def is_valid_url(text):
    return bool(text) and bool(URL_PATTERN.match(text.strip()))



DIRECT_EXTS = {
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img",
    "exe", "msi", "apk", "dmg", "pkg", "deb", "rpm",
    "mp4", "mkv", "avi", "mov", "flv", "wmv", "webm", "m4v", "mpg", "mpeg", "3gp",
    "mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "wma",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
}



def is_direct_file_url(url):
    """لينك ملف مباشر (مش صفحة فيديو)."""
    try:
        p = urllib.parse.urlparse(url)
        host = (p.hostname or "").lower()
        if host.endswith("youtube.com") or host.endswith("youtu.be"):
            return False
        ext = os.path.splitext(urllib.parse.unquote(p.path))[1].lstrip(".").lower()
        return ext in DIRECT_EXTS
    except Exception:
        return False



def fmt_bytes(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024



def fmt_speed(bps):
    return f"{fmt_bytes(bps)}/s" if bps else "-"



def fmt_eta(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "-"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"



def fmt_pct(p):
    return f"{p:.1f}%"



def friendly_error(msg):
    m = clean_terminal_text(msg).replace("ERROR:", "").strip()
    low = m.lower()
    rules = [
        (("sign in to confirm", "not a bot"), "YouTube wants sign-in (put cookies.txt next to the app)"),
        (("confirm your age", "age-restricted", "age restricted"), "Age-restricted video (needs cookies.txt)"),
        (("private video",), "Private video"),
        (("video unavailable", "this video is not available", "has been removed"), "Video unavailable"),
        (("ffmpeg", "ffprobe"), "ffmpeg is missing or failed"),
        (("no space left", "errno 28", "not enough space"), "Disk is full: free some space, then Resume"),
        (("http error 410", "410: gone"), "Link expired (410): right-click > Refresh link"),
        (("http error 403", "403: forbidden"), "Access denied (403): if the link expired, right-click > Refresh link"),
        (("http error 404", "404: not found"), "File not found (404)"),
        (("http error 429", "too many requests"), "Too many requests (429), try later"),
        (("requested format is not available",), "Selected quality is not available for this video (pick another quality)"),
        (("getaddrinfo", "urlopen error", "timed out", "connection reset", "network is unreachable", "remote end closed", "connection refused", "failed to establish", "unable to download webpage"), "Network problem"),
        (("permission denied", "errno 13"), "No permission to write in the save folder"),
    ]
    for keys, text in rules:
        if any(k in low for k in keys):
            return text
    return (m or "Unknown error")[:80]



# ----------------------------------------------------------------------------- Quality / formats
QUALITY_MAP = {
    "1080p": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
    "720p": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best",
    "480p": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best",
    "360p": "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best",
    "240p": "bestvideo[ext=mp4][height<=240]+bestaudio[ext=m4a]/bestvideo[height<=240]+bestaudio/best",
    "144p": "bestvideo[ext=mp4][height<=144]+bestaudio[ext=m4a]/bestvideo[height<=144]+bestaudio/best",
    "Audio Only": "bestaudio[ext=m4a]/bestaudio/best",
}

STANDARD_HEIGHTS = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "240p": 240, "144p": 144}



_ff_cache = {"t": 0.0, "v": ""}


EXT_KIND = {}

for _k, _exts in {
    "video": "mp4 mkv avi mov flv wmv webm m4v mpg mpeg 3gp",
    "audio": "mp3 wav flac m4a aac ogg opus wma",
    "archive": "zip rar 7z tar gz bz2 xz iso img",
    "app": "exe msi apk dmg pkg deb rpm",
    "doc": "pdf doc docx xls xlsx ppt pptx txt epub",
}.items():
    for _e in _exts.split():
        EXT_KIND[_e] = _k



def stream_size(f, dur=0):
    """
    (bytes, exact) لصيغة واحدة من yt-dlp.
    exact=True لو الرقم مأخوذ من السيرفر فعلاً (filesize أو clen في رابط يوتيوب)، وإلا تقدير من filesize_approx أو معدل البت × المدة.
    """
    try:
        s = f.get("filesize")
        if s:
            return int(s), True
        m = re.search(r"[?&/]clen[=/](\d+)", f.get("url") or "")
        if m:
            return int(m.group(1)), True
        s = f.get("filesize_approx")
        if s:
            return int(s), False
        if dur and f.get("tbr"):
            return int(f["tbr"] * 1000 / 8 * dur), False
    except Exception:
        pass
    return 0, False
