# -*- coding: utf-8 -*-
"""نافذة "اربط المتصفح": خطوات بسيطة + أزرار تفتح صفحة الإضافات ومجلد الإضافة، وبتتأكد لوحدها لما الإضافة تتصل."""
import subprocess
import time
import tkinter as tk
import customtkinter as ctk
from aerograb.common import log_error
from aerograb.config import IS_WINDOWS, UI_FONT
from aerograb.state import ext_info
from aerograb.system import prepare_extension_folder
from aerograb.tools import _NOWIN
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon
from aerograb.views.icons import icon_ctk
from aerograb.views.winutil import open_path

GREEN, GREEN_H = "#2cc985", "#21a06a"
_win = [None]

# (اسم الزرار, أمر ويندوز لتشغيل المتصفح, رابط صفحة الإضافات)
BROWSERS = (("Chrome", "chrome", "chrome://extensions"), ("Edge", "msedge", "edge://extensions"), ("Brave", "brave", "brave://extensions"))


def _open_extensions_page(cmd, url, status):
    try:
        if not IS_WINDOWS:
            raise OSError("Windows only")
        subprocess.Popen(["cmd", "/c", "start", "", cmd, url], creationflags=_NOWIN)
        status.configure(text=f"Opened {url}. Now follow steps 2 and 3.", text_color=GREEN)
    except Exception as e:
        log_error("open extensions page", e)
        status.configure(text=f"Could not open the browser. Type {url} in its address bar.", text_color="#FF9800")


def show_extension_setup(parent=None):
    """بتفتح النافذة (أو بترجّعها لقدّام لو مفتوحة)."""
    if _win[0] is not None:
        try:
            if _win[0].winfo_exists():
                _win[0].deiconify()
                _win[0].lift()
                _win[0].focus_force()
                return
        except Exception:
            pass
    folder = prepare_extension_folder()
    card_bg = ("#eef1f5", "#1b1f26")
    muted = ("#5f6b7a", "#98a2ad")
    win = ctk.CTkToplevel(parent or gui.root)
    win.withdraw()
    _win[0] = win
    apply_window_icon(win)
    win.title("Connect your browser")
    win.resizable(False, False)

    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill=tk.X, padx=22, pady=(20, 6))
    ctk.CTkLabel(head, text="", image=icon_ctk("puzzle", 34)).pack(side=tk.LEFT)
    ht = ctk.CTkFrame(head, fg_color="transparent")
    ht.pack(side=tk.LEFT, padx=12)
    ctk.CTkLabel(ht, text="Connect your browser", font=(UI_FONT, 18, "bold"), anchor="w").pack(anchor="w")
    ctk.CTkLabel(ht, text="One-time setup, about 30 seconds. It lets AeroGrab take over downloads and videos from the browser.",
                 font=(UI_FONT, 11), text_color=muted, anchor="w", wraplength=470, justify="left").pack(anchor="w")

    status = ctk.CTkLabel(win, text="", font=(UI_FONT, 11), anchor="w", justify="left", wraplength=540)

    def step(n, title, body_builder):
        f = ctk.CTkFrame(win, corner_radius=14, fg_color=card_bg)
        f.pack(fill=tk.X, padx=22, pady=6)
        badge = ctk.CTkLabel(f, text=str(n), width=30, height=30, corner_radius=15, fg_color=GREEN, text_color="white",
                             font=(UI_FONT, 13, "bold"))
        badge.pack(side=tk.LEFT, anchor="n", padx=(14, 12), pady=14)
        col = ctk.CTkFrame(f, fg_color="transparent")
        col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 14), pady=12)
        ctk.CTkLabel(col, text=title, font=(UI_FONT, 13, "bold"), anchor="w", justify="left", wraplength=470).pack(fill=tk.X)
        body_builder(col)

    def s1(col):
        r = ctk.CTkFrame(col, fg_color="transparent")
        r.pack(anchor="w", pady=(8, 0))
        for name, cmd, url in BROWSERS:
            ctk.CTkButton(r, text=name, width=92, height=32, corner_radius=8, font=(UI_FONT, 12, "bold"), fg_color=GREEN, hover_color=GREEN_H,
                          command=lambda c=cmd, u=url: _open_extensions_page(c, u, status)).pack(side=tk.LEFT, padx=(0, 8))

    def s2(col):
        ctk.CTkLabel(col, text="Turn on “Developer mode” (the switch at the top right of that page).", font=(UI_FONT, 11),
                     text_color=muted, anchor="w", justify="left", wraplength=470).pack(fill=tk.X, pady=(2, 0))

    def s3(col):
        ctk.CTkLabel(col, text="Click “Load unpacked”, then paste this folder path into the dialog (or choose the folder):",
                     font=(UI_FONT, 11), text_color=muted, anchor="w", justify="left", wraplength=470).pack(fill=tk.X, pady=(2, 6))
        e = ctk.CTkEntry(col, height=32, font=(UI_FONT, 11))
        e.insert(0, folder)
        e.configure(state="readonly")
        e.pack(fill=tk.X)
        r = ctk.CTkFrame(col, fg_color="transparent")
        r.pack(anchor="w", pady=(8, 0))

        def copy():
            gui.root.clipboard_clear()
            gui.root.clipboard_append(folder)
            status.configure(text="Folder path copied. Paste it in the “Load unpacked” dialog.", text_color=GREEN)
        sec = dict(fg_color=("#dfe5ec", "#2a303a"), hover_color=("#cfd7e1", "#37404d"), text_color=("#1a1a1a", "#e8eaed"))
        ctk.CTkButton(r, text="  Copy folder path", image=icon_ctk("link", 16), compound="left", height=32, corner_radius=8,
                      font=(UI_FONT, 12, "bold"), command=copy, **sec).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(r, text="  Open folder", image=icon_ctk("folder", 16), compound="left", height=32, corner_radius=8,
                      font=(UI_FONT, 12, "bold"), command=lambda: open_path(folder), **sec).pack(side=tk.LEFT)

    step(1, "Open your browser's extensions page", s1)
    step(2, "Turn on Developer mode", s2)
    step(3, "Load the AeroGrab extension folder", s3)

    status.pack(fill=tk.X, padx=26, pady=(8, 0))
    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill=tk.X, padx=22, pady=(8, 18))
    live = ctk.CTkLabel(foot, text="", font=(UI_FONT, 12, "bold"), anchor="w")
    live.pack(side=tk.LEFT)
    ctk.CTkButton(foot, text="Close", width=96, height=34, corner_radius=8, font=(UI_FONT, 12, "bold"), fg_color=("#dfe5ec", "#2a303a"),
                  hover_color=("#cfd7e1", "#37404d"), text_color=("#1a1a1a", "#e8eaed"), command=win.destroy).pack(side=tk.RIGHT)

    t_open = time.time()

    def poll():
        if not win.winfo_exists():
            return
        t = ext_info.get("t", 0)
        if t and t >= t_open - 5:
            live.configure(text="✔  Connected! You can close this window.", text_color=GREEN)
        else:
            live.configure(text="●  Waiting for the extension…", text_color="#FF9800")
        win.after(1500, poll)
    poll()

    win.update_idletasks()
    try:
        s = max(1.0, float(win.winfo_fpixels("1i")) / 96.0)
    except Exception:
        s = 1.0
    w, h = int(round(600 * s)), win.winfo_reqheight()
    x = gui.root.winfo_rootx() + max(0, (gui.root.winfo_width() - w) // 2)
    y = max(0, gui.root.winfo_rooty() + (gui.root.winfo_height() - h) // 3)
    tk.Toplevel.geometry(win, f"{w}x{h}+{x}+{y}")
    win.deiconify()
    win.attributes("-topmost", True)
    win.after(500, lambda: win.winfo_exists() and win.attributes("-topmost", False))
    win.focus_force()


def maybe_show_first_run():
    """أول تشغيل: نعرض النافذة مرة واحدة بس (لو الإضافة مش متوصلة أصلاً)."""
    from aerograb.common import get_setting, save_settings
    try:
        if get_setting("ext_setup_shown", False) or ext_info.get("t", 0):
            return
        save_settings("ext_setup_shown", True)
        show_extension_setup()
    except Exception as e:
        log_error("first run extension setup", e)
