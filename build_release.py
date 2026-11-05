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

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from aerograb.config import APP_VERSION  # noqa: E402


def main():
    dist, work, out = (os.path.join(ROOT, d) for d in ("dist", "build", "release"))
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--noconsole", "--onedir", "--name", "AeroGrab",
           "--icon", os.path.join(ROOT, "logo.ico"), "--add-data", f"{os.path.join(ROOT, 'logo.ico')}{sep}.",
           "--collect-data", "customtkinter", os.path.join(ROOT, "main.py")]
    print(">", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    app_dir = os.path.join(dist, "AeroGrab")
    ext_src = os.path.join(ROOT, "extension")
    if os.path.isdir(ext_src):
        shutil.rmtree(os.path.join(app_dir, "extension"), ignore_errors=True)
        shutil.copytree(ext_src, os.path.join(app_dir, "extension"))
    os.makedirs(out, exist_ok=True)
    arch = "x64" if sys.maxsize > 2 ** 32 else "x86"           # بايثون 64-bit يطلع x64، و 32-bit يطلع x86
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
