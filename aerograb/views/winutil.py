# -*- coding: utf-8 -*-
import os
import sys
import subprocess
from tkinter import messagebox
from aerograb.common import log_error
from aerograb.config import IS_WINDOWS
from aerograb.uistate import gui


# ----------------------------------------------------------------------------- GUI helpers (main thread)
def open_path(path):
    try:
        if IS_WINDOWS:
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        log_error("open_path", e)
        messagebox.showerror("Error", f"Could not open:\n{e}")



def reveal_in_folder(path, fallback_dir=None):
    try:
        if path and os.path.exists(path) and IS_WINDOWS:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif path and os.path.exists(path):
            open_path(os.path.dirname(path))
        elif fallback_dir and os.path.isdir(fallback_dir):
            open_path(fallback_dir)
        else:
            messagebox.showinfo("Not found", "The file or folder no longer exists.")
    except Exception as e:
        log_error("reveal_in_folder", e)



def wake_up_window():
    try:
        gui.root.deiconify()
        gui.root.lift()
        gui.root.attributes("-topmost", True)
        gui.root.after(400, lambda: gui.root.attributes("-topmost", False))
        gui.root.focus_force()
    except Exception:
        pass



def apply_glass_effect(window, dark=True):
    """تغبيش الخلفية (Acrylic) لنافذة بدون إطار. ويندوز فقط، وأي فشل بيتجاهل (النافذة بتفضل شغالة عادي)."""
    if not IS_WINDOWS:
        return
    try:
        from ctypes import windll, byref, sizeof, c_int, c_void_p, Structure, POINTER, c_uint, c_size_t, cast, pointer

        class ACCENTPOLICY(Structure):
            _fields_ = [("AccentState", c_uint), ("AccentFlags", c_uint), ("GradientColor", c_uint), ("AnimationId", c_uint)]

        class WINDOWCOMPOSITIONATTRIBDATA(Structure):
            _fields_ = [("Attribute", c_int), ("Data", POINTER(c_int)), ("SizeOfData", c_size_t)]

        hwnd = int(window.wm_frame(), 16)
        # الزوايا المدوّرة على ويندوز 11 (على 10 بتتجاهل)
        try:
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(c_int(2)), sizeof(c_int))
        except Exception:
            pass
        tint = 0xB81B1D22 if dark else 0xB8F7F5F4          # AABBGGRR: تدرّج خفيف بلون الثيم
        for state in (4, 3):                               # 4 = Acrylic (ويندوز 10 1803+) ، 3 = Blur عادي
            accent = ACCENTPOLICY()
            accent.AccentState = state
            accent.AccentFlags = 2
            accent.GradientColor = tint
            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = 19
            data.SizeOfData = sizeof(accent)
            data.Data = cast(pointer(accent), POINTER(c_int))
            if windll.user32.SetWindowCompositionAttribute(hwnd, byref(data)):
                break
    except Exception:
        pass



# ----------------------------------------------------------------------------- Thumbnails
THUMB_W, THUMB_H = 160, 90
