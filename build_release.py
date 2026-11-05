# -*- coding: utf-8 -*-
"""
يبني نسخة جاهزة للنشر:   python build_release.py
الناتج: release/AeroGrab-<version>-x64.zip (أو -x86 لو بايثون 32-bit)   (ده الملف اللي بترفعه في GitHub Release عشان التحديث التلقائي يوصل للمستخدمين)

الخطوات الكاملة للنشر:
  1) غيّر APP_VERSION في aerograb/config.py  (مثلاً "4.2")
  2) python build_release.py
  3) على GitHub: Releases ← Draft a new release ← Tag: v4.2 (لازم يطابق الرقم) ← ارفع release/AeroGrab-4.2-x64.zip ← Publish
  المستخدمين هيلاقوا التحديث لوحدهم (البرنامج بيفحص عند التشغيل وكل كام ساعة).
"""
import os
import shutil
import subprocess
import sys

# كونسول GitHub على ويندوز بيستخدم cp1252 ومبيعرفش يطبع عربي، فبنجبر UTF-8 (وبنتجاهل أي حرف مش مدعوم بدل ما البناء يفشل)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from aerograb.config import APP_VERSION  # noqa: E402


FFMPEG_URLS = {
    "x64": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "x86": "https://github.com/sudo-nautilus/FFmpeg-Builds-Win32/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip",
}


def bundle_ffmpeg(app_dir, arch):
    """بيحط ffmpeg.exe و ffprobe.exe جنب البرنامج (دمج الفيديو والصوت وتحويل H.264 محتاجينه). بيتجاهل لو مش ويندوز."""
    if os.name != "nt":
        return
    import io
    import urllib.request
    import zipfile
    local = [os.path.join(ROOT, n) for n in ("ffmpeg.exe", "ffprobe.exe")]
    if all(os.path.isfile(p) for p in local):                    # لو حاطط النسختين جنب build_release.py بنستخدمهم
        for p in local:
            shutil.copy2(p, app_dir)
        return
    urls = [FFMPEG_URLS[arch]] + ([FFMPEG_URLS["x64"]] if arch == "x86" else [])      # 32-bit مش لاقي؟ نسخة 64-bit تشتغل على ويندوز 64
    for i, url in enumerate(urls):
        try:
            print(f"> downloading ffmpeg: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "aerograb-build"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for want in ("ffmpeg.exe", "ffprobe.exe"):
                    member = next(n for n in z.namelist() if n.lower().endswith("/bin/" + want))
                    with open(os.path.join(app_dir, want), "wb") as f:
                        f.write(z.read(member))
            if i:
                print("WARNING: 32-bit ffmpeg was not available; bundled the 64-bit one (works on 64-bit Windows only)")
            return
        except Exception as e:
            print(f"ffmpeg download failed ({e})")
    raise SystemExit("could not get ffmpeg: put ffmpeg.exe and ffprobe.exe next to build_release.py and run again")


def main():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise SystemExit("yt-dlp is not installed: run  pip install -r requirements.txt  first")
    dist, work, out = (os.path.join(ROOT, d) for d in ("dist", "build", "release"))
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--noconsole", "--onedir", "--name", "AeroGrab",
           "--icon", os.path.join(ROOT, "logo.ico"), "--add-data", f"{os.path.join(ROOT, 'logo.ico')}{sep}.",
           "--collect-data", "customtkinter",
           "--hidden-import", "PIL._tkinter_finder",                       # Pillow بيحمّله ديناميكياً لعرض الصور في tkinter
           "--collect-all", "yt_dlp", "--collect-all", "yt_dlp_ejs",       # yt-dlp (كل الـ extractors) + حلّال تحديات يوتيوب
           os.path.join(ROOT, "main.py")]
    print(">", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    app_dir = os.path.join(dist, "AeroGrab")
    arch = "x64" if sys.maxsize > 2 ** 32 else "x86"           # بايثون 64-bit يطلع x64، و 32-bit يطلع x86
    bundle_ffmpeg(app_dir, arch)
    ext_src = os.path.join(ROOT, "extension")
    if os.path.isdir(ext_src):
        shutil.rmtree(os.path.join(app_dir, "extension"), ignore_errors=True)
        shutil.copytree(ext_src, os.path.join(app_dir, "extension"))
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, f"AeroGrab-{APP_VERSION}-{arch}")
    # الـ zip بيحتوي مجلد AeroGrab واحد (المحدّث بيعرف يتعامل معاه)
    archive = shutil.make_archive(base, "zip", root_dir=dist, base_dir="AeroGrab")
    print(f"\nتم: {archive}")
    # المثبّت (Inno Setup): لو متسطّب على الجهاز بنبنيه كمان. على GitHub الـ workflow بيسطّبه ويبنيه لوحده.
    iscc = next((p for p in (shutil.which("ISCC"),
                             os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
                             os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
                             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")) if p and os.path.exists(p)), None)
    if iscc:
        subprocess.check_call([iscc, f"/DAppVersion={APP_VERSION}", f"/DArch={arch}", "installer.iss"], cwd=ROOT)
        print(f"المثبّت: {os.path.join(out, f'AeroGrab-{APP_VERSION}-{arch}-Setup.exe')}")
    else:
        print("(Inno Setup مش متسطّب: اتبنى الـ zip بس. المثبّت بيتبني تلقائي على GitHub.)")
    print(f"ارفع الملفات في GitHub Release بالتاج v{APP_VERSION}")


if __name__ == "__main__":
    main()
