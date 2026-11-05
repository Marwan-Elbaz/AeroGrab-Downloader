# -*- coding: utf-8 -*-
"""نافذة الإعدادات: شريط جانبي بأقسام (زي إعدادات IDM) وكل قسم بيتبني أول ما تفتحه."""
import os
import sys
import threading
import re
import time
import urllib.parse
import customtkinter as ctk
from tkinter import filedialog
from tkinter import messagebox
import tkinter as tk
from aerograb import clipwork, partsdir
from aerograb.capture import BYPASS_KEYS, DEFAULT_EXTENSIONS, MENU_ITEMS, parse_extensions
from aerograb import i18n, updater
from aerograb.common import get_setting, save_settings
from aerograb.config import APP_DATA_DIR, APP_NAME, APP_VERSION, EXTENSION_VERSION, IS_WINDOWS, LOG_FILE
from aerograb.files import get_connections
from aerograb import usage
from aerograb.fmt import QUALITY_MAP, fmt_bytes
from aerograb.limits import (
    CATEGORY_NAMES,
    MAX_CONCURRENT_DOWNLOADS,
    _parse_hhmm,
    fmt_limit,
    limiter,
    schedule_allows,
    set_default_quality_safe,
    speed_limit_kbps,
)
from aerograb.state import ext_info, tasks, ui
from aerograb.system import _startup_vbs_path, set_startup
import webbrowser
from aerograb.links import COOKIES_HELP_URL, COPYRIGHT_OWNER
from aerograb.tools import find_ffmpeg, h264_enabled, reset_ffmpeg_cache
from aerograb.ytdlp_mgr import check_and_update_ytdlp_async, ensure_ytdlp
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon
from aerograb.views.branding import logo_ctk
from aerograb.views.tooltip import attach as attach_tip

GREEN, GREEN_H = "#2cc985", "#21a06a"
SECTIONS = [("General", "gears", "Appearance, startup, notifications and sounds"),
            ("Downloads", "bolt", "Speed limit, connections, retries and timeouts"),
            ("Video", "video", "Default quality and compatibility mode"),
            ("Save to", "floppy", "Where downloads are saved"),
            ("File types", "file", "Which files the browser extension sends to this program"),
            ("Browser", "puzzle", "Browser extension: capture, keys and right-click menu"),
            ("Network", "globe", "Proxy, user-agent and site logins"),
            ("Schedule", "alarm", "Download only at certain hours"),
            ("Data usage", "gauge", "Daily or monthly data limit and usage counter"),
            ("Tools", "toolbox", "ffmpeg, cookies file, logs and data"),
            ("Updates", "update", "Engine and extension versions"),
            ("About", "logo", "About AeroGrab, privacy and credits")]
CLOSE_ACTIONS = {"Keep running in the background": "background", "Exit the program": "exit", "Ask me": "ask"}
TIMEOUTS = {"Automatic": 0, "15 seconds": 15, "30 seconds": 30, "60 seconds": 60, "2 minutes": 120}
PROXY_TYPES = {"None": "", "HTTP": "http", "HTTPS": "https", "SOCKS5": "socks5", "SOCKS4": "socks4"}


_settings_show = [None]


def open_settings_window(section=None):
    if _settings_win[0] is not None:
        try:
            if _settings_win[0].winfo_exists():
                _settings_win[0].lift()
                _settings_win[0].focus_force()
                if section and _settings_show[0]:
                    _settings_show[0](section)
                return
        except Exception:
            pass
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    _settings_win[0] = win
    win.title("Settings")
    win.geometry("860x620")
    win.minsize(760, 520)
    win.attributes("-topmost", True)
    win.after(600, lambda: win.attributes("-topmost", False))

    # ------------------------------------------------------------------ الهيكل: شريط جانبي + محتوى
    side = ctk.CTkFrame(win, width=206, corner_radius=0)
    side.pack(side=tk.LEFT, fill=tk.Y)
    side.pack_propagate(False)
    brand = ctk.CTkFrame(side, fg_color="transparent")
    brand.pack(fill=tk.X, padx=14, pady=(16, 10))
    ctk.CTkLabel(brand, text="", image=logo_ctk(36)).pack(side=tk.LEFT)
    btxt = ctk.CTkFrame(brand, fg_color="transparent")
    btxt.pack(side=tk.LEFT, padx=10)
    ctk.CTkLabel(btxt, text=APP_NAME, font=("Segoe UI", 16, "bold"), anchor="w").pack(anchor="w")
    ctk.CTkLabel(btxt, text="Settings", font=("Segoe UI", 11), text_color="gray", anchor="w").pack(anchor="w")
    host = ctk.CTkFrame(win, fg_color="transparent")
    host.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    header = ctk.CTkLabel(host, text="", font=("Segoe UI", 12), text_color="gray", anchor="w")
    header.pack(fill=tk.X, padx=18, pady=(14, 0))

    pages, nav_btns, builders = {}, {}, {}
    current = {"name": None}

    def show(name):
        if current["name"] == name:
            return
        if current["name"] in pages:
            pages[current["name"]].pack_forget()
        if name not in pages:
            sf = ctk.CTkScrollableFrame(host, fg_color="transparent")
            pages[name] = sf
            builders[name](sf)
        pages[name].pack(fill=tk.BOTH, expand=True, padx=(8, 12), pady=(4, 10))
        current["name"] = name
        header.configure(text=dict((n, d) for n, _i, d in SECTIONS)[name])
        for n, b in nav_btns.items():
            sel = n == name
            b.configure(fg_color=GREEN if sel else "transparent", text_color=("#0b2a1e", "#06150e") if sel else ("#1a1a1a", "#e8eaed"))

    for name, icon, _desc in SECTIONS:
        b = ctk.CTkButton(side, text="  " + name, image=logo_ctk(20) if icon == "logo" else icon_ctk(icon, 20), compound="left", anchor="w", height=38, corner_radius=8,
                          fg_color="transparent", text_color=("#1a1a1a", "#e8eaed"), hover_color=("#d6e0f0", "#2f3846"),
                          font=("Segoe UI", 13, "bold"), command=lambda n=name: show(n))
        b.pack(fill=tk.X, padx=10, pady=2)
        nav_btns[name] = b

    power_img = load_icon("icon_power.png", size=(20, 20))
    ctk.CTkButton(side, text="" if power_img else "Close App Completely", image=power_img, font=("Segoe UI", 12, "bold"),
                  fg_color="#e53935", hover_color="#c62828", command=force_quit_app, height=34).pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=14)
    attach_tip(side.winfo_children()[-1], "Exit the program completely (stops downloads and the browser connection)")
    links_row = ctk.CTkFrame(side, fg_color="transparent")
    links_row.pack(side=tk.BOTTOM, pady=(0, 2))
    for ico, attr, tip in LINK_BUTTONS:
        lb = ctk.CTkButton(links_row, text="", image=icon_ctk(ico, 20), width=38, height=34, fg_color="transparent",
                           hover_color=("#d6e0f0", "#2f3846"), corner_radius=8, command=lambda a=attr: open_link(a, win))
        lb.pack(side=tk.LEFT, padx=2)
        attach_tip(lb, tip)
    sh = ctk.CTkButton(links_row, text="", image=icon_ctk("share", 20), width=38, height=34, fg_color="transparent",
                       hover_color=("#d6e0f0", "#2f3846"), corner_radius=8, command=lambda: copy_share_link(sh))
    sh.pack(side=tk.LEFT, padx=2)
    attach_tip(sh, "Copy the program link to share it with others")

    # ------------------------------------------------------------------ أدوات بناء مشتركة
    def card(page, title, icon=None):
        f = ctk.CTkFrame(page, corner_radius=10)
        f.pack(fill=tk.X, pady=(0, 10), padx=2)
        ctk.CTkLabel(f, text="  " + title, image=icon_ctk(icon, 18) if icon else None, compound="left",
                     font=("Segoe UI", 14, "bold"), text_color=GREEN, anchor="w").pack(fill=tk.X, padx=14, pady=(10, 6))
        return f

    def note(parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 10), text_color="gray", wraplength=600, justify="left",
                     anchor="w").pack(fill=tk.X, padx=16, pady=(0, 10))

    def label(parent, text, bold=False):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 12, "bold" if bold else "normal"), anchor="w").pack(fill=tk.X, padx=16, pady=(6, 2))

    def switch(parent, text, key, default=True, cmd=None, tip=None):
        v = ctk.BooleanVar(value=bool(get_setting(key, default)))

        def on():
            save_settings(key, bool(v.get()))
            if cmd:
                cmd(bool(v.get()))
        w = ctk.CTkSwitch(parent, text=text, variable=v, command=on, font=("Segoe UI", 12))
        w.pack(anchor="w", padx=16, pady=4)
        if tip:
            attach_tip(w, tip)
        return v

    def option(parent, labeltext, mapping, key, default, tip=None, cmd=None):
        """قايمة منسدلة بتحفظ القيمة المقابلة للاسم المعروض."""
        rev = {v: k for k, v in mapping.items()}
        label(parent, labeltext)
        cur = rev.get(get_setting(key, default), next(iter(mapping)))

        def on(choice):
            save_settings(key, mapping[choice])
            if cmd:
                cmd(mapping[choice])
        m = ctk.CTkOptionMenu(parent, variable=ctk.StringVar(value=cur), values=list(mapping.keys()), command=on, font=("Segoe UI", 12))
        m.pack(anchor="w", padx=16, pady=(0, 8))
        if tip:
            attach_tip(m, tip)
        return m

    def file_row(parent, key, placeholder, filetypes, on_change=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill=tk.X, padx=14, pady=(0, 8))
        e = ctk.CTkEntry(row, placeholder_text=placeholder, height=32)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cur = get_setting(key, "") or ""
        if cur:
            e.insert(0, cur)

        def save_val(v):
            save_settings(key, v)
            if on_change:
                on_change()

        def browse():
            p = filedialog.askopenfilename(parent=win, filetypes=filetypes)
            if p:
                e.delete(0, tk.END)
                e.insert(0, p)
                save_val(p)

        def clear():
            e.delete(0, tk.END)
            save_val("")
        ctk.CTkButton(row, text="Browse", width=72, height=32, command=browse).pack(side=tk.LEFT, padx=(8, 4))
        ctk.CTkButton(row, text="Clear", width=60, height=32, fg_color="gray40", command=clear).pack(side=tk.LEFT)
        e.bind("<FocusOut>", lambda ev: save_val(e.get().strip()))
        return e

    # ================================================================== General
    def build_general(p):
        c = card(p, "Appearance", "gears")
        ctk.CTkOptionMenu(c, variable=ctk.StringVar(value=get_setting("theme", "Dark")), values=["Dark", "Light"],
                          command=update_main_theme, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 12))

        c = card(p, "Language", "language")
        label(c, "Interface language")
        lang_names = list(i18n.LANGUAGES.values())
        code_of = {v: k for k, v in i18n.LANGUAGES.items()}
        from aerograb.views.window import change_language
        ctk.CTkOptionMenu(c, variable=ctk.StringVar(value=i18n.LANGUAGES[i18n.lang()]), values=lang_names,
                          command=lambda name: change_language(code_of[name]), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 12))

        c = card(p, "Startup and window", "gears")
        sv = ctk.BooleanVar(value=os.path.exists(_startup_vbs_path()) if IS_WINDOWS else False)

        def toggle_startup():
            if not set_startup(sv.get()):
                messagebox.showerror("Error", "Could not change the startup setting.", parent=win)
                sv.set(not sv.get())
        w = ctk.CTkSwitch(c, text="Start in the background with Windows", variable=sv, command=toggle_startup, font=("Segoe UI", 12))
        w.pack(anchor="w", padx=16, pady=4)
        attach_tip(w, "The program starts hidden and waits for downloads from the browser")
        switch(c, "Resume downloads that were running when the program was closed", "auto_resume_start", False,
               tip="Paused downloads (App closed previously) restart by themselves when the program opens")
        option(c, "When I click the window's close button (✕):", CLOSE_ACTIONS, "close_action", "background",
               tip="Keeping it in the background lets the browser extension keep sending downloads")

        c = card(p, "Clipboard", "link")
        v = switch(c, "Watch the clipboard (offer to download copied links)", "clip_monitor", False)

        def on_clip():
            try:
                _clip["last"] = gui.root.clipboard_get().strip()
            except Exception:
                _clip["last"] = None
        v.trace_add("write", lambda *a: on_clip())

        c = card(p, "Notifications and sounds", "bell")
        switch(c, "Show a notification when a download finishes", "notify_toast", True)
        switch(c, "Play a sound when a download finishes", "notify_sound", True)
        label(c, "Custom sound (.wav) — leave empty for the system sound:")
        file_row(c, "sound_file", "C:\\path\\to\\sound.wav", [("WAV sound", "*.wav"), ("All files", "*.*")])
        ctk.CTkButton(c, text="Test sound", width=100, height=30, fg_color="gray40", command=play_done_sound).pack(anchor="w", padx=16, pady=(0, 8))
        option(c, "When a download finishes:", {"Do nothing": "none", "Open the file": "file", "Open the folder": "folder"},
               "open_when_done", "none")

        c = card(p, "Confirmations", "info")
        switch(c, "Ask before removing items from the list", "confirm_remove", True)
        switch(c, "Ask before deleting files from the device", "confirm_delete_file", True,
               tip="Turning this off makes “Delete File From Device” permanent without a question")
        ctk.CTkFrame(c, height=6, fg_color="transparent").pack()

    # ================================================================== Downloads
    def build_downloads(p):
        c = card(p, "Speed limit", "bolt")
        cur_lbl = ctk.CTkLabel(c, text=f"Current limit: {fmt_limit(speed_limit_kbps())}", font=("Segoe UI", 12), anchor="w")
        cur_lbl.pack(fill=tk.X, padx=16, pady=(0, 4))

        def apply_limit(kbps):
            set_speed_limit(kbps)
            cur_lbl.configure(text=f"Current limit: {fmt_limit(speed_limit_kbps())}")
        ctk.CTkOptionMenu(c, variable=ctk.StringVar(value=fmt_limit(speed_limit_kbps()) if fmt_limit(speed_limit_kbps()) in SPEED_CHOICES else "Custom"),
                          values=list(SPEED_CHOICES.keys()) + ["Custom"],
                          command=lambda v: apply_limit(SPEED_CHOICES[v]) if v in SPEED_CHOICES else None,
                          font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=(0, 6))
        crow = ctk.CTkFrame(c, fg_color="transparent")
        crow.pack(anchor="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(crow, text="Custom (KB/s):", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 6))
        custom_e = ctk.CTkEntry(crow, width=90, placeholder_text="e.g. 1500")
        custom_e.pack(side=tk.LEFT)

        def set_custom():
            txt = custom_e.get().strip()
            if not txt.isdigit():
                messagebox.showwarning("Speed limit", "Enter a whole number of KB/s (0 = unlimited).", parent=win)
                return
            apply_limit(int(txt))
        ctk.CTkButton(crow, text="Set", width=60, command=set_custom).pack(side=tk.LEFT, padx=6)

        c = card(p, "Connections", "bolt")
        label(c, "Max concurrent downloads:", True)

        def on_concurrent(v):
            n = int(v)
            save_settings("max_concurrent", n)
            limiter.set_limit(n)
        ctk.CTkOptionMenu(c, variable=ctk.StringVar(value=str(get_setting("max_concurrent", MAX_CONCURRENT_DOWNLOADS))),
                          values=["1", "2", "3", "4", "5", "6"], command=on_concurrent, font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=(0, 8))
        label(c, "Connections per download (the file is split into parts):", True)
        m = ctk.CTkOptionMenu(c, variable=ctk.StringVar(value=str(get_connections())), values=["1", "2", "4", "8", "16"],
                              command=lambda v: save_settings("connections", int(v)), font=("Segoe UI", 12))
        m.pack(anchor="w", padx=16, pady=(0, 12))
        attach_tip(m, "More connections can be faster, but some servers limit them")

        c = card(p, "Reliability", "update")
        option(c, "Automatic retries after a temporary error (403, 429, dropped connection):",
               {str(n): n for n in (0, 1, 2, 3, 5, 8)}, "auto_retries", 2, tip="Each retry uses fewer connections and a fresh link")
        option(c, "Connection timeout:", TIMEOUTS, "net_timeout", 0, tip="How long to wait for a server before giving up")
        ctk.CTkFrame(c, height=4, fg_color="transparent").pack()

    # ================================================================== Video
    def build_video(p):
        c = card(p, "Default video quality", "video")

        def on_quality(v):
            save_settings("default_quality", v)
            set_default_quality_safe(v)
        ctk.CTkOptionMenu(c, variable=gui.quality_var, values=list(QUALITY_MAP.keys()), command=on_quality,
                          font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=(0, 12))
        c = card(p, "Compatibility", "video")
        switch(c, "Compatibility mode (H.264 video + AAC audio)", "h264_only", True,
               tip="Plays on old PCs, TVs and phones. Needs ffmpeg")
        note(c, "Videos in other formats are converted after the download. Turn it off for the original quality and faster finishing.")

    # ================================================================== Save to
    def build_saveto(p):
        c = card(p, "Save folder", "floppy")
        srow = ctk.CTkFrame(c, fg_color="transparent")
        srow.pack(fill=tk.X, padx=14, pady=(0, 12))
        ctk.CTkEntry(srow, textvariable=gui.download_path_var, state="disabled", height=32).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ctk.CTkButton(srow, text="Change", width=70, height=32, command=choose_directory).pack(side=tk.LEFT, padx=(8, 4))
        ctk.CTkButton(srow, text="Open", width=60, height=32, command=open_save_folder).pack(side=tk.LEFT)

        c = card(p, "Sort downloads by type", "floppy")
        cat_var = ctk.BooleanVar(value=bool(get_setting("use_categories", False)))
        ctk.CTkSwitch(c, text="Save each type in its own folder", variable=cat_var,
                      command=lambda: save_settings("use_categories", bool(cat_var.get())), font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 6))
        note(c, "Leave a box empty to use  <save folder>/<type name>.  Applies to new downloads.")
        dirs = dict(get_setting("cat_dirs", {}) or {})
        cat_entries = {}
        for kind in CAT_ORDER:
            r = ctk.CTkFrame(c, fg_color="transparent")
            r.pack(fill=tk.X, padx=12, pady=3)
            ctk.CTkLabel(r, text=CATEGORY_NAMES[kind], width=90, anchor="w", font=("Segoe UI", 12)).pack(side=tk.LEFT)
            e = ctk.CTkEntry(r, placeholder_text=f"<save folder>/{CATEGORY_NAMES[kind]}")
            e.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
            if dirs.get(kind):
                e.insert(0, dirs[kind])
            cat_entries[kind] = e

            def browse(entry=e):
                d = filedialog.askdirectory(parent=win)
                if d:
                    entry.delete(0, tk.END)
                    entry.insert(0, d)
            ctk.CTkButton(r, text="…", width=34, fg_color="#FF9800", hover_color="#F57C00", command=browse).pack(side=tk.LEFT)

        def save_cats():
            save_settings("cat_dirs", {k: e.get().strip() for k, e in cat_entries.items() if e.get().strip()})
            save_settings("use_categories", bool(cat_var.get()))
            messagebox.showinfo("Save to", "Saved.", parent=win)
        ctk.CTkButton(c, text="Save folders", fg_color=GREEN, hover_color=GREEN_H, command=save_cats).pack(anchor="w", padx=16, pady=(8, 14))

    # ================================================================== File types
    def build_filetypes(p):
        c = card(p, "Files sent to this program", "file")
        note(c, "When you click a download in the browser, the extension takes it over only if its type is in this list "
                "(separate with commas or spaces). Everything else is downloaded by the browser as usual.")
        box = ctk.CTkTextbox(c, height=120, font=("Consolas", 12), wrap="word")
        box.pack(fill=tk.X, padx=16, pady=(0, 6))
        cur = get_setting("capture_exts", None)
        box.insert("1.0", ", ".join(cur if isinstance(cur, list) and cur else DEFAULT_EXTENSIONS))
        cnt = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), text_color="gray", anchor="w")
        cnt.pack(fill=tk.X, padx=16)

        def save_exts():
            exts = parse_extensions(box.get("1.0", "end"))
            if not exts:
                messagebox.showwarning("File types", "Add at least one file type (example: zip, mp4, pdf).", parent=win)
                return
            save_settings("capture_exts", exts)
            cnt.configure(text=f"Saved: {len(exts)} file types. The browser extension picks it up within a minute.", text_color=GREEN)

        def reset_exts():
            box.delete("1.0", "end")
            box.insert("1.0", ", ".join(DEFAULT_EXTENSIONS))
            save_settings("capture_exts", list(DEFAULT_EXTENSIONS))
            cnt.configure(text="Restored the default list.", text_color=GREEN)
        brow = ctk.CTkFrame(c, fg_color="transparent")
        brow.pack(anchor="w", padx=16, pady=(6, 12))
        ctk.CTkButton(brow, text="Save", width=90, fg_color=GREEN, hover_color=GREEN_H, command=save_exts).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkButton(brow, text="Restore defaults", width=130, fg_color="gray40", command=reset_exts).pack(side=tk.LEFT)

        c = card(p, "Size limits and detection", "file")
        option(c, "Ignore documents (PDF, Office) smaller than:", {"Never ignore": 0, "512 KB": 0.5, "1 MB": 1, "5 MB": 5, "10 MB": 10},
               "min_doc_mb", 1, tip="Small documents are usually opened in the browser, not downloaded")
        option(c, "Files with no known type must be at least:", {"1 MB": 1, "5 MB": 5, "10 MB": 10, "50 MB": 50},
               "min_binary_mb", 5, tip="Applies to generic binary downloads (application/octet-stream)")
        switch(c, "Also take over video and audio streams by their content type", "capture_media_mime", True)
        switch(c, "Only take over downloads that I started with a click", "capture_require_click", True,
               tip="Prevents pages from starting downloads behind your back")
        ctk.CTkFrame(c, height=4, fg_color="transparent").pack()

    # ================================================================== Browser
    def build_browser(p):
        c = card(p, "Browser extension", "puzzle")
        st = ctk.CTkLabel(c, text="", font=("Segoe UI", 12), anchor="w", justify="left", wraplength=600)
        st.pack(fill=tk.X, padx=16, pady=(0, 4))

        def refresh_status():
            if not st.winfo_exists():
                return
            t, v = ext_info.get("t", 0), ext_info.get("v", "")
            if not t:
                st.configure(text="●  No contact from the extension yet since this program started.", text_color="#FF9800")
            else:
                ago = int(time.time() - t)
                when = "just now" if ago < 10 else (f"{ago} seconds ago" if ago < 90 else f"{ago // 60} minutes ago")
                ok = (v == EXTENSION_VERSION) or not v
                st.configure(text=f"●  Extension connected (version {v or '?'}), last contact {when}."
                                  + ("" if ok else f"  Expected extension version {EXTENSION_VERSION}: update the extension files."),
                             text_color=GREEN if ok else "#FF9800")
            st.after(3000, refresh_status)
        refresh_status()
        note(c, "Load the extension folder in your browser (chrome://extensions → Developer mode → Load unpacked). "
                "Changes you make in this window reach the extension within about a minute.")

        c = card(p, "Capturing downloads", "puzzle")
        switch(c, "Take over downloads started in the browser", "capture_enabled", True,
               tip="Turn off to let the browser download everything itself (right-click menu items still work)")
        option(c, "Hold this key while clicking a link to let the browser download it:",
               {"Alt": "alt", "Ctrl": "ctrl", "Shift": "shift", "None": "none"}, "bypass_key", "alt",
               tip="Same idea as IDM's “Alt = don't take over” key")
        ctk.CTkFrame(c, height=4, fg_color="transparent").pack()

        c = card(p, "Right-click menu in the browser", "puzzle")
        menu_cfg = dict(get_setting("browser_menu", {}) or {})
        for key, text in MENU_ITEMS:
            v = ctk.BooleanVar(value=bool(menu_cfg.get(key, True)))

            def on(k=key, var=v):
                m = dict(get_setting("browser_menu", {}) or {})
                m[k] = bool(var.get())
                save_settings("browser_menu", m)
            ctk.CTkSwitch(c, text=text, variable=v, command=on, font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=4)
        note(c, "Choose which items appear when you right-click in the browser.")

    # ================================================================== Network
    def build_network(p):
        c = card(p, "Proxy", "globe")
        raw = (get_setting("proxy", "") or "").strip()
        pu = urllib.parse.urlparse(raw) if raw else None
        cur_type = next((k for k, v in PROXY_TYPES.items() if pu and v == pu.scheme), "None")
        ptype = ctk.StringVar(value=cur_type)
        label(c, "Proxy type:")
        ctk.CTkOptionMenu(c, variable=ptype, values=list(PROXY_TYPES.keys()), font=("Segoe UI", 12)).pack(anchor="w", padx=16, pady=(0, 6))
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill=tk.X, padx=16)
        ents = {}
        for i, (key, ph, w, show_c) in enumerate((("host", "Host (proxy.example.com)", 230, ""), ("port", "Port", 80, ""),
                                                   ("user", "User (optional)", 150, ""), ("pass", "Password (optional)", 150, "•"))):
            e = ctk.CTkEntry(grid, placeholder_text=ph, width=w, show=show_c)
            e.grid(row=i // 2, column=i % 2, padx=(0, 8), pady=3, sticky="w")
            ents[key] = e
        if pu:
            if pu.hostname:
                ents["host"].insert(0, pu.hostname)
            if pu.port:
                ents["port"].insert(0, str(pu.port))
            if pu.username:
                ents["user"].insert(0, urllib.parse.unquote(pu.username))
            if pu.password:
                ents["pass"].insert(0, urllib.parse.unquote(pu.password))
        pstate = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), anchor="w")
        pstate.pack(fill=tk.X, padx=16, pady=(4, 0))

        def apply_proxy(clear=False):
            scheme = PROXY_TYPES[ptype.get()]
            if clear or not scheme:
                save_settings("proxy", "")
                pstate.configure(text="Proxy is off.", text_color="gray")
                return
            h, port = ents["host"].get().strip(), ents["port"].get().strip()
            if not h or not port.isdigit() or not (0 < int(port) < 65536):
                messagebox.showwarning("Proxy", "Enter a host and a port number (for example 8080).", parent=win)
                return
            auth = ""
            if ents["user"].get().strip():
                auth = urllib.parse.quote(ents["user"].get().strip(), safe="")
                if ents["pass"].get():
                    auth += ":" + urllib.parse.quote(ents["pass"].get(), safe="")
                auth += "@"
            save_settings("proxy", f"{scheme}://{auth}{h}:{port}")
            pstate.configure(text="Saved.", text_color=GREEN)

        def clear_proxy():
            ptype.set("None")
            for e in ents.values():
                e.delete(0, tk.END)
            apply_proxy(True)
        prow = ctk.CTkFrame(c, fg_color="transparent")
        prow.pack(anchor="w", padx=16, pady=(6, 6))
        ctk.CTkButton(prow, text="Save", width=90, fg_color=GREEN, hover_color=GREEN_H, command=apply_proxy).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkButton(prow, text="Turn off", width=90, fg_color="gray40", command=clear_proxy).pack(side=tk.LEFT)
        note(c, "Video sites support HTTP and SOCKS proxies. Direct file downloads support HTTP/HTTPS proxies only.")

        c = card(p, "User-Agent", "globe")
        note(c, "Used for video sites and for downloads where the browser did not send its own identity. Leave empty for the default.")
        ua_e = ctk.CTkEntry(c, placeholder_text="Mozilla/5.0 ...", height=32)
        ua_e.pack(fill=tk.X, padx=16, pady=(0, 6))
        if get_setting("user_agent", ""):
            ua_e.insert(0, get_setting("user_agent", ""))
        ua_e.bind("<FocusOut>", lambda ev: save_settings("user_agent", ua_e.get().strip()))
        ctk.CTkButton(c, text="Use default", width=110, fg_color="gray40",
                      command=lambda: (ua_e.delete(0, tk.END), save_settings("user_agent", ""))).pack(anchor="w", padx=16, pady=(0, 12))

        c = card(p, "Site logins", "globe")
        note(c, "Username and password sent (HTTP Basic) when downloading files from a site. Stored on this PC in the settings file, not encrypted.")
        listbox = ctk.CTkFrame(c, fg_color="transparent")
        listbox.pack(fill=tk.X, padx=16)

        def render_logins():
            for w in listbox.winfo_children():
                w.destroy()
            logins = get_setting("site_logins", {}) or {}
            if not logins:
                ctk.CTkLabel(listbox, text="No saved logins.", font=("Segoe UI", 11), text_color="gray", anchor="w").pack(fill=tk.X)
            for h, cred in sorted(logins.items()):
                r = ctk.CTkFrame(listbox, fg_color="transparent")
                r.pack(fill=tk.X, pady=2)
                ctk.CTkLabel(r, text=f"{h}   —   {cred.get('u', '')}", font=("Segoe UI", 12), anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
                ctk.CTkButton(r, text="Remove", width=70, height=26, fg_color="#e53935", hover_color="#c62828",
                              command=lambda hh=h: remove_login(hh)).pack(side=tk.RIGHT)

        def remove_login(h):
            logins = dict(get_setting("site_logins", {}) or {})
            logins.pop(h, None)
            save_settings("site_logins", logins)
            render_logins()
        add = ctk.CTkFrame(c, fg_color="transparent")
        add.pack(fill=tk.X, padx=16, pady=(8, 12))
        h_e = ctk.CTkEntry(add, placeholder_text="site.com", width=170)
        u_e = ctk.CTkEntry(add, placeholder_text="Username", width=130)
        pw_e = ctk.CTkEntry(add, placeholder_text="Password", width=130, show="•")
        for w in (h_e, u_e, pw_e):
            w.pack(side=tk.LEFT, padx=(0, 6))

        def add_login():
            h = re.sub(r"^https?://", "", h_e.get().strip().lower()).split("/")[0]
            if not h or not u_e.get().strip():
                messagebox.showwarning("Site logins", "Enter the site and the username.", parent=win)
                return
            logins = dict(get_setting("site_logins", {}) or {})
            logins[h] = {"u": u_e.get().strip(), "p": pw_e.get()}
            save_settings("site_logins", logins)
            for w in (h_e, u_e, pw_e):
                w.delete(0, tk.END)
            render_logins()
        ctk.CTkButton(add, text="Add", width=60, fg_color=GREEN, hover_color=GREEN_H, command=add_login).pack(side=tk.LEFT)
        render_logins()

        c = card(p, "Login-protected downloads", "globe")
        note(c, "Files you click in the browser are sent with your browser's cookies and user-agent, so downloads that need a login work. "
                "For age-restricted YouTube videos choose a cookies.txt file in Tools.")

    # ================================================================== Schedule
    def build_schedule(p):
        c = card(p, "Download schedule", "alarm")
        sched_var = ctk.BooleanVar(value=bool(get_setting("schedule_enabled", False)))
        ctk.CTkSwitch(c, text="Only download during these hours", variable=sched_var, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 8))
        trow = ctk.CTkFrame(c, fg_color="transparent")
        trow.pack(anchor="w", padx=16, pady=4)
        ctk.CTkLabel(trow, text="From", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 6))
        start_e = ctk.CTkEntry(trow, width=80, placeholder_text="02:00")
        start_e.pack(side=tk.LEFT)
        ctk.CTkLabel(trow, text="to", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=8)
        stop_e = ctk.CTkEntry(trow, width=80, placeholder_text="06:00")
        stop_e.pack(side=tk.LEFT)
        for ent, key in ((start_e, "schedule_start"), (stop_e, "schedule_stop")):
            if get_setting(key, ""):
                ent.insert(0, get_setting(key, ""))
        drow = ctk.CTkFrame(c, fg_color="transparent")
        drow.pack(anchor="w", padx=16, pady=(8, 4))
        cur_days = set(get_setting("schedule_days", list(range(7))))
        day_vars = []
        for idx, dn in enumerate(DAY_NAMES):
            v = ctk.BooleanVar(value=idx in cur_days)
            day_vars.append(v)
            ctk.CTkCheckBox(drow, text=dn, variable=v, width=60, checkbox_width=18, checkbox_height=18, font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=2)
        state_lbl = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), anchor="w")
        state_lbl.pack(fill=tk.X, padx=16, pady=(6, 2))

        def refresh_state():
            if not get_setting("schedule_enabled", False):
                state_lbl.configure(text="Schedule is off: downloads run any time.", text_color="gray")
            elif schedule_allows():
                state_lbl.configure(text="✔ Now: downloads are allowed", text_color=GREEN)
            else:
                state_lbl.configure(text="Now: waiting for the schedule", text_color="#FF9800")

        def apply_schedule():
            en, st, sp = bool(sched_var.get()), start_e.get().strip(), stop_e.get().strip()
            if en and _parse_hhmm(st) is None:
                messagebox.showwarning("Schedule", "Enter the start time as HH:MM, for example 02:00.", parent=win)
                return
            if sp and _parse_hhmm(sp) is None:
                messagebox.showwarning("Schedule", "Enter the stop time as HH:MM, for example 06:00 (or leave it empty).", parent=win)
                return
            days = [i for i, v in enumerate(day_vars) if v.get()]
            if en and not days:
                messagebox.showwarning("Schedule", "Select at least one day.", parent=win)
                return
            save_settings("schedule_enabled", en)
            save_settings("schedule_start", st)
            save_settings("schedule_stop", sp)
            save_settings("schedule_days", days)
            limiter.poke()
            refresh_state()
        ctk.CTkButton(c, text="Apply schedule", fg_color=GREEN, hover_color=GREEN_H, command=apply_schedule).pack(anchor="w", padx=16, pady=(4, 6))
        note(c, "Downloads pause outside the window and resume by themselves. A window like 23:00 to 06:00 runs overnight. "
                "With no stop time it runs until midnight.")
        refresh_state()

    # ================================================================== Data usage
    def build_usage(p):
        c = card(p, "Data limit", "gauge")
        en_var = ctk.BooleanVar(value=bool(get_setting("quota_enabled", False)))
        ctk.CTkSwitch(c, text="Limit my data usage", variable=en_var, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 8))

        PER = {"Daily": "day", "Monthly": "month", "Custom period": "custom"}
        per_rev = {v: k for k, v in PER.items()}
        per_var = ctk.StringVar(value=per_rev.get(get_setting("quota_period", "month"), "Monthly"))
        r1 = ctk.CTkFrame(c, fg_color="transparent")
        r1.pack(anchor="w", padx=16, pady=4)
        ctk.CTkLabel(r1, text="Period", font=("Segoe UI", 12), width=70, anchor="w").pack(side=tk.LEFT)
        dyn = ctk.CTkFrame(c, fg_color="transparent")

        # الحد: رقم + وحدة
        lim_mb = float(get_setting("quota_limit_mb", 0) or 0)
        use_gb = lim_mb >= 1024
        r2 = ctk.CTkFrame(c, fg_color="transparent")
        r2.pack(anchor="w", padx=16, pady=4)
        ctk.CTkLabel(r2, text="Limit", font=("Segoe UI", 12), width=70, anchor="w").pack(side=tk.LEFT)
        lim_e = ctk.CTkEntry(r2, width=90, placeholder_text="10")
        lim_e.pack(side=tk.LEFT)
        if lim_mb > 0:
            v = lim_mb / 1024 if use_gb else lim_mb
            lim_e.insert(0, f"{v:g}")
        unit_var = ctk.StringVar(value="GB" if use_gb or lim_mb <= 0 else "MB")
        ctk.CTkOptionMenu(r2, variable=unit_var, values=["MB", "GB"], width=70, font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=8)

        # حقول خاصة بكل نوع فترة
        month_row = ctk.CTkFrame(dyn, fg_color="transparent")
        ctk.CTkLabel(month_row, text="Resets on day", font=("Segoe UI", 12), width=100, anchor="w").pack(side=tk.LEFT)
        reset_e = ctk.CTkEntry(month_row, width=60, placeholder_text="1")
        reset_e.pack(side=tk.LEFT)
        reset_e.insert(0, str(get_setting("quota_reset_day", 1)))
        ctk.CTkLabel(month_row, text="of each month (1-28)", font=("Segoe UI", 11), text_color="gray").pack(side=tk.LEFT, padx=8)
        custom_row = ctk.CTkFrame(dyn, fg_color="transparent")
        ctk.CTkLabel(custom_row, text="Every", font=("Segoe UI", 12)).pack(side=tk.LEFT)
        days_e = ctk.CTkEntry(custom_row, width=60, placeholder_text="30")
        days_e.pack(side=tk.LEFT, padx=6)
        days_e.insert(0, str(get_setting("quota_custom_days", 30)))
        ctk.CTkLabel(custom_row, text="days, starting", font=("Segoe UI", 12)).pack(side=tk.LEFT)
        start_e = ctk.CTkEntry(custom_row, width=110, placeholder_text="YYYY-MM-DD")
        start_e.pack(side=tk.LEFT, padx=6)
        start_e.insert(0, get_setting("quota_cycle_start", "") or time.strftime("%Y-%m-%d"))

        def show_fields(_choice=None):
            month_row.pack_forget()
            custom_row.pack_forget()
            kind = PER.get(per_var.get(), "month")
            if kind == "month":
                month_row.pack(anchor="w", pady=4)
            elif kind == "custom":
                custom_row.pack(anchor="w", pady=4)
        ctk.CTkOptionMenu(r1, variable=per_var, values=list(PER.keys()), command=show_fields, width=150, font=("Segoe UI", 12)).pack(side=tk.LEFT)
        dyn.pack(anchor="w", padx=16, after=r2)
        show_fields()

        msg_lbl = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), anchor="w", wraplength=600, justify="left")

        def apply_quota():
            en = bool(en_var.get())
            try:
                val = float(lim_e.get().strip().replace(",", ".")) if lim_e.get().strip() else 0.0
            except ValueError:
                val = -1.0
            if en and val <= 0:
                messagebox.showwarning("Data limit", "Enter the limit as a number greater than zero, for example 10.", parent=win)
                return
            kind = PER.get(per_var.get(), "month")
            if kind == "month":
                try:
                    rd = int(reset_e.get().strip() or "1")
                except ValueError:
                    rd = 0
                if not 1 <= rd <= 28:
                    messagebox.showwarning("Data limit", "The reset day must be a number from 1 to 28.", parent=win)
                    return
                save_settings("quota_reset_day", rd)
            elif kind == "custom":
                try:
                    nd = int(days_e.get().strip())
                except ValueError:
                    nd = 0
                if not 1 <= nd <= 366:
                    messagebox.showwarning("Data limit", "Enter the number of days (1 to 366).", parent=win)
                    return
                if usage._parse_date(start_e.get().strip()) is None:
                    messagebox.showwarning("Data limit", "Enter the start date as YYYY-MM-DD, for example 2026-11-01.", parent=win)
                    return
                save_settings("quota_custom_days", nd)
                save_settings("quota_cycle_start", start_e.get().strip())
            mb = val * 1024 if unit_var.get() == "GB" else val
            save_settings("quota_enabled", en)
            save_settings("quota_period", kind)
            save_settings("quota_limit_mb", max(0.0, mb))
            save_settings("quota_override", "")
            save_settings("quota_warned", "")
            limiter.poke()
            msg_lbl.configure(text="✔ Saved", text_color=GREEN)
            refresh()
        ctk.CTkButton(c, text="Apply", fg_color=GREEN, hover_color=GREEN_H, command=apply_quota).pack(anchor="w", padx=16, pady=(8, 4))
        msg_lbl.pack(fill=tk.X, padx=16, pady=(0, 2))
        note(c, "When the limit is reached, running downloads pause and new ones wait until the next period starts. "
                "You can also choose to continue anyway for the current period.")

        # ---------------- الاستهلاك الحالي
        u = card(p, "Current usage", "download")
        used_lbl = ctk.CTkLabel(u, text="", font=("Segoe UI", 13, "bold"), anchor="w")
        used_lbl.pack(fill=tk.X, padx=16, pady=(0, 4))
        bar = ctk.CTkProgressBar(u, height=12, progress_color=GREEN)
        bar.pack(fill=tk.X, padx=16, pady=(0, 6))
        bar.set(0)
        per_lbl = ctk.CTkLabel(u, text="", font=("Segoe UI", 11), text_color="gray", anchor="w")
        per_lbl.pack(fill=tk.X, padx=16, pady=(0, 4))
        btn_row = ctk.CTkFrame(u, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(2, 8))
        cont_btn = ctk.CTkButton(btn_row, text="Continue anyway (this period)", fg_color="#FF9800", hover_color="#e68900", text_color="#1a1a1a",
                                 command=lambda: (usage.override_this_period(), limiter.poke(), refresh()))

        def reset_counter():
            if messagebox.askyesno("Reset counter", "Reset the usage counter of the current period to zero?", parent=win):
                usage.reset_period_counter()
                limiter.poke()
                refresh()
        ctk.CTkButton(btn_row, text="Reset counter", fg_color=("#e4e8ed", "#2a2f38"), hover_color=("#d6e0f0", "#2f3846"),
                      text_color=("#1a1a1a", "#e8eaed"), command=reset_counter).pack(side=tk.LEFT)

        h = card(p, "Last 7 days", "gauge")
        day_rows = []
        for _i in range(7):
            row = ctk.CTkFrame(h, fg_color="transparent")
            row.pack(fill=tk.X, padx=16, pady=2)
            dl = ctk.CTkLabel(row, text="", width=110, anchor="w", font=("Segoe UI", 11))
            dl.pack(side=tk.LEFT)
            pb = ctk.CTkProgressBar(row, height=8, progress_color=GREEN)
            pb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
            vl = ctk.CTkLabel(row, text="", width=90, anchor="e", font=("Segoe UI", 11))
            vl.pack(side=tk.LEFT)
            day_rows.append((dl, pb, vl))
        total_lbl = ctk.CTkLabel(h, text="", font=("Segoe UI", 11), text_color="gray", anchor="w")
        total_lbl.pack(fill=tk.X, padx=16, pady=(6, 4))
        note(h, "Counts the data this program downloads (files and videos). It is not your whole computer's internet usage, "
                "and small requests such as video info and thumbnails are not counted.")

        def refresh():
            try:
                if not win.winfo_exists():
                    return
                snap = usage.snapshot()
                s, e, _k = snap["start"], snap["end"], snap["kind"]
                if snap["enabled"]:
                    used_lbl.configure(text=f"Used {fmt_bytes(snap['used'])} of {fmt_bytes(snap['limit'])}  ({min(999, int(snap['frac'] * 100))}%)")
                    bar.set(min(1.0, snap["frac"]))
                    bar.configure(progress_color="#e53935" if snap["exceeded"] else ("#FF9800" if snap["frac"] >= 0.8 else GREEN))
                    if snap["exceeded"] and snap["overridden"]:
                        per_lbl.configure(text=f"Current period: {s.isoformat()} → {(e - usage.timedelta(days=1)).isoformat()}   |   Limit passed: downloads continue (override)")
                    else:
                        per_lbl.configure(text=f"Current period: {s.isoformat()} → {(e - usage.timedelta(days=1)).isoformat()}")
                else:
                    used_lbl.configure(text=f"Used today: {fmt_bytes(snap['today'])}")
                    bar.set(0)
                    per_lbl.configure(text="No data limit is set.")
                if snap["exceeded"] and not snap["overridden"]:
                    if not cont_btn.winfo_manager():
                        cont_btn.pack(side=tk.LEFT, padx=(0, 8), before=btn_row.winfo_children()[0])
                elif cont_btn.winfo_manager():
                    cont_btn.pack_forget()
                days = usage.last_days(7)
                mx = max([b for _d, b in days] + [1])
                for (dl, pb, vl), (d, b) in zip(day_rows, days):
                    dl.configure(text=d.strftime("%a %d %b"))
                    pb.set(b / mx)
                    vl.configure(text=fmt_bytes(b) if b else "-")
                total_lbl.configure(text=f"Total downloaded since the counter started: {fmt_bytes(usage.total_all())}")
            except Exception:
                return
            win.after(2000, refresh)
        refresh()

    # ================================================================== Tools
    def build_tools(p):
        c = card(p, "ffmpeg", "toolbox")
        ff_state = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), anchor="w", wraplength=600, justify="left")
        ff_state.pack(fill=tk.X, padx=16, pady=(0, 4))

        def refresh_ff():
            reset_ffmpeg_cache()
            found = find_ffmpeg()
            ff_state.configure(text=f"✔ Using: {found}" if found else "ffmpeg was not found. Merging video and cutting parts need it.",
                               text_color=GREEN if found else "#FF9800")
        label(c, "Path to ffmpeg (leave empty to detect automatically):")
        file_row(c, "ffmpeg_path", "C:\\ffmpeg\\bin\\ffmpeg.exe", [("ffmpeg", "ffmpeg*"), ("All files", "*.*")], on_change=refresh_ff)
        refresh_ff()

        c = card(p, "Cookies file", "cookie")
        note(c, "A cookies.txt exported from your browser lets video sites treat you as logged in (age-restricted or members-only videos).")
        file_row(c, "cookies_file", "cookies.txt", [("Cookies", "*.txt"), ("All files", "*.*")])
        if COOKIES_HELP_URL:
            ctk.CTkButton(c, text="How to export cookies.txt", image=icon_ctk("cookie", 16), compound="left", fg_color="gray40",
                          command=lambda: webbrowser.open(COOKIES_HELP_URL)).pack(anchor="w", padx=16, pady=(0, 12))

        c = card(p, "Data and logs", "toolbox")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(anchor="w", padx=16, pady=(0, 6))
        ctk.CTkButton(row, text="Open data folder", fg_color="gray40", command=lambda: open_path(APP_DATA_DIR)).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkButton(row, text="Open log file", fg_color="gray40",
                      command=lambda: open_path(LOG_FILE) if os.path.exists(LOG_FILE) else None).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkButton(row, text="Export all links", image=icon_ctk("export", 16), compound="left", fg_color="gray40",
                      command=export_links).pack(side=tk.LEFT)
        size_lbl = ctk.CTkLabel(c, text="", font=("Segoe UI", 11), text_color="gray", anchor="w")
        size_lbl.pack(fill=tk.X, padx=16, pady=(4, 0))

        def clip_cache_size():
            total = 0
            for root_d, _dirs, files in os.walk(clipwork.CLIPS_DIR):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root_d, f))
                    except OSError:
                        pass
            return total

        def refresh_cache():
            mb = (clip_cache_size() + partsdir.total_bytes()) / 1048576
            size_lbl.configure(text=f"Saved parts of paused downloads: {mb:.1f} MB")

        def clear_cache():
            with_active = {t.get("clip_key") or t.get("part_key") for t in tasks.values()
                           if t.get("status") in ("paused", "error")}
            if with_active and not messagebox.askyesno("Clear cache", "Some paused downloads would restart from the beginning. Continue?", parent=win):
                return
            clipwork.sweep(set())
            partsdir.sweep(set())
            refresh_cache()
        ctk.CTkButton(c, text="Clear saved parts", fg_color="gray40", command=clear_cache).pack(anchor="w", padx=16, pady=(4, 12))
        refresh_cache()

    # ================================================================== Updates
    def build_updates(p):
        c = card(p, "Program updates", "update")
        prog_lbl = ctk.CTkLabel(c, text=f"Version {APP_VERSION}", font=("Segoe UI", 12), anchor="w")
        prog_lbl.pack(fill=tk.X, padx=16, pady=(0, 4))
        switch(c, "Check for updates automatically", "auto_update", True,
               tip="The program checks for a new version when it starts and every few hours, then asks before installing.")

        def report(text, ok):
            if prog_lbl.winfo_exists():
                prog_lbl.configure(text=text, text_color=GREEN if ok else "#FF9800")

        def check_program():
            prog_lbl.configure(text="Checking for updates...", text_color="gray")
            manual_check(report)
        ctk.CTkButton(c, text="Check for program update", image=icon_ctk("update", 16), compound="left", fg_color=GREEN, hover_color=GREEN_H,
                      command=check_program).pack(anchor="w", padx=16, pady=(4, 12))

        c = card(p, "Download engine (yt-dlp)", "update")
        cur_ver = getattr(ensure_ytdlp().version, "__version__", "?")
        status_lbl = ctk.CTkLabel(c, text=f"Current engine: yt-dlp v{cur_ver}", font=("Segoe UI", 11), text_color="gray", wraplength=600, anchor="w", justify="left")
        status_lbl.pack(fill=tk.X, padx=16, pady=(0, 6))

        def on_update_result(status, ver):
            msgs = {"updated": f"✅ Update downloaded (v{ver}), active after restart.",
                    "latest": f"✅ Already up to date (v{ver}).",
                    "updated_old": f"✅ Updated to v{ver}, the newest your Python {sys.version_info[0]}.{sys.version_info[1]} can run.",
                    "latest_old": f"ℹ️ v{ver} is the newest your Python {sys.version_info[0]}.{sys.version_info[1]} can run.",
                    "error": "⚠️ Update check failed (check your internet)."}
            ui(lambda: status_lbl.winfo_exists() and status_lbl.configure(text=msgs[status]))

        def manual_check_update():
            status_lbl.configure(text="Checking for updates...")
            check_and_update_ytdlp_async(on_update_result)
        ctk.CTkButton(c, text="Check for engine update", fg_color=GREEN, hover_color=GREEN_H,
                      command=manual_check_update).pack(anchor="w", padx=16, pady=(0, 12))

        c = card(p, "JavaScript engine (YouTube)", "gears")
        from aerograb.tools import has_js_runtime, install_deno, js_runtime_report
        js_lbl = ctk.CTkLabel(c, text="Checking...", font=("Segoe UI", 11), text_color="gray", wraplength=600, anchor="w", justify="left")
        js_lbl.pack(fill=tk.X, padx=16, pady=(0, 6))

        def js_refresh():
            def work():
                rep = js_runtime_report(True)
                ok = [n for n, i in rep.items() if i["supported"]]
                ui(lambda: js_lbl.winfo_exists() and js_lbl.configure(
                    text=(f"✔ Using: {ok[0]}" if ok else "YouTube needs a JavaScript engine (deno or Node.js). Without it videos fail with “Requested format is not available”."),
                    text_color=GREEN if ok else "#FF9800"))
            threading.Thread(target=work, daemon=True).start()
        js_refresh()

        def js_install():
            js_lbl.configure(text="Installing the JavaScript engine (one time)...", text_color="gray")

            def work():
                ok, msg = install_deno(force=True)
                rt = next((n for n, i in js_runtime_report(True).items() if i["supported"]), "deno")
                ui(lambda: js_lbl.winfo_exists() and js_lbl.configure(
                    text=(f"✔ Using: {rt} {msg}" if ok else f"⚠️ Install failed: {msg}"), text_color=GREEN if ok else "#FF9800"))
            threading.Thread(target=work, daemon=True).start()
        ctk.CTkButton(c, text="Install / repair the JavaScript engine", fg_color=GREEN, hover_color=GREEN_H,
                      command=js_install).pack(anchor="w", padx=16, pady=(0, 12))
        note(c, "Downloaded once (about 30-40 MB) from the official Deno / Node.js releases and kept inside the program's data folder. 32-bit Windows uses Node.js.")

        c = card(p, "Versions", "info")
        ev = ext_info.get("v") or "not connected yet"
        ctk.CTkLabel(c, text=f"Program: {APP_VERSION}\nBrowser extension: {ev}", font=("Segoe UI", 12), anchor="w", justify="left").pack(fill=tk.X, padx=16, pady=(0, 12))

    # ================================================================== About
    def build_about(p):
        top = ctk.CTkFrame(p, corner_radius=10)
        top.pack(fill=tk.X, pady=(0, 10), padx=2)
        ctk.CTkLabel(top, text="", image=logo_ctk(96)).pack(pady=(18, 6))
        ctk.CTkLabel(top, text=APP_NAME, font=("Segoe UI", 26, "bold")).pack()
        ctk.CTkLabel(top, text=f"Version {APP_VERSION}", font=("Segoe UI", 12), text_color="gray").pack()
        ctk.CTkLabel(top, text="Fast, private download manager for Windows", font=("Segoe UI", 13)).pack(pady=(6, 18))

        c = card(p, "Your privacy", "info")
        note(c, "No ads, no account, no analytics. Your download list, settings and saved logins stay on this PC. "
                "The program only goes online for the downloads you start, the video thumbnails of links you add, "
                "and the engine update check when you press the button in Updates.")

        c = card(p, "What it does", "bolt")
        note(c, "• Splits files into parts for faster downloads, with pause, resume and automatic retries\n"
                "• Takes over downloads from your browser (Alt = let the browser handle it)\n"
                "• Downloads videos and playlists, or only a part of a video, with resume\n"
                "• Queue, schedule, speed limit, categories, link grabber and clipboard watching\n"
                "• Refresh an expired link and keep the part you already downloaded\n"
                "• Check a file's SHA-256 / SHA-1 / MD5 against the hash the publisher gives you")

        c = card(p, "Credits", "puzzle")
        note(c, "Video support is powered by yt-dlp and ffmpeg.")

        c = card(p, "Copyright and license", "copyright")
        ctk.CTkLabel(c, text=f"© {time.strftime('%Y')} {COPYRIGHT_OWNER}.  All rights reserved.", font=("Segoe UI", 12), anchor="w").pack(fill=tk.X, padx=16, pady=(0, 8))
        lrow = ctk.CTkFrame(c, fg_color="transparent")
        lrow.pack(anchor="w", padx=14, pady=(0, 12))
        for ico, attr, tip in LINK_BUTTONS:
            lb = ctk.CTkButton(lrow, text="", image=icon_ctk(ico, 22), width=44, height=38, fg_color=("#e4e8ed", "#232730"),
                               hover_color=("#d6e0f0", "#2f3846"), corner_radius=8, command=lambda a=attr: open_link(a, win))
            lb.pack(side=tk.LEFT, padx=4)
            attach_tip(lb, tip)
        shb = ctk.CTkButton(lrow, text="", image=icon_ctk("share", 22), width=44, height=38, fg_color=("#e4e8ed", "#232730"),
                            hover_color=("#d6e0f0", "#2f3846"), corner_radius=8, command=lambda: copy_share_link(shb))
        shb.pack(side=tk.LEFT, padx=4)
        attach_tip(shb, "Copy the program link to share it with others")

    builders.update({"General": build_general, "Downloads": build_downloads, "Video": build_video, "Save to": build_saveto,
                     "File types": build_filetypes, "Browser": build_browser, "Network": build_network,
                     "Schedule": build_schedule, "Data usage": build_usage, "Tools": build_tools, "Updates": build_updates, "About": build_about})
    _settings_show[0] = lambda n: show(n) if n in builders else None
    show(section if section in builders else "General")


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.views.grabber import CAT_ORDER, DAY_NAMES, _settings_win, force_quit_app  # noqa: E402
from aerograb.views.icons import icon_ctk  # noqa: E402
from aerograb.views.mainwin import (  # noqa: E402
    SPEED_CHOICES,
    _clip,
    export_links,
    load_icon,
    open_save_folder,
    play_done_sound,
    set_speed_limit,
    update_main_theme,
)
from aerograb.views.popups import choose_directory  # noqa: E402
from aerograb.views.linkutil import LINK_BUTTONS, copy_share_link, open_link  # noqa: E402
from aerograb.views.updatedlg import manual_check  # noqa: E402
from aerograb.views.winutil import open_path  # noqa: E402
