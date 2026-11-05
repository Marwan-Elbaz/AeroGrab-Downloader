# -*- coding: utf-8 -*-
import os
import sys
from aerograb.config import winreg
from aerograb.common import get_setting, log_error, save_settings
from aerograb.config import APP_NAME, FROZEN, HOME, IS_WINDOWS, MAIN_SCRIPT


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
    if IS_WINDOWS and not get_setting("startup_setup_done"):
        if set_startup(True):
            save_settings("startup_setup_done", True)



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
