# -*- coding: utf-8 -*-
import os
import urllib.request, urllib.parse, urllib.error
import customtkinter as ctk
from tkinter import filedialog
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from aerograb.config import UI_FONT
from aerograb.files import cookie_for
from aerograb.fmt import EXT_KIND
from aerograb.limits import get_default_quality_safe
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon


# ---- Link Grabber: كل روابط الصفحة (من الإضافة)
def _link_kind(url):
    ext = os.path.splitext(urllib.parse.unquote(urllib.parse.urlparse(url).path))[1].lstrip(".").lower()
    return EXT_KIND.get(ext) or "other", ext



GRAB_FILTERS = {"Files": None, "All": "all", "Video": "video", "Audio": "audio", "Archives": "archive",
                "Programs": "app", "Docs": "doc", "Other": "other"}



def show_link_grabber(items, referer="", cookie="", ua=""):
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    win.title("Link Grabber")
    win.geometry("940x660")
    win.attributes("-topmost", True)
    win.after(700, lambda: win.attributes("-topmost", False))
    rows = []
    for it in items:
        kind, ext = _link_kind(it["url"])
        pu = urllib.parse.urlparse(it["url"])
        name = urllib.parse.unquote(os.path.basename(pu.path)) or it.get("text") or pu.netloc
        rows.append({"url": it["url"], "name": name[:140], "kind": kind, "ext": ext})
    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill=tk.X, padx=14, pady=(12, 4))
    ctk.CTkLabel(head, text="🔗  Link Grabber", font=(UI_FONT, 16, "bold")).pack(side=tk.LEFT)
    info = ctk.CTkLabel(head, text="", font=(UI_FONT, 11), text_color=("#666", "#9a9a9a"))
    info.pack(side=tk.RIGHT)
    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill=tk.X, padx=14, pady=4)
    has_files = any(r["kind"] != "other" for r in rows)
    seg = ctk.CTkSegmentedButton(bar, values=list(GRAB_FILTERS.keys()), command=lambda v: refilter())
    seg.pack(side=tk.LEFT)
    seg.set("Files" if has_files else "All")
    search = ctk.CTkEntry(bar, placeholder_text="🔍  Filter...", width=220, height=30)
    search.pack(side=tk.RIGHT)
    holder = ctk.CTkFrame(win)
    holder.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)
    gtree = ttk.Treeview(holder, columns=("Name", "Type", "URL"), show="headings", selectmode="extended")
    for col, w, st in (("Name", 300, True), ("Type", 70, False), ("URL", 480, True)):
        gtree.heading(col, text=col)
        gtree.column(col, width=w, stretch=st, anchor=tk.W)
    sb = ttk.Scrollbar(holder, orient="vertical", style="IDM.Vertical.TScrollbar", command=gtree.yview)
    gtree.configure(yscrollcommand=sb.set)
    gtree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    by_iid = {}

    def refilter(*_):
        mode = GRAB_FILTERS.get(seg.get())
        q = search.get().strip().lower()
        for i in gtree.get_children():
            gtree.delete(i)
        by_iid.clear()
        shown = 0
        for r in rows:
            if mode is None and r["kind"] == "other":
                continue
            if mode not in (None, "all") and r["kind"] != mode:
                continue
            if q and q not in (r["name"] + " " + r["url"]).lower():
                continue
            iid = gtree.insert("", "end", values=(r["name"], r["ext"].upper() or "-", r["url"]))
            by_iid[iid] = r
            shown += 1
            if shown >= 3000:
                break
        info.configure(text=f"{shown} shown  /  {len(rows)} found")
        update_sel()

    def update_sel(*_):
        sel_lbl.configure(text=f"Selected: {len(gtree.selection())}")
        dl_btn.configure(text=f"⬇  Download selected ({len(gtree.selection())})")

    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill=tk.X, padx=14, pady=(2, 4))
    ctk.CTkButton(foot, text="Select all", width=90, height=30, fg_color="gray40",
                  command=lambda: (gtree.selection_set(gtree.get_children()), update_sel())).pack(side=tk.LEFT, padx=(0, 6))
    ctk.CTkButton(foot, text="Select none", width=96, height=30, fg_color="gray40",
                  command=lambda: (gtree.selection_remove(gtree.selection()), update_sel())).pack(side=tk.LEFT)
    sel_lbl = ctk.CTkLabel(foot, text="Selected: 0", font=(UI_FONT, 12, "bold"))
    sel_lbl.pack(side=tk.LEFT, padx=14)
    folder_var = ctk.StringVar(value=gui.download_path_var.get())

    def pick_folder():
        d = filedialog.askdirectory(parent=win)
        if d:
            folder_var.set(d)

    ctk.CTkButton(foot, text="📁", width=40, height=30, fg_color="#FF9800", hover_color="#F57C00", command=pick_folder).pack(side=tk.RIGHT)
    ctk.CTkEntry(foot, textvariable=folder_var, width=300, height=30, state="disabled").pack(side=tk.RIGHT, padx=6)
    ctk.CTkLabel(foot, text="Save to", font=(UI_FONT, 12), text_color=("#666", "#9a9a9a")).pack(side=tk.RIGHT)
    dl_btn = ctk.CTkButton(win, text="⬇  Download selected (0)", height=38, font=(UI_FONT, 13, "bold"),
                           fg_color=GREEN, hover_color=GREEN_H)
    dl_btn.pack(fill=tk.X, padx=14, pady=(2, 14))

    def do_download():
        sel = gtree.selection()
        if not sel:
            messagebox.showinfo("Link Grabber", "Select at least one link first.", parent=win)
            return
        chosen = [by_iid[i] for i in sel if i in by_iid]
        folder = folder_var.get()
        win.destroy()
        _batch["on"] = True
        try:
            for r in chosen:
                start_single_download(r["url"], get_default_quality_safe(), save_path=folder, referer=referer,
                                      direct=(r["kind"] != "other"), cookie=cookie_for(r["url"], referer, cookie), ua=ua)
        finally:
            _batch["on"] = False
            save_history()
            filter_tasks(gui.current_filter)

    dl_btn.configure(command=do_download)
    win._idm = {"tree": gtree, "button": dl_btn, "seg": seg, "search": search, "refilter": refilter}
    gtree.bind("<<TreeviewSelect>>", update_sel)
    search.bind("<KeyRelease>", refilter)
    gtree.bind("<Control-a>", lambda e: (gtree.selection_set(gtree.get_children()), update_sel(), "break")[2])
    refilter()



def force_quit_app():
    if messagebox.askyesno("Confirm Exit", "Are you sure you want to close the application completely?"):
        save_history()
        os._exit(0)



_settings_win = [None]

CAT_ORDER = ("video", "audio", "archive", "app", "doc", "file")

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.engine import start_single_download  # noqa: E402
from aerograb.tasks import _batch, save_history  # noqa: E402
from aerograb.views.mainwin import filter_tasks  # noqa: E402
from aerograb.views.thumbs import GREEN, GREEN_H  # noqa: E402
