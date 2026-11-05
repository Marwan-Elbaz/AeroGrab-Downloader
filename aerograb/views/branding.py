# -*- coding: utf-8 -*-
"""هوية AeroGrab: الشعار وأيقونة النوافذ (بتتحمّل من الملف logo.ico لو موجود، وإلا من الشعار المدمج)."""
import base64
import io
import os
import tkinter as tk
import customtkinter as ctk
from PIL import Image
from aerograb.common import log_error, resource_path
from aerograb.config import IS_WINDOWS
from aerograb.logo_data import LOGO_B64

APP_USER_MODEL_ID = "AeroGrab.DownloadManager"
_master = []
_ctk_cache = {}
_photos = []


def logo_pil(px):
    """الشعار بمقاس px (مربع شفاف الخلفية)."""
    if not _master:
        _master.append(Image.open(io.BytesIO(base64.b64decode(LOGO_B64))).convert("RGBA"))
    return _master[0].resize((px, px), Image.LANCZOS)


def logo_ctk(px):
    """CTkImage للشعار بحجم px (بيتحمّل بدقة مضاعفة للشاشات الحادة)."""
    im = _ctk_cache.get(px)
    if im is None:
        im = ctk.CTkImage(light_image=logo_pil(min(256, px * 2)), dark_image=logo_pil(min(256, px * 2)), size=(px, px))
        _ctk_cache[px] = im
    return im


def set_app_user_model_id():
    """بتخلّي شريط مهام ويندوز يعرض أيقونة AeroGrab (مش أيقونة بايثون) ويجمّع نوافذ البرنامج مع بعض."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as e:
        log_error("set_app_user_model_id", e)


def _photo_images():
    if not _photos:
        for px in (256, 64, 48, 32, 16):
            buf = io.BytesIO()
            logo_pil(px).save(buf, "PNG")
            _photos.append(tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii")))
    return _photos


def apply_window_icon(win):
    """بتحط أيقونة AeroGrab على نافذة. CTk بيرجّع أيقونته الافتراضية بعد ~200ms، فبنعيدها كذا مرة."""
    def go():
        try:
            if not win.winfo_exists():
                return
            ico = resource_path("logo.ico")
            if IS_WINDOWS and os.path.exists(ico):
                win.iconbitmap(ico)
            else:
                win.iconphoto(True, *_photo_images())
        except Exception:
            pass
    go()
    try:
        win.after(250, go)
        win.after(900, go)
    except Exception:
        pass
