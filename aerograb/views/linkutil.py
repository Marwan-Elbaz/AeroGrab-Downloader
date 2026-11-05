# -*- coding: utf-8 -*-
"""أزرار الروابط (GitHub / YouTube / تواصل) وزر المشاركة. الروابط نفسها في aerograb/links.py."""
import webbrowser
from tkinter import messagebox
from aerograb import links
from aerograb.uistate import gui
from aerograb.views.tooltip import tips

# (اسم الأيقونة, اسم الخاصية في links.py, التلميح)
LINK_BUTTONS = (
    ("github", "GITHUB_URL", "Open the project page on GitHub"),
    ("youtube", "YOUTUBE_URL", "Open the YouTube channel"),
    ("comment", "FEEDBACK_URL", "Leave feedback or contact the developer"),
)


def link_value(attr):
    return (getattr(links, attr, "") or "").strip()


def open_link(attr, parent=None):
    url = link_value(attr)
    if not url:
        messagebox.showinfo("AeroGrab", "This link has not been set yet.\nOpen aerograb/links.py and paste your link there.",
                            parent=parent or gui.root)
        return
    webbrowser.open(url)


def share_url():
    return link_value("SHARE_URL") or link_value("GITHUB_URL")


def copy_share_link(widget=None):
    """زر المشاركة: بينسخ الرابط (SHARE_URL) مباشرة للحافظة."""
    url = share_url()
    if not url:
        messagebox.showinfo("AeroGrab", "This link has not been set yet.\nOpen aerograb/links.py and paste your link there.",
                            parent=gui.root)
        return
    try:
        from aerograb.views.mainwin import _clip
        _clip["last"] = url              # مراقب الحافظة ميعتبرهوش لينك تنزيل
        gui.root.clipboard_clear()
        gui.root.clipboard_append(url)
        gui.root.update_idletasks()
    except Exception:
        return
    try:
        x = (widget.winfo_rootx() + widget.winfo_width() // 2) if widget is not None else gui.root.winfo_pointerx()
        y = (widget.winfo_rooty() + widget.winfo_height()) if widget is not None else gui.root.winfo_pointery()
        tips.flash("Link copied ✔", x, y)
    except Exception:
        pass
