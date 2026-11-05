# -*- coding: utf-8 -*-
"""
التحديث التلقائي للبرنامج (زي البرامج الكبيرة) عن طريق GitHub Releases.

إزاي بتنشر تحديث؟
  1) غيّر APP_VERSION في aerograb/config.py (مثلاً "4.1").
  2) ابني النسخة:  python build_release.py   (بيطلع AeroGrab-4.1.zip جوه مجلد release/)
  3) على GitHub اعمل Release جديد: Tag = v4.1  وارفع ملف الـ zip (أو Setup.exe لو عندك مثبّت).
  4) خلاص: كل نسخة منتشرة عند أي مستخدم هتلاقي التحديث لوحدها وتسأل المستخدم وتثبّته وتعيد التشغيل.

المطلوب مرة واحدة: حط "owner/repo" في aerograb/links.py → UPDATE_REPO.

طريقة التثبيت:
  - ملف *.zip (نسخة onedir من PyInstaller): بينزّل → يفك → سكربت صغير بيستنى البرنامج يقفل ويبدّل الملفات ويشغّل البرنامج.
  - ملف *Setup*.exe / *.msi (مثبّت): بيتنزّل وبيتشغّل والبرنامج بيقفل.
  - لو البرنامج شغّال من السورس (python main.py): بيفتح صفحة الإصدار في المتصفح بس.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

from aerograb.common import get_setting, log_error, save_settings
from aerograb.config import APP_DATA_DIR, APP_VERSION, FROZEN, IS_WINDOWS
from aerograb.links import UPDATE_REPO

CHECK_EVERY = 6 * 3600          # بنفحص كل 6 ساعات كحد أقصى
UPDATE_DIR = os.path.join(APP_DATA_DIR, "update")

# آخر نتيجة فحص (بتتقرا من الواجهة): None أو dict(version, notes, page, asset_url, asset_name, size)
available = {"info": None, "checked": 0.0}
_lock = threading.Lock()


def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4]) or (0,)


def is_newer(latest, current=APP_VERSION):
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def enabled():
    return bool(UPDATE_REPO.strip())


def _urlopen(req, timeout=15):
    from aerograb.netutil import _urlopen as _u          # نفس إعدادات البروكسي والشهادات بتاعة باقي البرنامج
    return _u(req, timeout=timeout)


def _installed_copy():
    """True لو البرنامج متثبّت بمثبّت Inno (فيه ملف unins000.exe جنب البرنامج)."""
    try:
        return os.path.exists(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "unins000.exe"))
    except Exception:
        return False


def _pick_asset(assets):
    """بنفضّل المثبّت لو موجود (لو البرنامج متثبّت)، وإلا الـ zip."""
    zips = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    tag = "x64" if sys.maxsize > 2 ** 32 else "x86"           # نفس معمارية البرنامج الشغّال (32 أو 64 بت)
    zips = [a for a in zips if f"-{tag}" in a["name"].lower()] or [a for a in zips if "-x86" not in a["name"].lower() and "-x64" not in a["name"].lower()]
    exes = [a for a in assets if re.search(r"(setup|installer).*\.(exe|msi)$", a.get("name", "").lower())]
    exes = [a for a in exes if f"-{tag}" in a["name"].lower()] or [a for a in exes if "-x86" not in a["name"].lower() and "-x64" not in a["name"].lower()]
    if FROZEN and IS_WINDOWS and exes and _installed_copy():
        return exes[0]                    # النسخة متثبّتة بالمثبّت: التحديث بالمثبّت عشان رقم الإصدار في Apps & features يتحدّث
    if FROZEN and zips:
        return zips[0]
    return (exes or zips or [None])[0]


def fetch_latest():
    """بيرجّع dict بالإصدار الأحدث (حتى لو مش أحدث من الحالي)، أو يرمي استثناء لو فشل الاتصال."""
    if not enabled():
        raise RuntimeError("UPDATE_REPO is empty")
    url = f"https://api.github.com/repos/{UPDATE_REPO.strip()}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "aerograb-updater", "Accept": "application/vnd.github+json"})
    with _urlopen(req) as r:
        data = json.loads(r.read().decode("utf-8"))
    asset = _pick_asset(data.get("assets") or [])
    return {
        "version": str(data.get("tag_name") or "").lstrip("vV"),
        "notes": (data.get("body") or "").strip(),
        "page": data.get("html_url") or f"https://github.com/{UPDATE_REPO}/releases",
        "asset_url": (asset or {}).get("browser_download_url"),
        "asset_name": (asset or {}).get("name"),
        "size": (asset or {}).get("size") or 0,
    }


def check_async(on_result, force=False):
    """on_result(status, info): status = 'new' | 'latest' | 'error' | 'disabled'. بيتنادى من thread الخلفية."""
    def worker():
        try:
            if not enabled():
                on_result("disabled", None)
                return
            if not force and not get_setting("auto_update", True):
                return
            if not force and time.time() - float(get_setting("update_last_check", 0) or 0) < CHECK_EVERY:
                info = available["info"]
                if info:
                    on_result("new", info)
                return
            info = fetch_latest()
            save_settings("update_last_check", time.time())
            available["checked"] = time.time()
            if is_newer(info["version"]):
                available["info"] = info
                on_result("new", info)
            else:
                available["info"] = None
                on_result("latest", info)
        except Exception as e:
            log_error("update check", e)
            on_result("error", None)
    threading.Thread(target=worker, daemon=True, name="aerograb-update-check").start()


def download(info, on_progress=None, should_stop=None):
    """بينزّل ملف التحديث لمجلد التحديثات. بيرجّع المسار. on_progress(done, total)."""
    os.makedirs(UPDATE_DIR, exist_ok=True)
    dest = os.path.join(UPDATE_DIR, re.sub(r"[^\w.\-]", "_", info["asset_name"] or "update.zip"))
    tmp = dest + ".part"
    req = urllib.request.Request(info["asset_url"], headers={"User-Agent": "aerograb-updater"})
    with _urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        done = 0
        while True:
            if should_stop and should_stop():
                raise RuntimeError("canceled")
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    if info.get("size") and os.path.getsize(tmp) != int(info["size"]):
        raise RuntimeError("incomplete update download")
    os.replace(tmp, dest)
    return dest


def _app_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def _write_swap_script(src_dir, dst_dir, exe_path):
    """سكربت بيستنى البرنامج يقفل، يبدّل الملفات (مع نسخة احتياطية)، ويشغّل البرنامج من جديد."""
    bat = os.path.join(UPDATE_DIR, "apply_update.bat")
    log = os.path.join(UPDATE_DIR, "apply_update.log")
    backup = dst_dir.rstrip("\\/") + "_old"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'echo [%date% %time%] waiting for AeroGrab to close > "{log}"',
        "set /a tries=0",
        ":wait",
        f'tasklist /FI "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul',
        "if not errorlevel 1 (",
        "  set /a tries+=1",
        "  if %tries% GTR 60 goto copy",
        "  timeout /t 1 /nobreak >nul",
        "  goto wait",
        ")",
        ":copy",
        f'if exist "{backup}" rmdir /s /q "{backup}"',
        f'xcopy "{dst_dir}" "{backup}\\" /E /I /Y /Q >nul',
        f'xcopy "{src_dir}\\*" "{dst_dir}\\" /E /I /Y /Q >> "{log}" 2>&1',
        "if errorlevel 1 (",
        f'  echo update failed, restoring backup >> "{log}"',
        f'  xcopy "{backup}\\*" "{dst_dir}\\" /E /I /Y /Q >nul',
        ")",
        f'start "" "{exe_path}" --restarted',
        f'rmdir /s /q "{os.path.join(UPDATE_DIR, "extracted")}" >nul 2>&1',
        '(goto) 2>nul & del "%~f0"',
    ]
    with open(bat, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")
    return bat


def prepare_install(path):
    """بيجهّز التثبيت. بيرجّع ('restart', None) لو لازم نقفل البرنامج دلوقتي، أو ('browser', url)."""
    low = path.lower()
    if not IS_WINDOWS:
        return "browser", None
    if low.endswith((".exe", ".msi")):
        if low.endswith(".msi"):
            subprocess.Popen(["msiexec", "/i", path], close_fds=True)
        elif re.search(r"setup|installer", os.path.basename(low)) and _installed_copy():
            # تحديث صامت: من غير ويزارد، بيقفل البرنامج، يستبدل الملفات، ويفتحه تاني
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"], close_fds=True)
        else:
            subprocess.Popen([path], close_fds=True)
        return "restart", None
    if low.endswith(".zip") and FROZEN:
        ext = os.path.join(UPDATE_DIR, "extracted")
        shutil.rmtree(ext, ignore_errors=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(ext)
        root = ext
        entries = [e for e in os.listdir(ext) if not e.startswith("__")]
        if len(entries) == 1 and os.path.isdir(os.path.join(ext, entries[0])):
            root = os.path.join(ext, entries[0])             # الـ zip جواه مجلد واحد
        exe_name = os.path.basename(sys.executable)
        if not os.path.exists(os.path.join(root, exe_name)):
            raise RuntimeError("the update package does not contain " + exe_name)
        bat = _write_swap_script(root, _app_dir(), sys.executable)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(["cmd", "/c", bat], close_fds=True, creationflags=flags)
        return "restart", None
    return "browser", None
