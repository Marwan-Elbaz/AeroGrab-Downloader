# -*- coding: utf-8 -*-
import os
import shutil
import threading
import glob
import re
import subprocess
import time
import importlib
import sys
import zipfile
import platform
import urllib.request
from aerograb.common import YtLogger, get_setting, log_error
from aerograb.config import APP_DATA_DIR, COOKIES_PATH, HOME, IS_WINDOWS, RESOURCE_DIRS
from aerograb.fmt import QUALITY_MAP, STANDARD_HEIGHTS, _ff_cache
from aerograb.netutil import _proxy_url, custom_user_agent, net_timeout
from aerograb.ytdlp_mgr import ensure_ytdlp


def _registry_path_dirs():
    """PATH الحالي من الريجستري: البرنامج لما بيتفتح من المتصفح ممكن يكون واخد PATH قديم من قبل تثبيت ffmpeg."""
    out = []
    if not IS_WINDOWS:
        return out
    try:
        import winreg as _wr
        for hive, sub in ((_wr.HKEY_CURRENT_USER, "Environment"),
                          (_wr.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with _wr.OpenKey(hive, sub) as k:
                    val, _ = _wr.QueryValueEx(k, "Path")
                out += [os.path.expandvars(p.strip()) for p in str(val).split(";") if p.strip()]
            except OSError:
                pass
    except Exception:
        pass
    return out



def reset_ffmpeg_cache():
    _ff_cache["v"], _ff_cache["t"] = None, 0


def find_ffmpeg():
    custom = (get_setting("ffmpeg_path", "") or "").strip()
    if custom and os.path.isfile(custom):
        return custom                                  # المسار اللي اختاره المستخدم في الإعدادات
    now = time.time()
    c = _ff_cache
    if c["v"] and os.path.exists(c["v"]):
        return c["v"]
    if not c["v"] and c["t"] and now - c["t"] < 15:
        return None
    exe = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
    dirs = list(RESOURCE_DIRS) + [os.path.join(APP_DATA_DIR, "bin")] + _registry_path_dirs()
    if IS_WINDOWS:
        la = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
        pd = os.environ.get("ProgramData", r"C:\ProgramData")
        dirs += [r"C:\ffmpeg\bin", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ffmpeg", "bin"),
                 os.path.join(pd, "chocolatey", "bin"), os.path.join(la, "Microsoft", "WinGet", "Links"),
                 os.path.join(HOME, "scoop", "shims"), os.path.join(HOME, "ffmpeg", "bin")]
        dirs += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin"))
    else:
        dirs += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    found = shutil.which("ffmpeg")
    if not found:
        for d in dirs:
            p = os.path.join(d, exe)
            if os.path.isfile(p):
                found = p
                break
    c["t"], c["v"] = now, found or ""
    return found



def h264_enabled():
    """وضع التوافق: فيديو H.264 + صوت AAC (بيشتغل على الأجهزة والمشغلات القديمة)."""
    return bool(get_setting("h264_only", True))



def quality_filters(h):
    """
    شروط "الجودة دي بالظبط" (مش أقل ولا أعلى): الارتفاع = h، أو العرض = h في فيديو عمودي بس (الارتفاع أكبر من العرض)، أو اسم الجودة عند يوتيوب (1080p / 1080p60).
    الاسم بيغطي الفيديوهات سينمائي العرض اللي ارتفاعها الفعلي مختلف (مثلاً 1920x804 اسمها 1080p).
    """
    return (f"[height={h}]", f"[width={h}][height>{h}]", f"[format_note^={h}p]")



def format_for(q_text, have_ffmpeg=True, h264=None, level=0):
    """
    صيغة yt-dlp للجودة المختارة بالظبط. البرنامج عمره ما بينزّل جودة غير اللي اخترتها: لو الجودة مش موجودة
    التحميل بيفشل برسالة واضحة بدل ما ينزّل جودة تانية. المسموح بس هو اختلاف الكودك (مثلاً VP9 بدل H.264) بنفس الجودة،
    وفي وضع التوافق بنحوّله بعد التحميل لـ H.264. (level محفوظ للتوافق مع الكود القديم ومبيغيّرش الجودة.)
    """
    q = q_text if q_text in QUALITY_MAP else "1080p"
    if q == "Audio Only":
        return "bestaudio[ext=m4a]/bestaudio/best"
    h = STANDARD_HEIGHTS[q]
    sels = quality_filters(h)
    if h264 is None:
        h264 = h264_enabled()
    out = []
    if not have_ffmpeg:                       # من غير ffmpeg مفيش دمج فيديو+صوت، فنختار ملف واحد جاهز
        for sel in sels:
            out += [f"b{sel}[ext=mp4]", f"b{sel}"]
        return "/".join(out)
    if h264:
        for sel in sels:                      # H.264 + AAC الأول (بيشتغل على كل الأجهزة)
            out += [f"bv*[vcodec^=avc1]{sel}+ba[acodec^=mp4a]", f"bv*[vcodec^=avc1]{sel}+ba", f"b[vcodec^=avc1]{sel}"]
    else:
        for sel in sels:
            out += [f"bv*[ext=mp4]{sel}+ba[ext=m4a]"]
    for sel in sels:                          # نفس الجودة بأي كودك
        out += [f"bv*{sel}+ba", f"b{sel}"]
    return "/".join(out)



# مجموعات عملاء يوتيوب البديلة: لو الصيغ ماجتش (غالباً بسبب تحدّي الحماية)، بنجرّب عملاء تانيين
YT_CLIENT_FALLBACKS = (None, ["default", "tv"], ["mweb", "web_safari"], ["ios", "android_vr"])



# ----------------------------------------------------------------------------- YouTube engine (JS runtime + solver)
# يوتيوب بيخنق السرعة (10-100 KB/s) لو yt-dlp معرفش يحل تحدي الـ "n". الحل محتاج حاجتين:
#  1) مشغّل JavaScript: deno >= 2.3  أو  node >= 22  أو  bun >= 1.2.11
#  2) مكوّن yt-dlp-ejs (سكريبت الحل)
JS_MIN = {"deno": (2, 3, 0), "node": (22, 0, 0), "bun": (1, 2, 11)}

BIN_DIR = os.path.join(APP_DATA_DIR, "bin")

_NOWIN = 0x08000000 if IS_WINDOWS else 0          # CREATE_NO_WINDOW



def _search_dirs():
    dirs = [BIN_DIR] + RESOURCE_DIRS + [d for d in os.environ.get("PATH", "").split(os.pathsep) if d] + _registry_path_dirs()
    if IS_WINDOWS:
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
        dirs += [os.path.join(pf, "nodejs"), os.path.join(pf86, "nodejs"), os.path.join(la, "Programs", "nodejs"),
                 os.path.join(HOME, ".deno", "bin"), os.path.join(la, "Microsoft", "WinGet", "Links"),
                 os.path.join(HOME, "scoop", "shims"), os.path.join(HOME, ".bun", "bin")]
    else:
        dirs += [os.path.join(HOME, ".deno", "bin"), os.path.join(HOME, ".bun", "bin"),
                 "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"]
    seen, out = set(), []
    for d in dirs:
        k = os.path.normcase(os.path.abspath(d))
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out



def _exe_version(path):
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, errors="replace",
                           timeout=8, creationflags=_NOWIN)
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", (r.stdout or "") + (r.stderr or ""))
        return tuple(int(x) for x in m.groups()) if m else None
    except Exception:
        return None



_rt_cache = {"t": 0.0, "val": None}

_rt_lock = threading.Lock()



def js_runtime_report(force=False):
    """{name: {path, version, supported}} لكل مشغّل لقيناه (بنفضّل أول نسخة مدعومة)."""
    with _rt_lock:
        if not force and _rt_cache["val"] is not None and time.time() - _rt_cache["t"] < 120:
            return _rt_cache["val"]
        dirs = _search_dirs()
        report = {}
        for name in ("deno", "node", "bun"):
            first = None
            for d in dirs:
                p = os.path.join(d, name + (".exe" if IS_WINDOWS else ""))
                if not os.path.isfile(p) or (not IS_WINDOWS and not os.access(p, os.X_OK)):
                    continue
                ver = _exe_version(p)
                info = {"path": p, "version": ver, "supported": bool(ver and ver >= JS_MIN[name])}
                if first is None:
                    first = info
                if info["supported"]:
                    first = info
                    break
            if first:
                report[name] = first
        _rt_cache["val"], _rt_cache["t"] = report, time.time()
        return report



def has_js_runtime(force=False):
    return any(i["supported"] for i in js_runtime_report(force).values())



_deno_lock = threading.Lock()

_deno_state = {"tried": False, "error": ""}



def _deno_asset():
    m = platform.machine().lower()
    arm = m in ("arm64", "aarch64")
    if IS_WINDOWS and m in ("x86", "i386", "i686"):
        return None                       # ويندوز 32-bit الحقيقي: مفيش نسخة Deno ليه
    if IS_WINDOWS:
        return "deno-aarch64-pc-windows-msvc.zip" if arm else "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "deno-aarch64-apple-darwin.zip" if arm else "deno-x86_64-apple-darwin.zip"
    return "deno-aarch64-unknown-linux-gnu.zip" if arm else "deno-x86_64-unknown-linux-gnu.zip"



def _install_node():
    """
    ويندوز 32-bit مفيهوش Deno، فبننزّل Node.js 22 (LTS) الرسمي بدله: بيشتغل مع yt-dlp بنفس الطريقة.
    الملف بيتحقق منه بـ SHA-256 من nodejs.org قبل ما يتفك، وبيتحط في مجلد بيانات البرنامج بس (مش بيتثبّت على الجهاز).
    بيرجّع (ok, version-or-error) زي install_deno.
    """
    import hashlib
    from aerograb.netutil import _urlopen
    m = platform.machine().lower()
    plat = "win-arm64" if m in ("arm64", "aarch64") else ("win-x86" if m in ("x86", "i386", "i686") else "win-x64")
    base = "https://nodejs.org/dist/latest-v22.x/"
    hdr = {"User-Agent": "aerograb-node-installer"}
    with _urlopen(urllib.request.Request(base + "SHASUMS256.txt", headers=hdr), timeout=30) as r:
        sums = r.read().decode("utf-8", "replace")
    hit = re.search(rf"^([0-9a-f]{{64}})\s+(node-v22\.\d+\.\d+-{plat}\.zip)\s*$", sums, re.M)
    if not hit:
        raise RuntimeError(f"Node.js 22 has no {plat} build")
    digest, name = hit.group(1), hit.group(2)
    os.makedirs(BIN_DIR, exist_ok=True)
    tmp = os.path.join(BIN_DIR, "node.zip.part")
    h = hashlib.sha256()
    with _urlopen(urllib.request.Request(base + name, headers=hdr), timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != digest:
        os.remove(tmp)
        raise RuntimeError("Node.js download failed the checksum test")
    with zipfile.ZipFile(tmp) as z:
        member = next(n for n in z.namelist() if os.path.basename(n).lower() == "node.exe")
        data = z.read(member)
    exe = os.path.join(BIN_DIR, "node.exe")
    with open(exe + ".new", "wb") as f:
        f.write(data)
    os.replace(exe + ".new", exe)
    try:
        os.remove(tmp)
    except OSError:
        pass
    ver = _exe_version(exe)
    if not ver or ver < JS_MIN["node"]:
        raise RuntimeError(f"downloaded node is not usable (version {ver})")
    js_runtime_report(True)
    return True, ".".join(str(x) for x in ver)


def install_deno(force=False):
    """
    بينزّل deno (مشغّل JavaScript بحجم ~40MB) مرة واحدة لمجلد البرنامج. يوتيوب من غيره مبيدّيش yt-dlp الصيغ
    ("Requested format is not available"). بيرجّع (ok, رسالة).
    """
    with _deno_lock:
        try:
            if has_js_runtime(True):
                return True, "ready"
            # المحاولة التلقائية بتتكرر (بعد 45 ثانية على الأقل من الفاشلة) بدل ما تقف للأبد: النت ممكن يكون لسه مفتحش وقت فتح البرنامج
            if _deno_state["tried"] and not force and time.time() - _deno_state.get("t", 0) < 45:
                return False, _deno_state["error"] or "failed before"
            _deno_state["tried"] = True
            _deno_state["t"] = time.time()
            asset = _deno_asset()
            if not asset:                                    # ويندوز 32-bit: Node.js بدل Deno
                return _install_node()
            from aerograb.netutil import _urlopen
            os.makedirs(BIN_DIR, exist_ok=True)
            url = f"https://github.com/denoland/deno/releases/latest/download/{asset}"
            tmp = os.path.join(BIN_DIR, "deno.zip.part")
            req = urllib.request.Request(url, headers={"User-Agent": "aerograb-deno-installer"})
            with _urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 16)
            with zipfile.ZipFile(tmp) as z:
                name = next(n for n in z.namelist() if os.path.basename(n).lower() in ("deno", "deno.exe"))
                data = z.read(name)
            exe = os.path.join(BIN_DIR, "deno.exe" if IS_WINDOWS else "deno")
            with open(exe + ".new", "wb") as f:
                f.write(data)
            os.replace(exe + ".new", exe)
            if not IS_WINDOWS:
                os.chmod(exe, 0o755)
            try:
                os.remove(tmp)
            except OSError:
                pass
            ver = _exe_version(exe)
            if not ver or ver < JS_MIN["deno"]:
                raise RuntimeError(f"downloaded deno is not usable (version {ver})")
            js_runtime_report(True)
            return True, ".".join(str(x) for x in ver)
        except Exception as e:
            log_error("install_deno", e)
            if IS_WINDOWS:                                   # Deno فشل لأي سبب؟ نجرّب Node.js كبديل مضمون
                try:
                    return _install_node()
                except Exception as e2:
                    log_error("install_node", e2)
                    e = e2
            _deno_state["error"] = str(e)[:150]
            return False, _deno_state["error"]



def ensure_js_for(url, on_status=None):
    """قبل تحميل يوتيوب: لو مفيش مشغّل JavaScript بنثبّت deno تلقائياً (مرة واحدة)."""
    try:
        if not any(h in (url or "").lower() for h in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
            return
        if has_js_runtime():
            return
        if on_status:
            on_status("Installing the JavaScript engine (one time)...")
        install_deno()
    except Exception as e:
        log_error("ensure_js_for", e)



def ejs_loaded():
    """هل yt-dlp حمّل مكوّن الحل فعلاً؟"""
    try:
        ensure_ytdlp()
        dep = importlib.import_module("yt_dlp.dependencies")
        return bool(getattr(dep, "yt_dlp_ejs", None))
    except Exception:
        return False



def base_ydl_opts():
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "socket_timeout": net_timeout() or 20, "logger": YtLogger(),
    }
    custom_cookies = (get_setting("cookies_file", "") or "").strip()
    if custom_cookies and os.path.isfile(custom_cookies):
        opts["cookiefile"] = custom_cookies
    elif os.path.exists(COOKIES_PATH):
        opts["cookiefile"] = COOKIES_PATH
    ua = custom_user_agent()
    if ua:
        opts["http_headers"] = {"User-Agent": ua}
    if _proxy_url():
        opts["proxy"] = _proxy_url()
    try:
        rt = {n: {"path": i["path"]} for n, i in js_runtime_report().items() if i["supported"]}
        if rt:
            opts["js_runtimes"] = rt
        if not ejs_loaded():
            opts["remote_components"] = ["ejs:github"]     # احتياطي: yt-dlp ينزّل سكريبت الحل بنفسه
    except Exception as e:
        log_error("base_ydl_opts engine detection", e)
    return opts



# ----------------------------------------------------------------------------- H.264 encoder (قص دقيق)
_enc_cache = {}

_HW_ENCODERS = (
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "21"]),
    ("h264_amf", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "21", "-qp_p", "21"]),
    ("h264_videotoolbox", ["-c:v", "h264_videotoolbox", "-q:v", "60"]),
)

SOFT_ENCODER = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def h264_encoder_args(ffmpeg):
    """
    أسرع مُرمّز H.264 شغّال فعلاً على الجهاز. القص الدقيق بيعيد ترميز الجزء كله، وعلى المعالج ده بياخد وقت قد مدة الجزء أو أكتر؛
    كارت الشاشة (NVENC / Quick Sync / AMF) بيعمل نفس الشغل أسرع بكتير. كل مُرمّز بنجرّبه بتشفير تجريبي صغير الأول،
    ولو فشل بنكمّل بالمُرمّز العادي (libx264) فمفيش حاجة بتتكسر.
    """
    if ffmpeg in _enc_cache:
        return _enc_cache[ffmpeg]
    chosen = list(SOFT_ENCODER)
    if not get_setting("clip_hw_encode", True):
        _enc_cache[ffmpeg] = chosen
        return chosen
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace",
                             timeout=15, creationflags=_NOWIN).stdout or ""
        for name, args in _HW_ENCODERS:
            if name not in out:
                continue
            try:
                r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                    "testsrc2=size=1280x720:rate=25", "-t", "0.4", "-pix_fmt", "yuv420p", *args, "-f", "null", "-"],
                                   capture_output=True, text=True, errors="replace", timeout=20, creationflags=_NOWIN)
                if r.returncode == 0:
                    chosen = list(args)
                    break
            except Exception:
                continue
    except Exception as e:
        log_error("h264_encoder_args", e)
    _enc_cache[ffmpeg] = chosen
    return chosen
