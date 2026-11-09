# -*- coding: utf-8 -*-
"""أيقونات حالة التحميل في أول عمود في جدول السجل (صح / غلط / إيقاف / تحذير ...) بدل رموز ويندوز الافتراضية."""
import customtkinter as ctk
from PIL import ImageTk
from aerograb.views.icons import icon_pil

STATUS_ICON = {"queued": "hourglass", "starting": "plug", "downloading": "download", "merging": "bolt", "paused": "pause_solid",
               "completed": "tick", "canceled": "cross", "error": "warn", "deleted": "trash"}

_cache = {}


def tree_image(status):
    """PhotoImage مناسب للثيم الحالي ('' لو مفيش أيقونة). بتتحفظ في كاش عشان Tk ميمسحهاش."""
    name = STATUS_ICON.get(status)
    if not name:
        return ""
    dark = ctk.get_appearance_mode() == "Dark"
    key = (name, dark)
    img = _cache.get(key)
    if img is None:
        try:
            from aerograb.uistate import gui
            scale = max(1.0, float(gui.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            scale = 1.0
        img = ImageTk.PhotoImage(icon_pil(name, int(round(18 * scale)), dark=dark))
        _cache[key] = img
    return img


def refresh_all():
    """بعد تغيير الثيم: نعيد تعيين أيقونة كل صف."""
    from aerograb.state import tasks
    from aerograb.uistate import gui
    if gui.tree is None:
        return
    for iid, t in list(tasks.items()):
        if gui.tree.exists(iid):
            gui.tree.item(iid, image=tree_image(t["status"]))
