# -*- coding: utf-8 -*-
import os
import threading
import time
import logging, logging.handlers
import traceback
import subprocess
import queue
import customtkinter as ctk
from tkinter import filedialog
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
from aerograb import i18n
from aerograb.winround import round_window
from aerograb.common import get_setting, log_error, resource_path, save_settings
from aerograb.config import HOME, UI_FONT
from aerograb import usage
from aerograb.fmt import QUALITY_MAP
from aerograb.state import ACTIVE_STATUSES, _ui_queue, gui_lock, pending_batches, pending_urls, tasks, tasks_lock
from aerograb.system import app_launch_argv
from aerograb.ytdlp_mgr import ensure_ytdlp
from aerograb.uistate import gui
from aerograb.views.dialogs import refresh_selected, verify_selected
from aerograb.views.branding import apply_window_icon, logo_ctk, set_app_user_model_id
from aerograb.views.tooltip import attach as attach_tip


def _ui_pump():
    try:
        for _ in range(300):
            fn, a, kw = _ui_queue.get_nowait()
            try:
                fn(*a, **kw)
            except Exception as e:
                log_error("ui callback", e)
    except queue.Empty:
        pass
    try:
        gui.root.after(40, _ui_pump)
    except Exception:
        pass



def _ui_scale():
    try:
        return max(1.0, float(ctk.ScalingTracker.get_window_scaling(gui.root)))
    except Exception:
        try:
            return max(1.0, gui.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            return 1.0



def restart_in_background():
    """بنشغّل نسخة خلفية جديدة (بتستنى البورت يتحرر) وبعدين نقفل الحالية."""
    try:
        subprocess.Popen(app_launch_argv() + ["--background", "--restarted"], close_fds=True)
    except Exception as e:
        log_error("restart_in_background", e)
        gui.root.withdraw()
        return
    shutdown_server()
    os._exit(0)



def change_language(code):
    """بيحفظ اللغة ويعيد تشغيل البرنامج (الواجهة بتتبني بلغتها من الأول). التنزيلات الجارية بتتوقف مؤقتاً."""
    if code == i18n.lang():
        return
    with tasks_lock:
        active = any(t["status"] in ACTIVE_STATUSES for t in tasks.values())
    msg = "The program will restart to apply the language."
    if active:
        msg += "\nDownloads that are running will be paused and can be resumed after the restart."
    if not messagebox.askyesno("Language", msg, parent=gui.root):
        return
    save_settings("language", code)
    save_history()
    try:
        subprocess.Popen(app_launch_argv() + ["--restarted"], close_fds=True)
    except Exception as e:
        log_error("change_language restart", e)
        return
    shutdown_server()
    os._exit(0)


STAT_TIPS = {"act": "Downloads running right now", "queue": "Downloads waiting for a free slot",
             "done": "Downloads that finished successfully",
             "fail": "Downloads that failed. Right-click a failed download and choose Resume / Retry or Re-download"}


def main_gui(initial_items=None):
    ensure_ytdlp()
    i18n.init_language(get_setting("language", ""))
    i18n.install_hooks()                       # بيترجم أي نص بيتعرض لو اللغة عربي
    gui.tk, gui.ttk, gui.messagebox, gui.filedialog, gui.ctk = tk, ttk, messagebox, filedialog, ctk

    ctk.set_default_color_theme("green")
    set_app_user_model_id()
    gui.root = ctk.CTk()
    gui.root.title("AeroGrab")
    apply_window_icon(gui.root)
    from aerograb.views.winutil import fit_geometry
    fit_geometry(gui.root, 1040, 650, 760, 480)                    # حجم يناسب الشاشة اللي شغّالة عليها
    gui.root.configure(fg_color=("#eef0f3", "#101114"))
    gui.root.report_callback_exception = lambda exc, val, tb: logging.error("Tk callback error: %s", "".join(traceback.format_exception(exc, val, tb)))

    my_font = ctk.CTkFont(family=UI_FONT, size=12, weight="bold")
    small_font = ctk.CTkFont(family=UI_FONT, size=11)
    bg_frame = ("#ffffff", "#16181c")
    border_c = ("#dde1e6", "#262a31")
    hover_c = ("#e3e3e3", "#2a2a2a")
    entry_bg = ("#ffffff", "#1c1c1c")
    text_c = ("#1a1a1a", "#e0e0e0")
    muted_c = ("#666666", "#9a9a9a")

    gui.search_var = _SearchBox()
    q0 = get_setting("default_quality", "1080p")
    gui.quality_var = ctk.StringVar(value=q0 if q0 in QUALITY_MAP else "1080p")
    gui.download_path_var = ctk.StringVar(value=get_setting("save_path", os.path.join(HOME, "Downloads")))

    # ---------------- شريط الأدوات
    toolbar = ctk.CTkFrame(gui.root, fg_color=bg_frame, corner_radius=12, border_width=1, border_color=border_c)
    toolbar.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(15, 6))

    def tb_btn(text, cmd, side=tk.LEFT, outline=False, danger=False, width=116, icon=None, primary=False, ico=None, tip=None):
        img = icon_ctk(ico, 20) if ico else (load_icon(icon, size=(22, 22)) if icon else None)
        if primary:
            kw = {"fg_color": GREEN, "hover_color": GREEN_H, "text_color": "white"}
        elif outline:
            kw = {"fg_color": "transparent", "hover_color": ("#d5f5e6", "#17372a"), "border_width": 2,
                  "border_color": GREEN, "text_color": ("#117a4d", GREEN)}
        else:
            kw = {"fg_color": "transparent", "hover_color": hover_c,
                  "text_color": ("#c62828", "#ff6b6b") if danger else text_c}
        b = ctk.CTkButton(toolbar, text=text, image=img, compound="left", command=cmd, font=my_font, height=38,
                          width=width, corner_radius=8, **kw)
        b.pack(side=side, padx=4, pady=8)
        if tip:
            attach_tip(b, tip)
        return b

    tb_btn("Add link", add_link_manual, outline=True, width=128, ico="add", tip="Add a new download link  (Ctrl+N or Ctrl+V)")
    tb_btn("Resume all", resume_all_tasks, width=124, ico="play", tip="Resume every paused, failed or canceled download")
    tb_btn("Pause all", pause_all_tasks, width=116, ico="pause", tip="Pause all running downloads")
    tb_btn("Cancel all", cancel_all_tasks, danger=True, width=116, ico="remove", tip="Cancel all running and queued downloads")
    tb_btn("Clear list", clear_list, width=118, ico="trash", tip="Remove finished downloads from the list (files stay on disk)")
    tb_btn("Settings", open_settings_window, side=tk.RIGHT, width=118, ico="settings_gear",
           tip="Open settings: theme, save folder, speed limit, connections...")

    def show_usage_menu(anchor):
        m = tk.Menu(gui.root, tearoff=0, font=("Segoe UI", 11))
        m.add_command(label="Data usage settings…", command=lambda: open_settings_window("Data usage"))
        snap = usage.snapshot()
        if snap["exceeded"] and not snap["overridden"]:
            m.add_command(label="Continue anyway (this period)", command=lambda: (usage.override_this_period(), limiter.poke()))
        try:
            m.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
        finally:
            m.grab_release()

    def usage_events():
        ev = usage.check_events()
        if ev == "warn":
            gui.messagebox.showinfo("Data limit", "You have used 90% of your data limit for this period.")
        elif ev == "limit":
            if gui.messagebox.askyesno("Data limit reached",
                                       "You reached your data limit. Downloads are paused until the next period starts.\n\n"
                                       "Continue downloading anyway for this period?"):
                usage.override_this_period()
                limiter.poke()

    # ---------------- التابات + البحث
    tabs_frame = ctk.CTkFrame(gui.root, fg_color="transparent")
    tabs_frame.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(6, 0))
    for key, label in FILTERS:
        btn = ctk.CTkButton(tabs_frame, text=f"{label} (0)", font=my_font, height=30, width=70, corner_radius=15,
                            border_width=1, command=lambda k=key: filter_tasks(k))
        btn.pack(side=tk.LEFT, padx=2)
        attach_tip(btn, "Show all downloads" if key == "All" else f"Show only: {label}")
        tab_buttons[key] = btn
    search_box = ctk.CTkFrame(tabs_frame, width=262, height=32, corner_radius=8, border_width=2, fg_color=entry_bg, border_color=border_c)
    search_box.pack(side=tk.RIGHT, padx=2)
    search_box.pack_propagate(False)
    ctk.CTkLabel(search_box, text="", image=icon_ctk("search", 15), width=28).pack(side=tk.LEFT, padx=(6, 0))
    search_entry = ctk.CTkEntry(search_box, placeholder_text="Search downloads...", height=26, border_width=0, fg_color="transparent",
                                font=small_font, text_color=text_c)
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
    status_menu = ctk.CTkOptionMenu(tabs_frame, values=list(STATUS_CHOICES.keys()), command=set_status_filter, width=118, height=32,
                                    font=small_font, dropdown_font=small_font)
    status_menu.pack(side=tk.RIGHT, padx=(2, 8))
    attach_tip(status_menu, "Filter the list by status (in progress, paused, completed, failed)")
    attach_tip(search_entry, "Search downloads by name or link  (Ctrl+F)")
    gui.search_var.entry = search_entry
    search_entry.bind("<KeyRelease>", lambda e: apply_layout(force=True))

    # ---------------- الشريط السفلي (طويل ورفيع): العدّادات | التقدم الكلي | المساحة + "لما يخلص"
    import tkinter.font as tkfont
    UI_SCALE = _ui_scale()
    bottom = ctk.CTkFrame(gui.root, fg_color=bg_frame, corner_radius=12, border_width=1, border_color=border_c)
    bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(6, 12))
    left = ctk.CTkFrame(bottom, fg_color="transparent")
    left.pack(side=tk.LEFT, padx=(14, 6), pady=7)
    gui.stat_lbls = {}
    stat_colors = {"act": "#2cc985", "queue": muted_c, "done": "#2cc985", "fail": ("#d6393f", "#ff6b6b")}
    for key, (icon, name) in STAT_META.items():
        gui.stat_lbls[key] = ctk.CTkLabel(left, text=f"0 {name}", font=small_font, text_color=stat_colors[key],
                                      image=icon_ctk(icon, 16), compound="left")
        gui.stat_lbls[key].pack(side=tk.LEFT, padx=(0, 14))
        attach_tip(gui.stat_lbls[key], STAT_TIPS[key])
    right = ctk.CTkFrame(bottom, fg_color="transparent")
    right.pack(side=tk.RIGHT, padx=(6, 12), pady=6)
    gui.after_var = ctk.StringVar(value="Do nothing")
    gui.after_menu = ctk.CTkOptionMenu(right, variable=gui.after_var, values=AFTER_MODES, width=112, height=26, font=small_font)
    gui.after_menu.pack(side=tk.RIGHT)
    attach_tip(gui.after_menu, "What to do automatically when all downloads finish (exit, sleep, shut down...)")
    ctk.CTkLabel(right, text="When all done:", font=small_font, text_color=muted_c).pack(side=tk.RIGHT, padx=(0, 6))
    gui.usage_btn = ctk.CTkButton(right, text="", font=small_font, height=24, width=10, corner_radius=8, fg_color="transparent",
                                  hover_color=hover_c, text_color=muted_c, image=icon_ctk("gauge", 16), compound="left",
                                  command=lambda: show_usage_menu(gui.usage_btn))
    gui.usage_btn.pack(side=tk.RIGHT, padx=(0, 10))
    attach_tip(gui.usage_btn, "Data used by this program. Click for the data limit options")
    gui.overall_font = tkfont.Font(family=UI_FONT, size=-int(13 * UI_SCALE), weight="bold")
    gui.overall_cv = tk.Canvas(bottom, height=int(28 * UI_SCALE), highlightthickness=0, bd=0)
    gui.overall_cv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=7)
    attach_tip(gui.overall_cv, "Overall progress of all unfinished downloads (speed, size, time remaining)")
    gui.overall_cv.bind("<Configure>", lambda e: (_overall_key.update(k=None), update_average_progress()))

    # ---------------- تحت: صف أفقي لكروت التحميلات الشغالة
    strip_frame = ctk.CTkFrame(gui.root, fg_color="transparent", corner_radius=0)
    strip_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=(15, 15), pady=(4, 0))
    gui.strip_title = ctk.CTkButton(strip_frame, text="Active downloads (0)", font=small_font, text_color=muted_c, anchor="w",
                                    image=icon_ctk("caret_down", 16), compound="left", fg_color="transparent", hover_color=hover_c,
                                    height=26, corner_radius=8)
    gui.strip_title.pack(fill=tk.X, padx=2)
    attach_tip(gui.strip_title, "Show or hide the active downloads")
    cards_body = ctk.CTkFrame(strip_frame, fg_color="transparent", corner_radius=0)
    cards_body.pack(side=tk.TOP, fill=tk.X)
    gui.cards = CardGrid(cards_body, UI_SCALE, lambda iid, n: card_action(iid, n),
                     lambda iid: on_double_click(None, iid, True), lambda e, iid: (_sel_src.update(v="cards"), show_context_menu(e, iid)))
    gui.cards.on_activate = lambda: (_sel_src.update(v="cards"), gui.tree.selection_set(()))
    gui.cards.set_empty("No active downloads", "Running downloads will appear here")

    # ---------------- فوق: الجدول (سجل كل التحميلات)
    gui.table_frame = ctk.CTkFrame(gui.root, fg_color=bg_frame, corner_radius=12, border_width=1, border_color=border_c)
    gui.table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(6, 0))
    tree_container = ctk.CTkFrame(gui.table_frame, fg_color="transparent")
    tree_container.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    cols = ("Title", "Type", "Size", "Progress", "Speed", "ETA", "Status", "Date", "Folder")
    gui.tree = ttk.Treeview(tree_container, columns=cols, show="tree headings", height=8, selectmode="extended")
    gui.tree.heading("#0", text="")
    gui.tree.column("#0", width=44, minwidth=44, stretch=False, anchor=tk.CENTER)       # عمود أيقونة الحالة
    for col, w, anc in (("Title", 250, tk.W), ("Type", 86, tk.CENTER), ("Size", 92, tk.CENTER), ("Progress", 62, tk.CENTER),
                        ("Speed", 96, tk.CENTER), ("ETA", 70, tk.CENTER), ("Status", 220, tk.W), ("Date", 100, tk.CENTER),
                        ("Folder", 170, tk.W)):
        gui.tree.heading(col, text=HEADINGS[col], anchor=anc)
        gui.tree.column(col, width=w, minwidth=40, anchor=anc, stretch=(col in ("Title", "Folder")))
    for col in SORTABLE:
        gui.tree.heading(col, command=lambda c=col: sort_by(c))

    tree_scrollbar = ttk.Scrollbar(tree_container, orient="vertical", style="IDM.Vertical.TScrollbar", command=gui.tree.yview)
    gui.tree.configure(yscrollcommand=tree_scrollbar.set)
    update_main_theme(get_setting("theme", "Dark"))
    gui.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # رسالة "الجدول فاضي" بتغطي مكان الصفوف (في الـ History)
    gui.empty_frame = ctk.CTkFrame(tree_container, corner_radius=0, fg_color=("#ffffff", "#14161a"))
    ctk.CTkLabel(gui.empty_frame, text="", image=logo_ctk(64)).place(relx=0.5, rely=0.20, anchor="center")
    gui.empty_title = ctk.CTkLabel(gui.empty_frame, text="", font=ctk.CTkFont(family=UI_FONT, size=18, weight="bold"), text_color=text_c)
    gui.empty_title.place(relx=0.5, rely=0.40, anchor="center")
    gui.empty_sub = ctk.CTkLabel(gui.empty_frame, text="", font=ctk.CTkFont(family=UI_FONT, size=12), text_color=muted_c, justify="center")
    gui.empty_sub.place(relx=0.5, rely=0.54, anchor="center")

    load_history()
    if get_setting("auto_resume_start", False):
        def _auto_resume_paused():
            for _iid, _t in list(tasks.items()):
                if _t["status"] == "paused" and "App closed" in str(_t.get("status_text", "")):
                    resume_task(_iid)
        gui.root.after(1500, _auto_resume_paused)
    gui.tree.bind("<<TreeviewSelect>>", lambda e: (_sel_src.update(v="tree"), gui.cards.select([])) if gui.tree.selection() else None)
    gui.root.after(120, lambda: filter_tasks("All"))
    gui.root.after(250, update_stats)

    def on_ctrl_v(e):
        w = gui.root.focus_get()
        if w is not None and w.winfo_class() in ("Entry", "Text", "TEntry"):
            return                                   # المستخدم بيكتب في خانة البحث: الصق عادي
        add_link_manual()

    gui.root.bind("<Control-v>", on_ctrl_v)
    gui.root.bind("<Control-n>", lambda e: add_link_manual())
    gui.root.bind("<Control-f>", lambda e: search_entry.focus_set())

    # ---------------- طي / فرد التنزيلات النشطة (الكروت) بحركة نزول وطلوع. الجدول ثابت.
    cards_state = {"collapsed": bool(get_setting("cards_collapsed", False)), "h": 0, "busy": False}

    def set_strip_arrow():
        gui.strip_title.configure(image=icon_ctk("caret_up" if cards_state["collapsed"] else "caret_down", 16))

    def apply_cards_state_now():
        if cards_state["collapsed"]:
            cards_body.pack_forget()
        elif not cards_body.winfo_manager():
            cards_body.pack(side=tk.TOP, fill=tk.X)
        set_strip_arrow()

    def toggle_cards():
        if cards_state["busy"]:
            return
        cards_state["collapsed"] = not cards_state["collapsed"]
        save_settings("cards_collapsed", cards_state["collapsed"])
        set_strip_arrow()
        gui.root.update_idletasks()
        if cards_state["collapsed"]:
            start, end = cards_body.winfo_height(), 0
            cards_state["h"] = max(start, 60)
        else:
            if not cards_body.winfo_manager():
                cards_body.pack(side=tk.TOP, fill=tk.X)
            gui.root.update_idletasks()
            start, end = 0, max(cards_state["h"], cards_body.winfo_reqheight(), 60)
        cards_body.pack_propagate(False)
        cards_body.configure(height=max(start, 1))
        cards_state["busy"] = True

        # الحركة مبنية على الزمن مش على عدد خطوات ثابت: كل إطار بيحسب مكانه من الوقت الفعلي، فلو التخطيط اتأخر
        # (الجدول بيتعاد رسمه مع كل تغيير ارتفاع) بنتخطى الإطار بدل ما الحركة تبان بتقطّع أو تتأخر.
        # ومفيش update_idletasks جوه الحركة: Tk بيجمّع كل التغييرات ويرسمها مرة واحدة لكل إطار.
        dur = 0.20 if abs(end - start) > 4 else 0.01
        t0 = time.perf_counter()
        def ease(p):                                          # بداية ونهاية هادية (ease-in-out)
            return 3 * p * p - 2 * p * p * p

        def step():
            p = min(1.0, (time.perf_counter() - t0) / dur)
            try:
                cards_body.configure(height=max(1, int(round(start + (end - start) * ease(p)))))
            except Exception:
                cards_state["busy"] = False
                return
            if p < 1.0:
                gui.root.after(8, step)
            else:
                cards_state["busy"] = False
                cards_body.pack_propagate(True)
                if cards_state["collapsed"]:
                    cards_body.pack_forget()
        step()

    gui.strip_title.configure(command=toggle_cards)
    apply_cards_state_now()

    # ---------------- Context menu
    ctx = {"menu": None}

    def close_ctx(*_):
        m = ctx["menu"]
        ctx["menu"] = None
        if m is not None:
            try:
                m.destroy()
            except Exception:
                pass

    def show_context_menu(e, row=None):
        if row is None:
            row = gui.tree.identify_row(e.y)
        if not row:
            return
        if row not in _selected_ids():
            set_selected([row])
        close_ctx()
        is_dark = ctk.get_appearance_mode() == "Dark"
        primary = ("#1a1a1a", "#f2f3f5")                     # (فاتح, غامق): الكتابة واضحة في الثيمين
        SEP = None
        H_NORM = ("#d6e0f0", "#2f3846")                      # لون الـ hover العادي
        H_WARN = ("#ffe6c7", "#41331f")
        H_RED = ("#fddada", "#43252a")
        red = ("#C62828", "#FF6B6B")
        orange = ("#E65100", "#FFA726")
        yellow = ("#8a6500", "#FFD54F")
        entries = [      # (النص, اسم الأيقونة, لون الكتابة, لون الـ hover, الأمر)
            ("Resume / Retry", "play", primary, H_NORM, resume_selected),
            ("Pause", "pause", yellow, H_WARN, pause_selected),
            ("Download this first", "bolt", yellow, H_WARN, lambda: prioritize_task((_selected_ids() or [None])[0])),
            SEP,
            ("Move up in queue", "caret_up", primary, H_NORM, lambda: move_tasks(_selected_ids(), "up")),
            ("Move down in queue", "caret_down", primary, H_NORM, lambda: move_tasks(_selected_ids(), "down")),
            SEP,
            ("Cancel Download", "remove", red, H_RED, cancel_selected),
            ("Remove from List", "trash_orange", orange, H_WARN, remove_selected),
            SEP,
            ("Open File", "file", primary, H_NORM, open_selected_file),
            ("Open Folder", "folder", primary, H_NORM, open_selected_folder),
            ("Copy link", "link", primary, H_NORM, copy_links_selected),
            ("Properties", "info", primary, H_NORM, open_properties_selected),
            ("Verify checksum...", "check", primary, H_NORM, verify_selected),
            ("Refresh link...", "update", primary, H_NORM, refresh_selected),
            ("Re-download", "redownload", primary, H_NORM, redownload_selected),
            SEP,
            ("Delete File From Device", "trash", red, H_RED, delete_file_from_disk_selected),
        ]
        pick = (lambda c: (c[1] if is_dark else c[0]) if isinstance(c, tuple) else c)     # ألوان ثابتة حسب الثيم
        bg = "#1e2025" if is_dark else "#f6f7f9"
        bd = "#3a404b" if is_dark else "#c5cbd5"
        sep_c = "#343a45" if is_dark else "#d3d7de"
        # القايمة مبنية بمكونات Tk العادية (مش CTk): أبسط وأضمن على ويندوز، والضغطة بتتنفّذ عند رفع الإصبع من الزرار نفسه.
        menu = tk.Toplevel(gui.root)
        ctx["menu"] = menu
        menu.withdraw()                                   # منظهرهاش إلا بعد ما نحسب الارتفاع الحقيقي
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(bg=bd)                             # إطار 1 بكسل
        body = tk.Frame(menu, bg=bg)
        body.pack(fill="both", expand=True, padx=1, pady=1)
        menu._imgs = []
        try:
            s = max(1.0, float(menu.winfo_fpixels("1i")) / 96.0)        # تكبير الشاشة (125% / 150% ...)
        except Exception:
            s = 1.0

        def run(cmd):
            close_ctx()
            gui.root.after(30, cmd)

        def make_item(text, icon_name, tcolor, hcolor, cmd, compact):
            img = ImageTk.PhotoImage(icon_pil(icon_name, int(round(16 * s))))
            menu._imgs.append(img)                        # لازم نحتفظ بالصورة وإلا بتختفي
            lbl = tk.Label(body, text="  " + text, image=img, compound="left", anchor="w", bg=bg, fg=pick(tcolor),
                           font=("Segoe UI", 10, "bold"), padx=int(10 * s), pady=int((2 if compact else 5) * s), cursor="hand2")
            lbl.pack(fill="x", padx=int(6 * s), pady=1)
            hov = pick(hcolor)
            lbl.bind("<Enter>", lambda ev: lbl.configure(bg=hov))
            lbl.bind("<Leave>", lambda ev: lbl.configure(bg=bg))
            lbl.bind("<ButtonRelease-1>", lambda ev: run(cmd))

        def build(compact):
            for child in body.winfo_children():
                child.destroy()
            menu._imgs.clear()
            tk.Frame(body, height=int((3 if compact else 5) * s), bg=bg).pack(fill="x")
            for ent in entries:
                if ent is SEP:
                    tk.Frame(body, height=1, bg=sep_c).pack(fill="x", padx=int(12 * s), pady=int((1 if compact else 3) * s))
                else:
                    make_item(*ent, compact)
            tk.Frame(body, height=int((3 if compact else 5) * s), bg=bg).pack(fill="x")
            menu.update_idletasks()
            return body.winfo_reqheight() + 2             # الارتفاع من المحتوى الفعلي: مفيش مساحة فاضية تحت

        w_px = int(round(236 * s))
        sw, sh = gui.root.winfo_screenwidth(), gui.root.winfo_screenheight()
        margin = int(48 * s)                              # مكان شريط المهام تحت
        h = build(False)
        if e.y_root + h > sh - margin:                    # مفيش مكان تحت المؤشر: نصغّر المسافات قبل ما نفكر نحرّك القايمة
            h = build(True)
        x = max(0, min(e.x_root + 2, sw - w_px - 4))
        y = max(0, min(e.y_root + 2, sh - margin - h))    # بتفتح لتحت دايماً من مكان الضغطة؛ لو الشاشة قصيرة جداً بتتزحزح بالقدر اللازم بس
        menu.geometry(f"{w_px}x{h}+{x}+{y}")
        menu.update_idletasks()
        round_window(menu, w_px, h, int(12 * s), bd)      # حواف منحنية (ويندوز 11: من النظام، ويندوز 10: قصّ للنافذة)
        menu.deiconify()
        menu.lift()

    gui.tree.bind("<Button-3>", lambda e: (_sel_src.update(v="tree"), show_context_menu(e)))
    gui.root.bind("<Button-1>", close_ctx, add="+")
    gui.root.bind("<Escape>", close_ctx, add="+")
    gui.root.bind("<Unmap>", lambda e: close_ctx() if e.widget is gui.root else None, add="+")

    def on_double_click(e, row=None, from_card=False):
        if row is None:
            row = gui.tree.identify_row(e.y)
        if not row or row not in tasks:
            return
        t = tasks[row]
        if t["status"] == "completed" and t.get("file_path") and os.path.exists(t["file_path"]):
            open_path(t["file_path"])
            if from_card:
                dismiss_task(row)
        elif t["status"] in ("paused", "error"):
            resume_task(row)

    gui.tree.bind("<Double-1>", on_double_click)
    gui.tree.bind("<Delete>", lambda e: remove_selected())
    gui.tree.bind("<Control-Up>", lambda e: (move_tasks(_selected_ids(), "up"), "break")[1])
    gui.tree.bind("<Control-Down>", lambda e: (move_tasks(_selected_ids(), "down"), "break")[1])
    gui.tree.bind("<Control-c>", lambda e: (copy_links_selected(), "break")[1])
    gui.tree.bind("<Return>", lambda e: open_selected_file())
    for seq, fn in (("<Delete>", remove_selected), ("<Return>", open_selected_file), ("<Control-c>", copy_links_selected),
                    ("<Control-Up>", lambda: move_tasks(_selected_ids(), "up")),
                    ("<Control-Down>", lambda: move_tasks(_selected_ids(), "down"))):
        gui.cards.cv.bind(seq, lambda e, f=fn: (f(), "break")[1])
    gui.cards.cv.bind("<Control-a>", lambda e: (gui.cards.select(list(gui.cards.ids)), "break")[1])

    # ---------------- Close behaviour
    def on_close():
        save_history()
        mode = get_setting("close_action", "background")
        if mode == "ask":
            ans = messagebox.askyesnocancel("Close", "Keep running in the background?\n\nYes: keep downloading / watching the browser\n"
                                                    "No: exit the program completely", parent=gui.root)
            if ans is None:
                return
            mode = "background" if ans else "exit"
        if mode == "exit":
            force_quit_app()
            return
        with tasks_lock:
            active = any(t["status"] in ACTIVE_STATUSES for t in tasks.values())
        if active:
            gui.root.withdraw()
            if not get_setting("bg_notice_shown"):
                save_settings("bg_notice_shown", True)
                messagebox.showinfo("Still downloading",
                                    "Downloads continue in the background.\nOpen the app again (or click a download in the browser) to bring this window back.")
        else:
            restart_in_background()

    gui.root.protocol("WM_DELETE_WINDOW", on_close)

    # ---------------- Start loops, then accept pending requests
    gui.root.after(10, _ui_pump)

    def heartbeat():
        apply_layout()
        update_stats()
        update_average_progress()
        scheduler_tick()
        usage.tick()
        usage_events()
        prio_tick()
        check_after_all()
        gui.root.after(500, heartbeat)

    gui.root.after(300, heartbeat)
    gui.root.after(1500, clip_tick)
    def _prepare_js():                  # يوتيوب محتاج مشغّل JavaScript: بننزّله تلقائياً في الخلفية (deno أو Node) ونعيد المحاولة لو النت واقع
        try:
            from aerograb.tools import has_js_runtime, install_deno
            for delay in (0, 20, 60, 180, 600, 1800):
                if delay:
                    time.sleep(delay)
                if has_js_runtime(True):
                    return
                ok, _msg = install_deno()
                if ok:
                    return
        except Exception as e:
            log_error("prepare js runtime", e)
    threading.Thread(target=_prepare_js, daemon=True, name="aerograb-js-runtime").start()
    start_background_checks()           # التحديث التلقائي: بيفحص بعد ثواني من فتح البرنامج
    def _sync_extension():              # لو اليوزر ربط الإضافة من مجلد Documents: نحدّثه بآخر ملفات تلقائياً
        try:
            from aerograb.system import prepare_extension_folder
            prepare_extension_folder(create=False)
        except Exception as e:
            log_error("sync extension", e)
    threading.Thread(target=_sync_extension, daemon=True, name="aerograb-ext-sync").start()
    from aerograb.views.extsetup import maybe_show_first_run
    gui.root.after(2500, maybe_show_first_run)      # أول مرة: نافذة بتشرح ربط المتصفح بخطوات سهلة

    with gui_lock:
        gui.gui_running = True
        late = list(pending_urls)
        pending_urls.clear()
        late_batches = list(pending_batches)
        pending_batches.clear()
    for item in (initial_items or []) + late:
        gui.root.after(800, lambda i=item: dispatch_add_item(i))
    for b in late_batches:
        gui.root.after(1000, lambda b=b: show_link_grabber(b["items"], b["referer"], b["cookie"], b["ua"]))
    gui.root.mainloop()


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.views.grabber import force_quit_app  # noqa: E402
from aerograb.engine import (
    _selected_ids,
    cancel_all_tasks,
    cancel_selected,
    clear_list,
    delete_file_from_disk_selected,
    open_selected_file,
    open_selected_folder,
    pause_all_tasks,
    pause_selected,
    remove_selected,
    resume_all_tasks,
    resume_selected,
    resume_task,
    set_selected,
)  # noqa: E402
from aerograb.server import shutdown_server  # noqa: E402
from aerograb.tasks import load_history, save_history  # noqa: E402
from aerograb.views.cards import CardGrid, card_action, dismiss_task, prio_tick, prioritize_task  # noqa: E402
from aerograb.views.grabber import show_link_grabber  # noqa: E402
from aerograb.views.icons import STAT_META, icon_ctk, icon_pil  # noqa: E402
from aerograb.limits import limiter  # noqa: E402
from aerograb.views.mainwin import (
    AFTER_MODES,
    FILTERS,
    HEADINGS,
    SORTABLE,
    STATUS_CHOICES,
    _sel_src,
    apply_layout,
    check_after_all,
    clip_tick,
    copy_links_selected,
    filter_tasks,
    load_icon,
    move_tasks,
    open_properties_selected,
    redownload_selected,
    scheduler_tick,
    set_status_filter,
    sort_by,
    tab_buttons,
    update_main_theme,
)  # noqa: E402
from aerograb.views.popups import add_link_manual, dispatch_add_item  # noqa: E402
from aerograb.views.settings import open_settings_window  # noqa: E402
from aerograb.views.stats import _SearchBox, _overall_key, update_average_progress, update_stats  # noqa: E402
from aerograb.views.thumbs import GREEN, GREEN_H  # noqa: E402
from aerograb.views.winutil import open_path  # noqa: E402
from aerograb.views.updatedlg import start_background_checks  # noqa: E402
