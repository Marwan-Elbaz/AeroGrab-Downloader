# -*- coding: utf-8 -*-
import os
import sys
import re
import subprocess
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from aerograb.common import get_setting, log_error, resource_path, save_settings
from aerograb.config import IS_WINDOWS, UI_FONT
from aerograb.files import extract_urls
from aerograb import usage
from aerograb.fmt import is_direct_file_url, is_valid_url
from aerograb.limits import (
    apply_speed_limit,
    fmt_limit,
    get_default_quality_safe,
    limiter,
    schedule_allows,
    speed_limit_kbps,
)
from aerograb.mediainfo import fmt_hms
from aerograb.state import ACTIVE_STATUSES, tasks, tasks_lock
from aerograb.tools import _NOWIN
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon


# ----------------------------------------------------------------------------- Theme / filters
def update_main_theme(mode):
    ctk.set_appearance_mode(mode)
    save_settings("theme", mode)
    style = ttk.Style()
    style.theme_use("default")
    if mode == "Dark":
        bg, fg, sel_bg, head_bg, head_fg = "#14161a", "#e8eaed", "#245a9c", "#1b1e23", "#9aa4b2"
        c_comp, c_paus, c_canc, c_err = "#5bd69c", "#f2c94c", "#ff8a80", "#ff6b6b"
        head_hover = "#262b33"
    else:
        bg, fg, sel_bg, head_bg, head_fg = "#ffffff", "#1a1d21", "#b9dcff", "#eceff3", "#5b6573"
        c_comp, c_paus, c_canc, c_err = "#0a8a4f", "#9a6a00", "#c62828", "#b71c1c"
        head_hover = "#dde3ea"
    # خط أكبر وصفوف أعرض وترويسة هادية: أسهل في القراءة (ويدعم العربي)
    style.configure("Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=42, borderwidth=0, font=(UI_FONT, 11))
    style.map("Treeview", background=[("selected", sel_bg)], foreground=[("selected", "#ffffff" if mode == "Dark" else "#0b1b2b")])
    style.configure("Treeview.Heading", background=head_bg, foreground=head_fg, relief="flat", borderwidth=0,
                    font=(UI_FONT, 10, "bold"), padding=(10, 9))
    style.map("Treeview.Heading", background=[("active", head_hover)], foreground=[("active", fg)])
    thumb = "#3a3a3a" if mode == "Dark" else "#c9c9c9"
    style.configure("IDM.Vertical.TScrollbar", gripcount=0, background=thumb, darkcolor=thumb, lightcolor=thumb,
                    troughcolor=bg, bordercolor=bg, arrowcolor=fg, relief="flat", arrowsize=12, width=10)
    style.map("IDM.Vertical.TScrollbar", background=[("active", "#2cc985"), ("pressed", "#21a06a")])
    strip_bg = "#101114" if mode == "Dark" else "#eef0f3"
    style.configure("IDM.Horizontal.TScrollbar", gripcount=0, background=thumb, darkcolor=thumb, lightcolor=thumb,
                    troughcolor=strip_bg, bordercolor=strip_bg, arrowcolor=fg, relief="flat", arrowsize=10, width=9)
    style.map("IDM.Horizontal.TScrollbar", background=[("active", "#2cc985"), ("pressed", "#21a06a")])
    if gui.tree is not None:
        gui.tree.tag_configure("completed", foreground=c_comp)
        gui.tree.tag_configure("paused", foreground=c_paus)
        gui.tree.tag_configure("canceled", foreground=c_canc)
        gui.tree.tag_configure("error", foreground=c_err)
        gui.tree.tag_configure("deleted", foreground=c_err)
    try:
        if gui.cards is not None:
            gui.cards.apply_theme()
        _overall_key["k"] = None
        _style_tabs()
        if gui.empty_frame is not None:
            gui.empty_frame.configure(fg_color=bg)
    except Exception:
        pass



FILTERS = [("All", "All"), ("video", "Videos"), ("audio", "Audio"), ("archive", "Archives"),
           ("app", "Programs"), ("doc", "Documents"), ("file", "Other")]

STATUS_CHOICES = {"All status": "all", "In progress": "progress", "Paused": "paused", "Completed": "completed", "Failed": "failed"}

status_filter = {"v": "all"}

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp",
              ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma")

STATUS_RANK = {"downloading": 0, "merging": 0, "starting": 0, "queued": 1, "paused": 2, "error": 3,
               "canceled": 4, "completed": 5, "deleted": 6}

HEADINGS = {"Title": "Name", "Type": "Type", "Size": "Size", "Progress": "%", "Speed": "Speed", "ETA": "ETA",
            "Status": "Status", "Date": "Date", "Folder": "Folder"}

SORTABLE = ("Title", "Type", "Size", "Status", "Date")

tab_buttons = {}

_sel_src = {"v": "tree"}       # آخر مكان المستخدم اختار منه: "tree" أو "cards"

sort_state = {"col": None, "rev": False}

_layout_cache = {"key": None}



def _is_video_task(t):
    ref = str(t.get("file_path") or "").lower()
    url = t["url"].lower()
    return (ref.endswith(VIDEO_EXTS) or "youtube.com" in url or "youtu.be" in url
            or url.split("?")[0].endswith(VIDEO_EXTS))



def _matches(t, cat):
    return cat == "All" or task_kind_c(t)[0] == cat



def _status_ok(t):
    f, st = status_filter["v"], t["status"]
    if f == "all":
        return True
    if f == "progress":
        return st in ACTIVE_STATUSES
    if f == "paused":
        return st == "paused"
    if f == "completed":
        return st == "completed"
    return st in ("error", "canceled", "deleted")            # failed



def _style_tabs():
    idle = dict(fg_color=("#eef0f3", "#181a1f"), text_color=("#444444", "#a8a8a8"), hover_color=("#e0e3e8", "#252932"),
                border_color=("#d5d9df", "#2b2f37"))
    on = dict(fg_color=GREEN, text_color="white", hover_color=GREEN_H, border_color=GREEN)
    for name, btn in tab_buttons.items():
        try:
            btn.configure(**(on if name == gui.current_filter else idle))
        except Exception:
            pass



def set_status_filter(label):
    status_filter["v"] = STATUS_CHOICES.get(label, "all")
    apply_layout(force=True)



def filter_tasks(category=None):
    if category:
        gui.current_filter = category
    apply_layout(force=True)



def _update_empty_state(total, shown):
    if gui.empty_frame is None:
        return
    if shown:
        gui.empty_frame.place_forget()
        return
    if total == 0:
        title = "No downloads yet"
        sub = "Click  ➕ Add link,  press Ctrl+V to paste a link,\nor use the download button on YouTube / any file in your browser."
    else:
        title = "Nothing matches this filter"
        sub = "Try another file type / status, or clear the search box."
    gui.empty_title.configure(text=title)
    gui.empty_sub.configure(text=sub)
    gui.empty_frame.place(x=0, y=40, relwidth=1.0, relheight=1.0)     # الزيادة بره الإطار بتتقص تلقائياً



def apply_layout(force=False):
    """الجدول (فوق) بيتفلتر بالتصنيف والحالة والبحث، وصف الكروت (تحت) بيعرض التحميلات الشغالة."""
    if gui.tree is None:
        return
    q = gui.search_var.get().strip().lower() if gui.search_var is not None else ""
    with tasks_lock:
        snap = [(idx, iid, t["title"], t["url"], t["status"], t["date"], not t.get("dismissed"), t.get("prio", idx),
                 _matches(t, gui.current_filter) and _status_ok(t), KIND_LABEL.get(task_kind_c(t)[0], "Other"),
                 _parse_size(t["size"]))
                for idx, (iid, t) in enumerate(tasks.items())]
    total = len(snap)
    rows = [r for r in snap if r[8] and (not q or q in str(r[2]).lower() or q in r[3].lower())]
    col, rev = sort_state["col"], sort_state["rev"]
    if col is None:
        rows.sort(key=lambda r: (r[7], r[0]))              # ترتيب الطابور (الأولوية)
    elif col == "Title":
        rows.sort(key=lambda r: str(r[2]).lower(), reverse=rev)
    elif col == "Type":
        rows.sort(key=lambda r: (r[9], r[0]), reverse=rev)
    elif col == "Size":
        rows.sort(key=lambda r: (r[10], r[0]), reverse=rev)
    elif col == "Status":
        rows.sort(key=lambda r: (STATUS_RANK.get(r[4], 9), r[0]), reverse=rev)
    elif col == "Date":
        rows.sort(key=lambda r: (r[5], r[0]), reverse=rev)
    visible = tuple(r[1] for r in rows)
    strip = tuple(r[1] for r in sorted((r for r in snap if r[6]), key=lambda r: (r[7], r[0])))
    titles = tuple(r[2] for r in rows) if col == "Title" else ()
    key = (visible, strip, titles, gui.current_filter, status_filter["v"], q, col, rev, total)
    if not force and key == _layout_cache["key"]:
        return
    _layout_cache["key"] = key
    vis = set(visible)
    for r in snap:
        if r[1] not in vis and gui.tree.exists(r[1]):
            gui.tree.detach(r[1])
    for iid in visible:
        if gui.tree.exists(iid):
            gui.tree.reattach(iid, "", "end")
    if gui.cards is not None:
        gui.cards.set_items(strip)
    _style_tabs()
    _update_empty_state(total, len(visible))



def sort_by(col):
    st = sort_state
    if st["col"] == col:
        if st["rev"]:
            st["col"], st["rev"] = None, False      # الضغطة التالتة بتلغي الترتيب
        else:
            st["rev"] = True
    else:
        st["col"], st["rev"] = col, False
    for c, label in HEADINGS.items():
        arrow = (" ▼" if st["rev"] else " ▲") if st["col"] == c else ""
        gui.tree.heading(c, text=label + arrow)
    apply_layout(force=True)



def open_save_folder():
    d = gui.download_path_var.get()
    if d and os.path.isdir(d):
        open_path(d)
    else:
        messagebox.showinfo("Not found", "The save folder does not exist yet.")



# ----------------------------------------------------------------------------- Settings window
_icon_cache = {}



def load_icon(filename, size=(20, 20)):
    key = (filename, size)
    if key in _icon_cache:
        return _icon_cache[key]
    try:
        img = Image.open(resource_path(filename))
        res = ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        res = None
    _icon_cache[key] = res
    return res



# ----------------------------------------------------------------------------- IDM-style extras
_clip = {"last": None}

SPEED_CHOICES = {"Unlimited": 0, "128 KB/s": 128, "256 KB/s": 256, "512 KB/s": 512, "1 MB/s": 1024,
                 "2 MB/s": 2048, "5 MB/s": 5120, "10 MB/s": 10240}

AFTER_MODES = ["Do nothing", "Exit app", "Sleep", "Hibernate", "Shut down", "Lock screen"]

_after = {"seen": False, "dialog": None}

POWER_RUNNER = [None]          # الاختبارات بتبدّلها بدالة وهمية بدل ما نطفّي الجهاز فعلاً



def _selected_tasks():
    return [(i, tasks[i]) for i in _selected_ids()]



def _parse_speed_label(label):
    if label in SPEED_CHOICES:
        return SPEED_CHOICES[label]
    m = re.fullmatch(r"([\d.]+)\s*(KB|MB)/s", label or "")
    return int(float(m.group(1)) * (1024 if m.group(2) == "MB" else 1)) if m else 0



def refresh_speed_menu():
    if gui.speed_menu is None:
        return
    vals = list(SPEED_CHOICES.keys())
    cur = fmt_limit(speed_limit_kbps())
    if cur not in vals:
        vals.append(cur)
    gui.speed_menu.configure(values=vals)
    gui.speed_var.set(cur)



def set_speed_limit(kbps):
    save_settings("speed_limit_kbps", max(0, int(kbps)))
    apply_speed_limit()
    refresh_speed_menu()



# ---- ترتيب الطابور
def move_tasks(ids, how):
    with tasks_lock:
        order = sorted(tasks, key=lambda i: tasks[i].get("prio", 0))
        sel = {i for i in ids if i in tasks}
        if not sel:
            return
        if how in ("top", "bottom"):
            chosen = [i for i in order if i in sel]
            pr = [tasks[i].get("prio", 0) for i in order]
            base = (min(pr) - len(chosen) - 1) if how == "top" else (max(pr) + 1)
            for k, i in enumerate(chosen):
                tasks[i]["prio"] = base + k
        else:
            seq = order if how == "up" else list(reversed(order))
            for idx in range(len(seq)):
                i = seq[idx]
                if i in sel and idx > 0 and seq[idx - 1] not in sel:
                    j = seq[idx - 1]
                    tasks[i]["prio"], tasks[j]["prio"] = tasks[j]["prio"], tasks[i]["prio"]
                    seq[idx - 1], seq[idx] = i, j
    limiter.poke()
    save_history()
    apply_layout(force=True)



def copy_links_selected():
    urls = [t["url"] for _, t in _selected_tasks()]
    if not urls:
        return
    text = "\n".join(urls)
    gui.root.clipboard_clear()
    gui.root.clipboard_append(text)
    _clip["last"] = text.strip()           # عشان مراقب الكليبورد ميعتبرهاش لينك جديد



def redownload_selected():
    for iid, t in _selected_tasks():
        if t["status"] in ACTIVE_STATUSES:
            continue
        extra = {k: t[k] for k in ("clip_start", "clip_end", "clip_precise", "name_prefix") if t.get(k) is not None}
        start_single_download(t["url"], t["quality"], save_path=t["save_path"], referer=t.get("referer", ""),
                              direct=t.get("direct", False), cookie=t.get("cookie", ""), ua=t.get("ua", ""), extra=extra)



def open_properties_selected():
    sel = _selected_tasks()
    if not sel:
        return
    iid, t = sel[0]
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    win.title("Properties")
    win.geometry("560x430")
    win.attributes("-topmost", True)
    win.after(500, lambda: win.attributes("-topmost", False))
    rows = [("Name", t["title"]), ("Status", t["status_text"]), ("Size", t["size"]), ("Added", t["date"]),
            ("Quality", t["quality"]), ("Saved to", t.get("file_path") or t.get("save_path") or "-"),
            ("Referer", t.get("referer") or "-")]
    if t.get("clip_start") is not None or t.get("clip_end") is not None:
        rows.insert(5, ("Part", f"{fmt_hms(t.get('clip_start') or 0)} → {fmt_hms(t['clip_end']) if t.get('clip_end') is not None else 'end'}"))
    grid = ctk.CTkFrame(win, fg_color="transparent")
    grid.pack(fill=tk.X, padx=18, pady=(16, 6))
    for r, (k, v) in enumerate(rows):
        ctk.CTkLabel(grid, text=k, font=(UI_FONT, 12, "bold"), text_color=("#666", "#9a9a9a"), anchor="w", width=80).grid(row=r, column=0, sticky="nw", pady=3)
        ctk.CTkLabel(grid, text=_shorten(v, 70), font=(UI_FONT, 12), anchor="w", wraplength=400, justify="left").grid(row=r, column=1, sticky="w", padx=8, pady=3)
    ctk.CTkLabel(win, text="Link", font=(UI_FONT, 12, "bold"), text_color=("#666", "#9a9a9a"), anchor="w").pack(fill=tk.X, padx=18)
    box = ctk.CTkTextbox(win, height=80, font=(UI_FONT, 11), wrap="char")
    box.pack(fill=tk.X, padx=18, pady=(2, 10))
    box.insert("1.0", t["url"])
    box.configure(state="disabled")
    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(pady=6)
    ctk.CTkButton(row, text="🔗 Copy link", width=120, fg_color=GREEN, hover_color=GREEN_H,
                  command=lambda: (copy_links_selected(), win.lift())).pack(side=tk.LEFT, padx=6)
    ctk.CTkButton(row, text="📁 Open folder", width=120, fg_color="gray40",
                  command=lambda: reveal_in_folder(t.get("file_path"), t.get("save_path"))).pack(side=tk.LEFT, padx=6)
    ctk.CTkButton(row, text="Close", width=90, fg_color="gray30", command=win.destroy).pack(side=tk.LEFT, padx=6)



# ---- تصدير / استيراد الروابط
def export_links():
    with tasks_lock:
        urls = [t["url"] for t in sorted(tasks.values(), key=lambda t: t.get("prio", 0))]
    if not urls:
        messagebox.showinfo("Export", "The list is empty.")
        return
    path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", "*.txt")], initialfile="idm_links.txt")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(urls))
        messagebox.showinfo("Export", f"Saved {len(urls)} links.")
    except Exception as e:
        messagebox.showerror("Export", f"Could not save:\n{e}")



def read_links_from_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return extract_urls(f.read())



# ---- إشعار اكتمال التحميل
def play_done_sound():
    try:
        if IS_WINDOWS:
            import winsound
            custom = (get_setting("sound_file", "") or "").strip()
            if custom and os.path.isfile(custom):                       # ملف صوت (wav) اختاره المستخدم
                winsound.PlaySound(custom, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        else:
            gui.root.bell()
    except Exception:
        pass



_toast = {"win": None}



def show_toast(item_id):
    t = tasks.get(item_id)
    if not t:
        return
    try:
        if _toast["win"] is not None:
            try:
                _toast["win"].destroy()
            except Exception:
                pass
        win = ctk.CTkToplevel(gui.root)
        apply_window_icon(win)
        _toast["win"] = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        w, h = 390, 108
        win.geometry(f"{w}x{h}+{gui.root.winfo_screenwidth() - w - 18}+{gui.root.winfo_screenheight() - h - 74}")
        kind, ext = task_kind(t)
        url = t.get("thumb")
        pil = _thumb_mem[url] if (url and _thumb_mem.get(url)) else make_type_icon(kind, ext)
        img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(96, 54))
        frame = ctk.CTkFrame(win, corner_radius=12, border_width=2, border_color=GREEN)
        frame.pack(fill="both", expand=True)
        pic = ctk.CTkLabel(frame, image=img, text="")
        pic.image = img
        pic.pack(side="left", padx=(12, 8), pady=12)
        col = ctk.CTkFrame(frame, fg_color="transparent")
        col.pack(side="left", fill="both", expand=True, pady=8, padx=(0, 6))
        ctk.CTkLabel(col, text="✔  Download complete", font=(UI_FONT, 12, "bold"), text_color=GREEN, anchor="w").pack(fill="x")
        ctk.CTkLabel(col, text=_shorten(t["title"], 38), font=(UI_FONT, 11), anchor="w").pack(fill="x")
        fp = t.get("file_path")
        row = ctk.CTkFrame(col, fg_color="transparent")
        row.pack(anchor="w", pady=(6, 0))

        def close(*_):
            try:
                win.destroy()
            except Exception:
                pass

        ctk.CTkButton(row, text="Open", width=64, height=26, font=(UI_FONT, 11), fg_color=GREEN, hover_color=GREEN_H,
                      command=lambda: (fp and os.path.exists(fp) and open_path(fp), close())).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="Folder", width=64, height=26, font=(UI_FONT, 11), fg_color="gray40",
                      command=lambda: (reveal_in_folder(fp, t.get("save_path")), close())).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="✕", width=30, height=26, font=(UI_FONT, 11), fg_color="gray30", command=close).pack(side="left")
        win.after(9000, close)
    except Exception as e:
        log_error("show_toast", e)



def on_task_completed(item_id):
    t = tasks.get(item_id)
    if not t:
        return
    if get_setting("notify_sound", True):
        play_done_sound()
    if get_setting("notify_toast", True):
        show_toast(item_id)
    mode, fp = get_setting("open_when_done", "none"), t.get("file_path")
    if mode == "file" and fp and os.path.exists(fp):
        open_path(fp)
    elif mode == "folder" and fp:
        reveal_in_folder(fp, t.get("save_path"))



# ---- "لما كل التحميلات تخلص": إغلاق / نوم / قفل ...
def _power_cmd(mode):
    if IS_WINDOWS:
        return {"Sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "Hibernate": ["shutdown", "/h"],
                "Shut down": ["shutdown", "/s", "/t", "0"], "Lock screen": ["rundll32.exe", "user32.dll,LockWorkStation"]}.get(mode)
    if sys.platform == "darwin":
        return {"Sleep": ["pmset", "sleepnow"], "Lock screen": ["pmset", "displaysleepnow"],
                "Shut down": ["osascript", "-e", 'tell app "System Events" to shut down']}.get(mode)
    return {"Sleep": ["systemctl", "suspend"], "Hibernate": ["systemctl", "hibernate"],
            "Shut down": ["systemctl", "poweroff"], "Lock screen": ["loginctl", "lock-session"]}.get(mode)



def _do_power(mode):
    if mode == "Exit app":
        save_history()
        os._exit(0)
    cmd = _power_cmd(mode)
    if cmd:
        subprocess.Popen(cmd, creationflags=_NOWIN)



def run_power_action(mode):
    (POWER_RUNNER[0] or _do_power)(mode)



def start_after_countdown(mode, seconds=60):
    seconds = 10 if mode == "Exit app" else seconds
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    win.title("Downloads finished")
    win.geometry("430x190")
    win.attributes("-topmost", True)
    ctk.CTkLabel(win, text="✔  All downloads are finished", font=(UI_FONT, 15, "bold")).pack(pady=(20, 6))
    lbl = ctk.CTkLabel(win, text="", font=(UI_FONT, 14), text_color=GREEN)
    lbl.pack(pady=4)
    state = {"left": seconds, "stop": False}
    _after["dialog"] = win

    def cancel():
        state["stop"] = True
        _after["dialog"] = None
        gui.after_var.set("Do nothing")
        try:
            win.destroy()
        except Exception:
            pass

    ctk.CTkButton(win, text="Cancel", width=120, fg_color="#e53935", hover_color="#c62828", command=cancel).pack(pady=12)
    win.protocol("WM_DELETE_WINDOW", cancel)

    def tick():
        if state["stop"]:
            return
        if state["left"] <= 0:
            _after["dialog"] = None
            gui.after_var.set("Do nothing")
            try:
                win.destroy()
            except Exception:
                pass
            run_power_action(mode)
            return
        lbl.configure(text=f"{mode} in {state['left']} s")
        state["left"] -= 1
        win.after(1000, tick)

    tick()



def check_after_all():
    try:
        mode = gui.after_var.get()
    except Exception:
        return
    if mode == "Do nothing":
        _after["seen"] = False
        return
    with tasks_lock:
        active = any(t["status"] in ACTIVE_STATUSES for t in tasks.values())
        busy = active or any(t["status"] == "paused" for t in tasks.values())
    if active:
        _after["seen"] = True
    if not busy and _after["seen"] and _after["dialog"] is None:
        _after["seen"] = False
        start_after_countdown(mode)



# ---- الجدولة: بتوقف/تكمّل التحميلات تلقائياً حسب الوقت
def scheduler_tick():
    allowed = schedule_allows() and usage.allows()      # الجدولة + حد الاستهلاك
    if not allowed:
        for iid in list(tasks):
            with tasks_lock:
                t = tasks.get(iid)
                running = bool(t) and t["status"] in ("starting", "downloading")
                if running:
                    t["auto_paused"] = True
            if running:
                pause_task(iid)
    else:
        for iid in list(tasks):
            with tasks_lock:
                t = tasks.get(iid)
                flag = bool(t) and t.get("auto_paused")
                is_paused = bool(t) and t["status"] == "paused"
                if flag:
                    t["auto_paused"] = False
            if flag and is_paused:
                resume_task(iid)



# ---- مراقبة الكليبورد
def _looks_downloadable(url):
    return is_direct_file_url(url) or bool(youtube_thumb_url(url))



def clip_tick():
    try:
        try:
            txt = (gui.root.clipboard_get() or "").strip()
        except Exception:
            txt = ""
        if txt and txt != _clip["last"]:
            monitor = get_setting("clip_monitor", False)
            first_seen = _clip["last"] is None
            _clip["last"] = txt
            if monitor and not first_seen and "\n" not in txt and is_valid_url(txt) and _looks_downloadable(txt):
                with tasks_lock:
                    known = any(t["url"] == txt for t in tasks.values())
                if not known:
                    show_quick_confirm_popup(txt, get_default_quality_safe(), "", is_direct_file_url(txt))
    except Exception as e:
        log_error("clip_tick", e)
    try:
        gui.root.after(1000, clip_tick)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.engine import _selected_ids, pause_task, resume_task, start_single_download  # noqa: E402
from aerograb.tasks import KIND_LABEL, save_history, task_kind, task_kind_c, youtube_thumb_url  # noqa: E402
from aerograb.views.icons import _parse_size  # noqa: E402
from aerograb.views.popups import show_quick_confirm_popup  # noqa: E402
from aerograb.views.stats import _overall_key, _shorten  # noqa: E402
from aerograb.views.thumbs import GREEN, GREEN_H, _thumb_mem, make_type_icon  # noqa: E402
from aerograb.views.winutil import open_path, reveal_in_folder  # noqa: E402
