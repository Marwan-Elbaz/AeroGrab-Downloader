# -*- coding: utf-8 -*-
import os
import urllib.request, urllib.parse, urllib.error
import threading
import logging, logging.handlers
import copy
import re
import io
import time
from PIL import Image
from aerograb.common import log_error
from aerograb.config import USER_AGENT
from aerograb.fmt import STANDARD_HEIGHTS, fmt_bytes, is_direct_file_url, is_valid_url
from aerograb.netutil import _urlopen
from aerograb.fmt import stream_size
from aerograb.tools import base_ydl_opts, find_ffmpeg, format_for, h264_enabled
from aerograb.ytdlp_mgr import ensure_ytdlp


# ----------------------------------------------------------------------------- Direct probe + yt-dlp info
def probe_direct(url, referer=""):
    """اسم + حجم لملف مباشر من غير yt-dlp."""
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    size, name = None, None
    for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        try:
            req = urllib.request.Request(url, method=method, headers={**headers, **extra})
            with _urlopen(req, timeout=6) as r:
                cr = r.headers.get("Content-Range")
                cl = r.headers.get("Content-Length")
                if cr and "/" in cr and cr.rsplit("/", 1)[-1].isdigit():
                    size = int(cr.rsplit("/", 1)[-1])
                elif cl and cl.isdigit() and r.status != 206:
                    size = int(cl)
                cd = r.headers.get("Content-Disposition") or ""
                m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
                if m:
                    name = urllib.parse.unquote(m.group(1).strip())
                break
        except Exception:
            continue
    if not name:
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path)) or urllib.parse.urlparse(url).netloc
    return name, (fmt_bytes(size) if size else "")



# ----------------------------------------------------------------------------- أدوات الوقت + قوائم التشغيل + تفاصيل الفيديو
def parse_time(text):
    """'90' / '1:30' / '01:02:03' / '1h2m3s' / '12.5'  ->  ثواني (float)، أو None لو مش مفهوم."""
    s = str(text or "").strip().lower().replace(",", ".")
    if not s:
        return None
    try:
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return float(s)
        if re.fullmatch(r"\d+(\.\d+)?(:\d+(\.\d+)?){1,2}", s):
            parts = [float(p) for p in s.split(":")]
            sec = 0.0
            for p in parts:
                sec = sec * 60 + p
            return sec
        m = re.fullmatch(r"(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", s)
        if m and any(m.groups()):
            h, mi, se = (float(g) if g else 0.0 for g in m.groups())
            return h * 3600 + mi * 60 + se
    except Exception:
        pass
    return None



def fmt_hms(sec):
    try:
        sec = int(round(float(sec)))
    except Exception:
        return "00:00"
    h, rem = divmod(max(0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"



def _is_youtube_host(host):
    host = (host or "").lower()
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com") or host.endswith("youtube-nocookie.com")



def youtube_list_id(url):
    """رقم قائمة التشغيل (من غير قوائم الـ Mix التلقائية RD...)."""
    try:
        u = urllib.parse.urlparse(url)
        if not _is_youtube_host(u.hostname):
            return None
        lid = (urllib.parse.parse_qs(u.query).get("list") or [None])[0]
        return lid if lid and re.fullmatch(r"[\w-]{10,64}", lid) and not lid.startswith("RD") else None
    except Exception:
        return None



def is_playlist_page(url):
    try:
        return bool(youtube_list_id(url)) and urllib.parse.urlparse(url).path.rstrip("/") == "/playlist"
    except Exception:
        return False



def playlist_url_of(url):
    lid = youtube_list_id(url)
    return f"https://www.youtube.com/playlist?list={lid}" if lid else url



def _fmt_list(info):
    """نسخة خفيفة من formats: (height, vcodec, acodec, size_bytes, exact)."""
    dur = info.get("duration") or 0
    out = []
    for f in (info.get("formats") or []):
        size, exact = stream_size(f, dur)
        out.append({"h": int(f.get("height") or 0), "w": int(f.get("width") or 0), "note": str(f.get("format_note") or ""),
                    "v": f.get("vcodec") or "none", "a": f.get("acodec") or "none", "size": int(size or 0), "exact": exact})
    return out



def _is_quality(f, h):
    """هل الصيغة دي هي الجودة h بالظبط (نفس شروط format_for)؟"""
    return f["h"] == h or (f.get("w") == h and f["h"] > h) or f.get("note", "").startswith(f"{h}p")



def qualities_from_fmts(fmts, h264=None):
    """الجودات الموجودة فعلاً للفيديو ده (مفيش جودة بتظهر وهي مش متاحة بالظبط)."""
    h264 = h264_enabled() if h264 is None else h264
    video = [f for f in fmts if f["v"] != "none" and (f["h"] or f.get("w"))]
    h264_video = [f for f in video if f["v"].startswith("avc1")]
    pool = h264_video if (h264 and h264_video) else video      # نعرض بس الجودات اللي متاحة H.264 مباشرة (من غير تحويل)
    result = [label for label, h in STANDARD_HEIGHTS.items() if any(_is_quality(f, h) for f in pool)]
    if not result:
        result = [label for label, h in STANDARD_HEIGHTS.items() if any(_is_quality(f, h) for f in video)]
    if any(f["v"] == "none" and f["a"] != "none" for f in fmts):
        result.append("Audio Only")
    return result



def estimate_size(fmts, quality, h264=None):
    """تقدير حجم الفيديو (بالبايت) للجودة دي بالظبط من غير أي طلب شبكة. 0 = مش معروف."""
    h264 = h264_enabled() if h264 is None else h264
    audio = max([f["size"] for f in fmts if f["v"] == "none" and f["a"] != "none"] or [0])
    if quality == "Audio Only":
        return audio
    h = STANDARD_HEIGHTS.get(quality, 1080)
    cands = [f for f in fmts if f["v"] != "none" and _is_quality(f, h)]
    if h264:
        cands = [f for f in cands if f["v"].startswith("avc1")] or cands
    if not cands:
        return 0
    best = max(cands, key=lambda f: f["size"])
    if best["a"] != "none":
        return best["size"]
    return best["size"] + audio if best["size"] else 0



def fetch_media_details(url, quality, referer="", direct=False):
    """تفاصيل الفيديو لنافذة التأكيد: العنوان، الصورة، المدة، القناة، الجودات المتاحة، الحجم."""
    d = {"title": "", "pil": None, "size": "", "duration": None, "uploader": "", "qualities": [], "fmts": [], "direct": False}
    if direct or is_direct_file_url(url):
        name, size = probe_direct(url, referer)
        d.update(title=name, size=size, direct=True)
        return d
    try:
        y = ensure_ytdlp()
        opts = base_ydl_opts()
        opts["skip_download"] = True
        if referer:
            opts["http_headers"] = {**(opts.get("http_headers") or {}), "Referer": referer}     # من غير ما نمسح User-Agent المخصص
        with y.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise RuntimeError("no info")
        fmts = _fmt_list(info)
        d.update(title=info.get("title") or "Unknown Video", duration=info.get("duration"),
                 uploader=info.get("uploader") or info.get("channel") or "", fmts=fmts,
                 qualities=qualities_from_fmts(fmts), info=info, sizes={})
        if d["qualities"]:
            with _fmt_lock:
                _fmt_cache[f"{int(h264_enabled())}|{url}"] = (time.time(), d["qualities"])
        q0 = quality if quality in d["qualities"] else (d["qualities"][0] if d["qualities"] else quality)
        b, ex = selected_size_ex(info, q0)
        if not b:
            b, ex = estimate_size(fmts, q0) or info.get("filesize") or info.get("filesize_approx") or 0, False
        d["sizes"][q0] = b
        d.setdefault("exact", {})[q0] = ex
        d["size"] = (("" if ex else "~") + fmt_bytes(b)) if b else ""
        thumb = info.get("thumbnail")
        if thumb:
            try:
                req = urllib.request.Request(thumb, headers={"User-Agent": "Mozilla/5.0"})
                d["pil"] = Image.open(io.BytesIO(_urlopen(req, timeout=6).read())).convert("RGB")
            except Exception:
                d["pil"] = None
        return d
    except Exception as e:
        log_error("fetch_media_details", e)
        _, size = probe_direct(url, referer)
        # "Unsupported URL" = yt-dlp مش فاهم الرابط ده فعلاً (ملف عادي): نحمّله مباشر. أي خطأ تاني (شبكة / خاص / محجوب)
        # بنسيبه يعدّي على yt-dlp عشان المستخدم يشوف السبب الحقيقي بدل ما نحاول نحمّل صفحة الفيديو كأنها ملف.
        d.update(title="🔗 Link is ready for download", size=size, direct=True, fallback_direct="unsupported url" in str(e).lower())
        return d



def fetch_playlist(url, limit=2000):
    """بيرجّع {title, uploader, entries:[{id,title,url,duration}]} من غير ما ينزّل حاجة."""
    y = ensure_ytdlp()
    opts = base_ydl_opts()
    opts.update({"noplaylist": False, "extract_flat": "in_playlist", "skip_download": True, "playlistend": limit,
                 "socket_timeout": 20})
    with y.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("Could not read the playlist")
    entries = []
    for e in (info.get("entries") or []):
        if not e:
            continue
        vid = e.get("id")
        title = e.get("title") or ""
        if title in ("[Private video]", "[Deleted video]", "[Unavailable video]"):
            continue
        u = e.get("webpage_url") or e.get("url") or ""
        if not is_valid_url(u):
            if vid and re.fullmatch(r"[\w-]{6,20}", str(vid)) and "youtube" in str(e.get("ie_key") or info.get("extractor") or "").lower():
                u = f"https://www.youtube.com/watch?v={vid}"
            else:
                continue
        entries.append({"id": vid or u, "title": title or u, "url": u, "duration": e.get("duration")})
    return {"title": info.get("title") or "Playlist", "uploader": info.get("uploader") or info.get("channel") or "",
            "entries": entries}



# ----------------------------------------------------------------------------- Qualities (للإضافة) + كاش
_fmt_cache = {}

_fmt_inflight = {}

_fmt_lock = threading.Lock()

FMT_TTL = 600



def get_available_qualities_for_url(url):
    try:
        y = ensure_ytdlp()
        opts = base_ydl_opts()
        opts.update({"skip_download": True, "socket_timeout": 12})
        with y.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return qualities_from_fmts(_fmt_list(info))
    except Exception as e:
        log_error(f"get_available_qualities_for_url {url}", e)
        return []



def get_qualities_cached(url):
    key = f"{int(h264_enabled())}|{url}"
    now = time.time()
    with _fmt_lock:
        hit = _fmt_cache.get(key)
        if hit and now - hit[0] < FMT_TTL:
            return hit[1]
        ev = _fmt_inflight.get(key)
        if ev is None:
            ev = threading.Event()
            _fmt_inflight[key] = ev
            owner = True
        else:
            owner = False
    if not owner:
        ev.wait(30)
        with _fmt_lock:
            hit = _fmt_cache.get(key)
        return hit[1] if hit else []
    try:
        res = get_available_qualities_for_url(url)
        if res:
            with _fmt_lock:
                if len(_fmt_cache) > 200:
                    _fmt_cache.clear()
                _fmt_cache[key] = (time.time(), res)
        return res
    finally:
        with _fmt_lock:
            _fmt_inflight.pop(key, None)
        ev.set()



# ----------------------------------------------------------------------------- Local HTTP server
EXT_ORIGIN_RE = re.compile(r"^(chrome-extension|moz-extension)://[a-z0-9\-]+$", re.IGNORECASE)

_recent_adds = {}

_recent_lock = threading.Lock()



def _head_length(f, timeout=5):
    """طلب HEAD خفيف لمعرفة الحجم الحقيقي لصيغة مالهاش حجم معروف (روابط مباشرة بس)."""
    try:
        url = f.get("url") or ""
        if not url.startswith(("http://", "https://")) or (f.get("protocol") or "https") not in ("http", "https"):
            return 0
        h = dict(f.get("http_headers") or {})
        req = urllib.request.Request(url, headers=h, method="HEAD")
        with _urlopen(req, timeout=timeout) as r:
            n = r.headers.get("Content-Length")
            return int(n) if n and n.isdigit() else 0
    except Exception:
        return 0


def selected_size_ex(info, quality):
    """
    (bytes, exact): حجم اللي yt-dlp هيختاره فعلاً للجودة دي (نفس اختيار الـ worker بالظبط).
    exact=False معناها تقدير (مفيش حجم من السيرفر، أو الفيديو هيتحوّل لـ H.264 بعد التحميل فحجمه النهائي هيتغيّر).
    """
    try:
        y = ensure_ytdlp()
        opts = base_ydl_opts()
        opts.update({"skip_download": True, "format": format_for(quality, bool(find_ffmpeg()))})
        with y.YoutubeDL(opts) as ydl:
            res = ydl.process_ie_result(copy.deepcopy(info), download=False)
        dur = res.get("duration") or 0
        total, exact = 0, True
        chosen = res.get("requested_formats") or [res]
        for f in chosen:
            sz, ex = stream_size(f, dur)
            if not sz:
                sz, ex = _head_length(f), True
                if not sz:
                    exact = False
                    continue
            total += sz
            exact = exact and ex
        if h264_enabled() and quality != "Audio Only":
            for f in chosen:
                vc = (f.get("vcodec") or "none").lower()
                if vc != "none" and not vc.startswith(("avc1", "h264")):
                    exact = False            # هيتحوّل لـ H.264 بعد التحميل: الحجم النهائي هيختلف
        return int(total), bool(total and exact)
    except Exception as e:
        logging.info(f"selected_size failed: {e}")
        return 0, False


def selected_size(info, quality):
    return selected_size_ex(info, quality)[0]
