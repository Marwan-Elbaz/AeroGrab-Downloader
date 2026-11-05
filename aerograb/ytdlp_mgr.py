# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import zipfile
import hashlib
import urllib.request, urllib.parse, urllib.error
import threading
import re
from aerograb.common import log_error
from aerograb.config import APP_VERSION, YTDLP_CACHE_DIR, YTDLP_VERSION_FILE
from aerograb.netutil import _urlopen


# ----------------------------------------------------------------------------- yt-dlp update / import
def _read_cache_meta():
    try:
        with open(YTDLP_VERSION_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except Exception:
        return None, None
    ver, _, app = raw.partition("|")
    return (ver or None), (app or None)



def _drop_stale_cache():
    """لو النسخة المخزنة اتعملت مع إصدار قديم من البرنامج نمسحها، عشان متغطيش على yt-dlp الأحدث المرفق."""
    _, app = _read_cache_meta()
    if os.path.isdir(YTDLP_CACHE_DIR) and app != APP_VERSION:
        shutil.rmtree(YTDLP_CACHE_DIR, ignore_errors=True)
        try:
            os.remove(YTDLP_VERSION_FILE)
        except OSError:
            pass



_drop_stale_cache()

if os.path.isdir(YTDLP_CACHE_DIR):
    sys.path.insert(0, YTDLP_CACHE_DIR)



def _py_satisfies(spec, py=None):
    """بيفحص requires_python زي '>=3.9' (نسخة مبسّطة)."""
    py = py or sys.version_info[:2]
    try:
        for part in (spec or "").split(","):
            m = re.match(r"\s*(>=|>|<=|<|==|!=)\s*(\d+)\.(\d+)", part)
            if not m:
                continue
            op, tgt = m.group(1), (int(m.group(2)), int(m.group(3)))
            ok = {">=": py >= tgt, ">": py > tgt, "<=": py <= tgt, "<": py < tgt, "==": py == tgt, "!=": py != tgt}[op]
            if not ok:
                return False
    except Exception:
        pass
    return True



def _fetch_latest_ytdlp_info(timeout=8, py=None):
    """بيرجّع (version, wheel_url, sha256, is_newest). is_newest=False معناها إن أحدث إصدار محتاج بايثون أحدث من اللي عندك."""
    try:
        req = urllib.request.Request("https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "aerograb-updater"})
        with _urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        releases = data.get("releases", {})
        newest = data["info"]["version"]

        def key(v):
            return tuple(int(x) for x in re.findall(r"\d+", v)[:5])

        stable = sorted((v for v in releases if releases[v] and re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}(\.post\d+)?", v)),
                        key=key, reverse=True)
        for v in stable:
            for u in releases[v]:
                if (u.get("packagetype") == "bdist_wheel" and u.get("filename", "").endswith(".whl")
                        and not u.get("yanked") and _py_satisfies(u.get("requires_python"), py)):
                    return v, u["url"], (u.get("digests") or {}).get("sha256"), v == newest
    except Exception as e:
        log_error("fetch_latest_ytdlp_info", e)
    return None, None, None, True



def _download_and_extract_wheel(wheel_url, sha256, dest_dir):
    tmp_zip = dest_dir + ".whl.tmp"
    tmp_extract = dest_dir + ".new"
    try:
        if not sha256:
            raise ValueError("no checksum published")
        h = hashlib.sha256()
        req = urllib.request.Request(wheel_url, headers={"User-Agent": "aerograb-updater"})
        with _urlopen(req, timeout=30) as r, open(tmp_zip, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest().lower() != sha256.lower():
            raise ValueError("checksum mismatch")
        shutil.rmtree(tmp_extract, ignore_errors=True)
        os.makedirs(tmp_extract, exist_ok=True)
        with zipfile.ZipFile(tmp_zip, "r") as z:
            z.extractall(tmp_extract)
        if not os.path.exists(os.path.join(tmp_extract, "yt_dlp", "__init__.py")):
            raise ValueError("wheel has no yt_dlp package")
        shutil.rmtree(dest_dir, ignore_errors=True)
        os.replace(tmp_extract, dest_dir)
        return True
    except Exception as e:
        log_error("download_and_extract_wheel", e)
        shutil.rmtree(tmp_extract, ignore_errors=True)
        return False
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass



def check_and_update_ytdlp_async(on_result=None):
    """on_result(status, version) : status = updated | latest | error  (بيتنادى من thread الخلفية)."""
    def worker():
        try:
            latest, wheel_url, sha, is_newest = _fetch_latest_ytdlp_info()
            if not latest or not wheel_url:
                res = ("error", None)
            elif latest == _read_cache_meta()[0] and os.path.isdir(YTDLP_CACHE_DIR):
                res = ("latest", latest)
            elif _download_and_extract_wheel(wheel_url, sha, YTDLP_CACHE_DIR):
                with open(YTDLP_VERSION_FILE, "w", encoding="utf-8") as f:
                    f.write(f"{latest}|{APP_VERSION}")
                res = ("updated", latest)
            else:
                res = ("error", None)
        except Exception as e:
            log_error("ytdlp update worker", e)
            res = ("error", None)
        if res[0] in ("updated", "latest") and not is_newest:
            res = (res[0] + "_old", res[1])      # الأحدث محتاج بايثون أجدد من اللي عندك
        if on_result:
            on_result(*res)
    threading.Thread(target=worker, daemon=True).start()



yt_dlp = None

_ytdlp_lock = threading.Lock()



def ensure_ytdlp():
    """بيحمّل yt-dlp مرة واحدة، ولو النسخة المحدّثة بايظة بيرجع للنسخة المرفقة."""
    global yt_dlp
    if yt_dlp is not None:
        return yt_dlp
    with _ytdlp_lock:
        if yt_dlp is not None:
            return yt_dlp
        try:
            import yt_dlp as _y
        except Exception as e:
            log_error("import yt_dlp (cached build)", e)
            if YTDLP_CACHE_DIR in sys.path:
                sys.path.remove(YTDLP_CACHE_DIR)
            for m in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                del sys.modules[m]
            shutil.rmtree(YTDLP_CACHE_DIR, ignore_errors=True)
            import yt_dlp as _y
        yt_dlp = _y
        try:
            from aerograb.downloader import install_segmented_downloader   # استيراد كسول: بيكسر دايرة ytdlp_mgr <-> downloader
            install_segmented_downloader(_y)
        except Exception as e:
            log_error("install_segmented_downloader", e)
        return yt_dlp
