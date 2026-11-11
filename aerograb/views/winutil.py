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


def fit_geometry(win, w, h, min_w=None, min_h=None, center=True):
    """
    بيظبط حجم النافذة (بوحدات ctk: قبل تكبير الشاشة) عشان متعدّيش الشاشة اللي شغّالة عليها، وبيوسّطها.
    مثال: شاشة لابتوب صغيرة أو تكبير 150% => النافذة بتصغر لحد ما تتسع في الشاشة بدل ما تتقص.
    """
    try:
        try:
            scale = float(win._get_window_scaling())
        except Exception:
            scale = 1.0
        sw, sh = win.winfo_screenwidth() / scale, win.winfo_screenheight() / scale
        w = int(max(300, min(w, sw - 40)))
        h = int(max(240, min(h, sh - 100)))                    # 100 = شريط المهام + شريط العنوان
        if min_w is not None and min_h is not None:
            win.minsize(int(min(min_w, w)), int(min(min_h, h)))
        if center:
            x = int(max(0, (win.winfo_screenwidth() - w * scale) // 2))
            y = int(max(0, (win.winfo_screenheight() - h * scale) // 2 - 30))
            win.geometry(f"{w}x{h}+{x}+{y}")
        else:
            win.geometry(f"{w}x{h}")
    except Exception as e:
        log_error("fit_geometry", e)
