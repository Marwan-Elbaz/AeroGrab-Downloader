# -*- coding: utf-8 -*-
import os
import sys
from aerograb.config import winreg
from aerograb.common import get_setting, log_error, save_settings
from aerograb.config import APP_NAME, BASE_DIR, FROZEN, HOME, IS_WINDOWS, MAIN_SCRIPT


# ----------------------------------------------------------------------------- Startup / protocol (Windows)
def app_launch_argv():
    if FROZEN:
        return [sys.executable]
    py = sys.executable
    if IS_WINDOWS:
        pw = os.path.join(os.path.dirname(py), "pythonw.exe")
        if os.path.exists(pw):
            py = pw
    return [py, MAIN_SCRIPT]



def _startup_vbs_path():
    return os.path.join(os.environ.get("APPDATA", HOME), "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "AeroGrab.vbs")



def _legacy_startup_path():
    return os.path.join(os.path.dirname(_startup_vbs_path()), "IDM_Modern_Pro.vbs")


def set_startup(enabled):
    if not IS_WINDOWS:
        return True
    vp = _startup_vbs_path()
    try:
        if os.path.exists(_legacy_startup_path()):          # ملف التشغيل القديم (اسم البرنامج القديم)
            os.remove(_legacy_startup_path())
        if enabled:
            os.makedirs(os.path.dirname(vp), exist_ok=True)
            parts = " & chr(32) & ".join(f'chr(34) & "{a}" & chr(34)' for a in app_launch_argv())
            with open(vp, "w", encoding="utf-8") as f:
                f.write(f'CreateObject("WScript.Shell").Run {parts} & " --background", 0\n')
        elif os.path.exists(vp):
            os.remove(vp)
        return True
    except Exception as e:
        log_error("set_startup", e)
        return False



def setup_startup():
    if IS_WINDOWS and os.path.exists(_legacy_startup_path()):      # ترقية من النسخة القديمة: ننقل التشغيل التلقائي للاسم الجديد
        set_startup(True)
    if IS_WINDOWS and not get_setting("startup_default_v2"):
        # التشغيل مع ويندوز (في الخلفية) مفعّل تلقائياً: مرة واحدة بس، وبعدها اختيار المستخدم من الإعدادات بيتحترم
        if set_startup(True):
            save_settings("startup_default_v2", True)
            save_settings("startup_setup_done", True)
    elif IS_WINDOWS and os.path.exists(_startup_vbs_path()):
        set_startup(True)                   # نحدّث مسار البرنامج في ملف التشغيل (لو البرنامج اتنقل أو اتحدّث)



PROTOCOLS = ("aerograb", "idmpro")      # idmpro = الاسم القديم (إضافات المتصفح القديمة لسه تشتغل)


def register_protocol():
    """تسجيل aerograb:// (وidmpro:// القديم) عشان الإضافة تقدر تفتح البرنامج لو مقفول."""
    if not IS_WINDOWS:
        return
    cmd = " ".join(f'"{a}"' for a in app_launch_argv()) + ' "%1"'
    for scheme in PROTOCOLS:
        try:
            key_path = rf"Software\Classes\{scheme}"
            existing = None
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + r"\shell\open\command") as k:
                    existing = winreg.QueryValueEx(k, "")[0]
            except OSError:
                pass
            if existing == cmd:
                continue
            if existing is not None and not FROZEN and scheme == "aerograb":
                continue      # مش هنكتب فوق تسجيل النسخة المثبّتة وإحنا بنشتغل من السورس
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"URL:{APP_NAME} Protocol")
                winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path + r"\shell\open\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        except Exception as e:
            log_error(f"register_protocol({scheme})", e)


def _documents_dir():
    """مجلد Documents الحقيقي (حتى لو منقول لـ OneDrive)."""
    if IS_WINDOWS:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:     # CSIDL_PERSONAL
                return buf.value
        except Exception:
            pass
    return os.path.join(HOME, "Documents")


def bundled_extension_version():
    """رقم نسخة الإضافة اللي مع البرنامج (من manifest.json)."""
    import json
    try:
        with open(os.path.join(BASE_DIR, "extension", "manifest.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except Exception:
        return ""


def prepare_extension_folder(create=True):
    """
    بيجهّز مجلد إضافة المتصفح في مكان ظاهر وسهل (Documents\\AeroGrab Browser Extension) بدل مجلد البرنامج المخفي (AppData).
    بيتحدّث تلقائياً لو الإضافة اتغيّرت. لو النسخ فشل بنرجّع المجلد الأصلي. بيرجّع المسار.
    """
    import filecmp
    import shutil
    src = os.path.join(BASE_DIR, "extension")
    if not os.path.isdir(src):
        return src
    dst = os.path.join(_documents_dir(), "AeroGrab Browser Extension")
    if not create and not os.path.isdir(dst):
        return src                         # اليوزر لسه مربطش من النسخة دي: منعملش مجلد في Documents من نفسنا
    try:
        def same(a, b):
            fa = sorted(os.path.relpath(os.path.join(r, f), a) for r, _d, fs in os.walk(a) for f in fs)
            fb = sorted(os.path.relpath(os.path.join(r, f), b) for r, _d, fs in os.walk(b) for f in fs)
            return fa == fb and all(filecmp.cmp(os.path.join(a, f), os.path.join(b, f), shallow=False) for f in fa)
        if not (os.path.isdir(dst) and same(src, dst)):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        return dst
    except Exception as e:
        log_error("prepare_extension_folder", e)
        return src
