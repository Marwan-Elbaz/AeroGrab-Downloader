# -*- coding: utf-8 -*-
import os
import urllib.request, urllib.parse, urllib.error
import threading
import re
from PIL import Image
from PIL import ImageDraw
from PIL import ImageOps
import customtkinter as ctk
from tkinter import filedialog
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from aerograb.common import log_error, save_settings
from aerograb.views.winutil import fit_geometry
from aerograb.config import UI_FONT
from aerograb.files import expand_patterns
from aerograb.fmt import QUALITY_MAP, STANDARD_HEIGHTS, fmt_bytes, is_valid_url
from aerograb.limits import get_default_quality_safe
from aerograb.mediainfo import (
    estimate_size,
    fetch_media_details,
    fetch_playlist,
    fmt_hms,
    is_playlist_page,
    parse_time,
    playlist_url_of,
    selected_size_ex,
    youtube_list_id,
)
from aerograb.state import ui
from aerograb.tools import find_ffmpeg
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon


# ----------------------------------------------------------------------------- Popups
# ----------------------------------------------------------------------------- نوافذ التنزيل (شكل البطاقات)
WIN_BG = ("#eef0f3", "#101114")

CARD_BG = ("#ffffff", "#17191e")

CARD_BORDER = ("#dde1e6", "#262a31")

CHIP_BG = ("#e8ebef", "#232730")

MUTED = ("#6b7480", "#98a2ad")

_open_popups = {}



def _win_scale(win):
    try:
        return float(win._get_window_scaling())
    except Exception:
        return 1.0



def _fit_window(win, w, min_h=240):
    """بيظبط حجم النافذة على المحتوى وبيوسّطها في الشاشة."""
    try:
        win.update_idletasks()
        s = _win_scale(win)
        h = max(min_h, int(win.winfo_reqheight() / s) + 4)
        h = min(h, int(win.winfo_screenheight() / s) - 90)
        win.geometry(f"{w}x{h}")
        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() - int(w * s)) // 2)
        y = max(0, (win.winfo_screenheight() - int(h * s)) // 2 - 20)
        win.geometry(f"+{x}+{y}")
    except Exception as e:
        log_error("_fit_window", e)



def _chip(parent, text, color=None, icon=None):
    f = ctk.CTkFrame(parent, corner_radius=11, fg_color=CHIP_BG)
    f.lbl = ctk.CTkLabel(f, text=text, font=(UI_FONT, 11, "bold"), text_color=color or MUTED,
                         image=icon_ctk(icon, 14) if icon else None, compound="left")
    f.lbl.pack(padx=9, pady=2)
    return f



def _decorate_thumb(pil, size, duration_text=""):
    """صورة بحواف دايرية + شارة المدة."""
    img = ImageOps.fit(pil.convert("RGB"), size).convert("RGBA")
    if duration_text:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        f = _font(16)
        tw = int(od.textlength(duration_text, font=f))
        x1, y1 = size[0] - 10, size[1] - 10
        od.rounded_rectangle((x1 - tw - 16, y1 - 26, x1, y1), radius=8, fill=(10, 12, 16, 220))
        od.text((x1 - tw / 2 - 8, y1 - 13), duration_text, font=f, fill="white", anchor="mm")
        img = Image.alpha_composite(img, ov)
    return _round_corners(img, 18)



def show_quick_confirm_popup(url, quality, referer="", direct=False, cookie="", ua="", clip=False):
    old = _open_popups.get(url)
    if old is not None:
        try:
            if old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:
            pass
    W = 440
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    _open_popups[url] = win
    win.title("Download")
    win.configure(fg_color=WIN_BG)
    win.attributes("-topmost", True)
    win.geometry(f"{W}x200")
    win.bind("<Destroy>", lambda e: _open_popups.pop(url, None) if e.widget is win else None)
    win.bind("<Escape>", lambda e: win.destroy())
    card = ctk.CTkFrame(win, corner_radius=16, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER)
    card.pack(fill="both", expand=True, padx=10, pady=10)
    loading = ctk.CTkFrame(card, fg_color="transparent")
    loading.pack(expand=True, pady=34)
    ctk.CTkLabel(loading, text="Fetching video info…", font=(UI_FONT, 13, "bold"), text_color=GREEN,
                 image=icon_ctk("download", 18), compound="left").pack()
    bar = ctk.CTkProgressBar(loading, mode="indeterminate", width=240, progress_color=GREEN)
    bar.pack(pady=(10, 0))
    bar.start()
    _fit_window(win, W, 200)
    current_dl_path = ctk.StringVar(value=gui.download_path_var.get())

    def alive():
        try:
            return bool(win.winfo_exists())
        except Exception:
            return False

    def build_ui(d):
        if not alive():
            return
        try:
            bar.stop()
        except Exception:
            pass
        loading.destroy()
        media = not d["direct"]
        dur = d.get("duration")
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=12)

        # --- الصورة
        kind, ext = _link_kind(url) if not media else ("video", "")
        pil = d.get("pil") or make_type_icon("video" if media else (kind if kind != "other" else "file"), ext.upper()[:5])
        thumb = _decorate_thumb(pil, (384, 216), fmt_hms(dur) if dur else "")
        ctk.CTkLabel(body, image=ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(384, 216)), text="").pack()

        # --- العنوان + القناة + الشارات
        ctk.CTkLabel(body, text=d["title"] or url, font=(UI_FONT, 14, "bold"), wraplength=380, justify="left",
                     anchor="w").pack(fill="x", pady=(9, 1))
        if d.get("uploader"):
            ctk.CTkLabel(body, text=f"👤 {d['uploader']}", font=(UI_FONT, 11), text_color=MUTED, anchor="w").pack(fill="x")
        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.pack(fill="x", pady=(6, 2))
        size_chip = _chip(chips, d["size"] or "Size unknown", "#2cc985" if d["size"] else None, "drive")
        size_chip.pack(side="left")
        if dur:
            _chip(chips, fmt_hms(dur), None, "hourglass").pack(side="left", padx=5)
        if media:
            _chip(chips, "Video").pack(side="left")
        else:
            _chip(chips, urllib.parse.urlparse(url).netloc[:28] or "File", None, "link").pack(side="left", padx=5)

        q_var = ctk.StringVar(value=quality)

        def clip_range():
            """(start, end) أو None لو الفيديو كله، أو 'error'."""
            if not clip_on.get():
                return None
            s_txt, e_txt = start_e.get().strip(), end_e.get().strip()
            s = parse_time(s_txt) if s_txt else 0.0
            e = parse_time(e_txt) if e_txt else (float(dur) if dur else None)
            if s is None or (e_txt and e is None):
                return "error"
            if dur:
                e = min(e, float(dur)) if e is not None else float(dur)
            if e is not None and e <= s:
                return "error"
            if s == 0 and (e is None or (dur and e >= float(dur) - 0.5)):
                return None
            return (s, e)

        pending = set()

        def size_for(q):
            """حجم الجودة دي: None = لسه بيتحسب في الخلفية (مش بنعطّل الواجهة)."""
            sz = d.setdefault("sizes", {})
            if q in sz:
                return sz[q]
            if q not in pending:
                pending.add(q)

                def work():
                    b, e = selected_size_ex(d["info"], q) if d.get("info") else (0, False)
                    if not b:
                        b, e = estimate_size(d["fmts"], q), False

                    def done():
                        pending.discard(q)
                        sz[q] = b
                        d.setdefault("exact", {})[q] = e
                        if alive() and q_var.get() == q:
                            refresh_size()
                    ui(done)
                threading.Thread(target=work, daemon=True).start()
            return None

        def refresh_size(*_):
            if not media:
                return
            q = q_var.get()
            b = size_for(q)
            exact = bool(d.get("exact", {}).get(q))
            r = clip_range() if clip_on.get() else None
            if b is None:
                size_chip.lbl.configure(text="Calculating…", text_color=MUTED)
            elif b and isinstance(r, tuple) and dur:
                b = int(b * max(0.0, (r[1] - r[0])) / float(dur))
                size_chip.lbl.configure(text=f"~{fmt_bytes(b)} (part)", text_color="#2cc985")
            elif b:
                size_chip.lbl.configure(text=("" if exact else "~") + fmt_bytes(b), text_color="#2cc985")
            else:
                size_chip.lbl.configure(text="Size unknown", text_color=MUTED)
            if isinstance(r, tuple):
                clip_info.configure(text=f"{fmt_hms(r[0])}  →  {fmt_hms(r[1])}   ({fmt_hms(r[1] - r[0])})",
                                    text_color=("#117a4d", "#2cc985"))
            elif r == "error":
                clip_info.configure(text="Check the times (e.g. 90 · 1:30 · 01:02:03)", text_color="#e06666")
            else:
                clip_info.configure(text="Whole video", text_color=MUTED)

        clip_on = ctk.BooleanVar(value=False)
        start_e = end_e = clip_info = None
        if media:
            qvals = d["qualities"] or list(QUALITY_MAP.keys())
            want = STANDARD_HEIGHTS.get(quality, 1080) if quality != "Audio Only" else 0
            if quality in qvals:
                q_var.set(quality)
            else:
                q_var.set(next((v for v in qvals if v in STANDARD_HEIGHTS and STANDARD_HEIGHTS[v] <= want), qvals[0]))
            qrow = ctk.CTkFrame(body, fg_color="transparent")
            qrow.pack(fill="x", pady=(6, 0))
            ctk.CTkLabel(qrow, text="Quality", font=(UI_FONT, 12, "bold"), width=62, anchor="w").pack(side="left")
            ctk.CTkOptionMenu(qrow, values=qvals, variable=q_var, command=refresh_size, width=140, height=28,
                              fg_color=("#e8ebef", "#232730"), button_color=("#d3d9e0", "#2b3644"),
                              text_color=("#1a1d21", "#f1f3f5")).pack(side="left")

            # --- تحميل جزء من الفيديو
            have_ff = bool(find_ffmpeg())
            crow = ctk.CTkFrame(body, fg_color="transparent")
            crow.pack(fill="x", pady=(8, 0))
            clip_box = ctk.CTkFrame(body, corner_radius=10, fg_color=CHIP_BG)

            def toggle_clip():
                if clip_on.get():
                    clip_box.pack(fill="x", pady=(6, 0), before=save_row)
                else:
                    clip_box.pack_forget()
                refresh_size()
                _fit_window(win, W, 200)

            sw = ctk.CTkSwitch(crow, text="✂  Download only a part of the video", variable=clip_on, command=toggle_clip,
                               font=(UI_FONT, 12, "bold"), progress_color=GREEN, switch_width=34, switch_height=17)
            sw.pack(side="left")
            if not have_ff or not dur:
                sw.configure(state="disabled")
            trow = ctk.CTkFrame(clip_box, fg_color="transparent")
            trow.pack(fill="x", padx=10, pady=(8, 2))
            ctk.CTkLabel(trow, text="From", font=(UI_FONT, 11)).pack(side="left")
            start_e = ctk.CTkEntry(trow, width=84, height=28, placeholder_text="00:00")
            start_e.pack(side="left", padx=(5, 10))
            ctk.CTkLabel(trow, text="To", font=(UI_FONT, 11)).pack(side="left")
            end_e = ctk.CTkEntry(trow, width=84, height=28, placeholder_text=fmt_hms(dur) if dur else "")
            end_e.pack(side="left", padx=5)
            precise = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(trow, text="Precise cut", variable=precise, width=20, checkbox_width=16, checkbox_height=16,
                            font=(UI_FONT, 11), fg_color=GREEN, hover_color=GREEN_H).pack(side="right")
            ctk.CTkLabel(clip_box, text="Precise cut re-encodes the part (slower). Turn it off for an instant cut at the nearest keyframe.",
                         font=(UI_FONT, 10), text_color=MUTED, wraplength=360, justify="left", anchor="w").pack(fill="x", padx=12, pady=(0, 4))
            clip_info = ctk.CTkLabel(clip_box, text="Whole video", font=(UI_FONT, 11), text_color=MUTED, anchor="w",
                                     image=icon_ctk("info", 13), compound="left")
            clip_info.pack(fill="x", padx=12, pady=(0, 8))
            for e in (start_e, end_e):
                e.bind("<KeyRelease>", refresh_size)
            d["_precise"] = precise
            if not have_ff:
                ctk.CTkLabel(body, text="ffmpeg not found — install it (winget install ffmpeg) or put ffmpeg.exe next to the program, "
                                        "then reopen this window to enable this.", font=(UI_FONT, 10), text_color=MUTED,
                             wraplength=376, justify="left", anchor="w", image=icon_ctk("info", 13), compound="left").pack(fill="x", pady=(4, 0))

            if youtube_list_id(url):
                ctk.CTkButton(body, text="📚  Part of a playlist — choose videos…", height=26, fg_color="transparent",
                              hover_color=CHIP_BG, text_color=("#117a4d", "#2cc985"), font=(UI_FONT, 11, "bold"), anchor="w",
                              command=lambda: show_playlist_picker(playlist_url_of(url), q_var.get(), referer, cookie, ua, "pick")
                              ).pack(fill="x", pady=(6, 0))

        # --- مكان الحفظ
        save_row = ctk.CTkFrame(body, fg_color="transparent")
        save_row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(save_row, text="Save to", font=(UI_FONT, 12, "bold"), width=62, anchor="w").pack(side="left")
        ctk.CTkButton(save_row, text="Browse", width=64, height=28, fg_color="#FF9800", hover_color="#F57C00",
                      command=lambda: _pick_dir(win, current_dl_path)).pack(side="right")
        ctk.CTkEntry(save_row, textvariable=current_dl_path, state="disabled", height=28).pack(side="left", fill="x", expand=True, padx=(0, 8))

        # --- الأزرار
        def on_confirm():
            extra = None
            if media:
                r = clip_range()
                if r == "error":
                    messagebox.showwarning("Download a part", "Please check the start / end times.\nExamples: 90   1:30   01:02:03", parent=win)
                    return
                if isinstance(r, tuple):
                    extra = {"clip_start": r[0], "clip_end": r[1], "clip_precise": bool(d["_precise"].get())}
            q = q_var.get() if media else quality
            folder = current_dl_path.get()
            win.destroy()
            start_single_download(url, q, save_path=folder, referer=referer, direct=direct or bool(d.get("fallback_direct")), cookie=cookie, ua=ua, extra=extra)

        brow = ctk.CTkFrame(body, fg_color="transparent")
        brow.pack(fill="x", pady=(12, 0))
        ctk.CTkButton(brow, text="Cancel", height=36, font=(UI_FONT, 12, "bold"), fg_color=("#e8ebef", "#232730"),
                      hover_color=("#d3d9e0", "#2b3644"), text_color=("#1a1d21", "#f1f3f5"), command=win.destroy
                      ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(brow, text="Start Download", height=36, font=(UI_FONT, 12, "bold"), fg_color=GREEN, hover_color=GREEN_H,
                      image=icon_ctk("download", 16), compound="left", command=on_confirm
                      ).pack(side="left", expand=True, fill="x", padx=(5, 0))
        if media and clip and have_ff and dur:
            clip_on.set(True)
            toggle_clip()
        refresh_size()
        _fit_window(win, W, 200)

    def fetch_info():
        d = fetch_media_details(url, quality, referer, direct)
        ui(build_ui, d)

    threading.Thread(target=fetch_info, daemon=True).start()



def _pick_dir(win, var):
    d = filedialog.askdirectory(parent=win, title="📁 Choose Save Directory...")
    if d:
        var.set(d)



def show_playlist_picker(url, quality="", referer="", cookie="", ua="", preselect="all"):
    """اختيار فيديوهات من قايمة تشغيل (أو تنزيلها كلها)."""
    key = "pl:" + url
    old = _open_popups.get(key)
    if old is not None:
        try:
            if old.winfo_exists():
                old.lift()
                return
        except Exception:
            pass
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    _open_popups[key] = win
    win.title("Playlist")
    win.configure(fg_color=WIN_BG)
    win.attributes("-topmost", True)
    win.after(700, lambda: win.attributes("-topmost", False))
    fit_geometry(win, 780, 700, 560, 480)
    win.bind("<Destroy>", lambda e: _open_popups.pop(key, None) if e.widget is win else None)
    win.bind("<Escape>", lambda e: win.destroy())
    card = ctk.CTkFrame(win, corner_radius=18, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER)
    card.pack(fill="both", expand=True, padx=14, pady=14)
    loading = ctk.CTkFrame(card, fg_color="transparent")
    loading.pack(expand=True)
    msg = ctk.CTkLabel(loading, text="📚  Loading playlist…", font=(UI_FONT, 15, "bold"), text_color=GREEN)
    msg.pack()
    bar = ctk.CTkProgressBar(loading, mode="indeterminate", width=280, progress_color=GREEN)
    bar.pack(pady=(12, 0))
    bar.start()
    save_var = ctk.StringVar(value=gui.download_path_var.get())

    def alive():
        try:
            return bool(win.winfo_exists())
        except Exception:
            return False

    def build(data):
        if not alive():
            return
        bar.stop()
        entries = data["entries"]
        if not entries:
            msg.configure(text="⚠  No videos found in this playlist.", text_color="#e06666")
            bar.pack_forget()
            return
        loading.destroy()
        total = len(entries)
        checked = {i: (preselect != "pick") for i in range(total)}
        total_dur = sum(e["duration"] or 0 for e in entries)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(body, text="📚  " + data["title"], font=(UI_FONT, 18, "bold"), anchor="w", wraplength=700, justify="left").pack(fill="x")
        sub = [f"{total} videos"]
        if total_dur:
            sub.append(f"⏱ {fmt_hms(total_dur)}")
        if data["uploader"]:
            sub.insert(0, f"👤 {data['uploader']}")
        ctk.CTkLabel(body, text="     ".join(sub), font=(UI_FONT, 12), text_color=MUTED, anchor="w").pack(fill="x", pady=(2, 8))

        bar_row = ctk.CTkFrame(body, fg_color="transparent")
        bar_row.pack(fill="x")
        sel_lbl = ctk.CTkLabel(bar_row, text="", font=(UI_FONT, 12, "bold"), text_color=GREEN)
        search = ctk.CTkEntry(bar_row, placeholder_text="🔍  Filter…", width=180, height=30)
        search.pack(side="right")
        footer = ctk.CTkFrame(body, fg_color="transparent")      # بيتحط تحت الأول: زرار التنزيل يفضل ظاهر مهما كانت النافذة صغيرة، والقايمة هي اللي بتتقلص
        footer.pack(side="bottom", fill="x")
        holder = ctk.CTkFrame(body, fg_color="transparent")
        holder.pack(fill="both", expand=True, pady=8)
        gt = ttk.Treeview(holder, columns=("ok", "n", "title", "dur"), show="headings", selectmode="browse")
        for col, text, w, st, anc in (("ok", "", 40, False, tk.CENTER), ("n", "#", 46, False, tk.CENTER),
                                      ("title", "Title", 520, True, tk.W), ("dur", "Duration", 80, False, tk.CENTER)):
            gt.heading(col, text=text)
            gt.column(col, width=w, minwidth=30, stretch=st, anchor=anc)
        sb = ttk.Scrollbar(holder, orient="vertical", style="IDM.Vertical.TScrollbar", command=gt.yview)
        gt.configure(yscrollcommand=sb.set)
        gt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        by_iid = {}

        def update_count():
            n = sum(1 for v in checked.values() if v)
            dsum = sum((entries[i]["duration"] or 0) for i, v in checked.items() if v)
            sel_lbl.configure(text=f"Selected: {n} / {total}" + (f"   ⏱ {fmt_hms(dsum)}" if dsum else ""))
            dl_btn.configure(text=f"⬇  Download selected ({n})", state="normal" if n else "disabled")

        def refill(*_):
            q = search.get().strip().lower()
            for i in gt.get_children():
                gt.delete(i)
            by_iid.clear()
            for i, e in enumerate(entries):
                if q and q not in e["title"].lower():
                    continue
                iid = gt.insert("", "end", values=("☑" if checked[i] else "☐", i + 1, e["title"], fmt_hms(e["duration"]) if e["duration"] else "-"))
                by_iid[iid] = i

        def toggle(iid):
            i = by_iid.get(iid)
            if i is None:
                return
            checked[i] = not checked[i]
            gt.set(iid, "ok", "☑" if checked[i] else "☐")
            update_count()

        def on_click(e):
            if gt.identify("region", e.x, e.y) == "cell":
                iid = gt.identify_row(e.y)
                if iid and gt.identify_column(e.x) == "#1":
                    toggle(iid)
                    return "break"

        def set_all(value):
            for iid, i in by_iid.items():        # بس اللي ظاهر (الفلتر)
                checked[i] = value(checked[i])
                gt.set(iid, "ok", "☑" if checked[i] else "☐")
            update_count()

        gt.bind("<Button-1>", on_click)
        gt.bind("<Double-1>", lambda e: toggle(gt.identify_row(e.y)) if gt.identify_row(e.y) else None)
        def on_space(e):
            for i in gt.selection():
                toggle(i)
            return "break"

        gt.bind("<space>", on_space)
        search.bind("<KeyRelease>", refill)
        for text, fn in (("Select all", lambda: set_all(lambda v: True)), ("Select none", lambda: set_all(lambda v: False)),
                         ("Invert", lambda: set_all(lambda v: not v))):
            ctk.CTkButton(bar_row, text=text, width=88, height=30, fg_color=("#e8ebef", "#232730"), hover_color=("#d3d9e0", "#2b3644"),
                          text_color=("#1a1d21", "#f1f3f5"), command=fn).pack(side="left", padx=(0, 6))
        sel_lbl.pack(side="left", padx=8)

        # --- الخيارات
        opt = ctk.CTkFrame(footer, fg_color="transparent")
        opt.pack(fill="x", pady=(0, 4))
        opt2 = ctk.CTkFrame(footer, fg_color="transparent")
        opt2.pack(fill="x", pady=(0, 6))
        qvals = list(QUALITY_MAP.keys())
        q_var = ctk.StringVar(value=quality if quality in qvals else get_default_quality_safe())
        ctk.CTkLabel(opt, text="Quality", font=(UI_FONT, 12, "bold")).pack(side="left")
        ctk.CTkOptionMenu(opt, values=qvals, variable=q_var, width=110, height=30, fg_color=("#e8ebef", "#232730"),
                          button_color=("#d3d9e0", "#2b3644"), text_color=("#1a1d21", "#f1f3f5")).pack(side="left", padx=(8, 16))
        sub_var, num_var = ctk.BooleanVar(value=True), ctk.BooleanVar(value=False)
        low_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt, text="If a video doesn't have this quality, use the closest lower one", variable=low_var, width=20,
                        checkbox_width=18, checkbox_height=18, font=(UI_FONT, 12), fg_color=GREEN, hover_color=GREEN_H).pack(side="left")
        ctk.CTkCheckBox(opt2, text="Folder for this playlist", variable=sub_var, width=20, checkbox_width=18, checkbox_height=18,
                        font=(UI_FONT, 12), fg_color=GREEN, hover_color=GREEN_H).pack(side="left", padx=(0, 14))
        ctk.CTkCheckBox(opt2, text="Number the files (01 - …)", variable=num_var, width=20, checkbox_width=18, checkbox_height=18,
                        font=(UI_FONT, 12), fg_color=GREEN, hover_color=GREEN_H).pack(side="left")
        prow = ctk.CTkFrame(footer, fg_color="transparent")
        prow.pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(prow, text="Save to", font=(UI_FONT, 12, "bold")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(prow, text="Browse", width=70, height=30, fg_color="#FF9800", hover_color="#F57C00",
                      command=lambda: _pick_dir(win, save_var)).pack(side="right")
        ctk.CTkEntry(prow, textvariable=save_var, state="disabled", height=30).pack(side="left", fill="x", expand=True, padx=(0, 8))

        def do_download():
            idxs = [i for i in range(total) if checked[i]]
            if not idxs:
                return
            if len(idxs) > 50 and not messagebox.askyesno("Playlist", f"Add {len(idxs)} videos to the queue?", parent=win):
                return
            folder = save_var.get() or gui.download_path_var.get()
            if sub_var.get():
                name = re.sub(r'[\\/:*?"<>|]', "_", data["title"]).strip(" .")[:80] or "Playlist"
                folder = os.path.join(folder, name)
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Playlist", f"Cannot use this folder:\n{folder}\n\n{e}", parent=win)
                return
            q, number, width = q_var.get(), num_var.get(), max(2, len(str(total)))
            lower = bool(low_var.get()) and q != "Audio Only"
            win.destroy()
            _batch["on"] = True
            try:
                for i in idxs:
                    extra = {"name_prefix": f"{str(i + 1).zfill(width)} - "} if number else {}
                    if lower:
                        extra["lower_ok"] = True
                    start_single_download(entries[i]["url"], q, save_path=folder, referer=referer, extra=extra)
            finally:
                _batch["on"] = False
                save_history()
                filter_tasks(gui.current_filter)

        dl_btn = ctk.CTkButton(footer, text="⬇  Download selected", height=42, font=(UI_FONT, 14, "bold"), fg_color=GREEN,
                               hover_color=GREEN_H, command=do_download)
        dl_btn.pack(fill="x")
        refill()
        update_count()
        win.lift()

    def work():
        try:
            data = fetch_playlist(url)
        except Exception as e:
            log_error(f"fetch_playlist {url}", e)
            data = {"title": "", "uploader": "", "entries": []}
        ui(build, data)

    threading.Thread(target=work, daemon=True).start()



def dispatch_add_item(i):
    """طلب جاي من الإضافة: نافذة التنزيل العادية أو اختيار قايمة التشغيل."""
    if i.get("playlist") in ("all", "pick"):
        show_playlist_picker(i["url"], i.get("quality", ""), i.get("referer", ""), i.get("cookie", ""), i.get("ua", ""), i["playlist"])
    else:
        show_quick_confirm_popup(i["url"], i["quality"], i.get("referer", ""), i.get("direct", False), i.get("cookie", ""),
                                 i.get("ua", ""), clip=bool(i.get("clip")))



def add_link_manual():
    cb = ""
    try:
        cb = gui.root.clipboard_get()
    except Exception:
        pass
    first = cb.strip().splitlines()[0] if cb.strip() else ""
    cb = cb.strip() if is_valid_url(first) else ""
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    win.title("Add Download")
    fit_geometry(win, 600, 370)
    win.attributes("-topmost", True)
    ctk.CTkLabel(win, text="Enter one or more links (one per line):", font=("Arial", 13, "bold")).pack(pady=(15, 5))
    box = ctk.CTkTextbox(win, width=470, height=140, font=("Arial", 11))
    box.pack(pady=5)
    if cb:
        box.insert("1.0", cb)
    ctk.CTkLabel(win, text="Tip: for a numbered series use  http://site.com/img[001-050].jpg",
                 font=("Arial", 11), text_color=("#666666", "#9a9a9a")).pack()

    def do_paste():
        try:
            box.insert(tk.INSERT, gui.root.clipboard_get())
        except Exception:
            pass

    m = tk.Menu(win, tearoff=False)
    m.add_command(label="📋 Paste", command=do_paste)
    box.bind("<Button-3>", lambda ev: m.post(ev.x_root, ev.y_root))

    def import_file():
        path = filedialog.askopenfilename(parent=win, title="Import links",
                                          filetypes=[("Text / lists", "*.txt *.csv *.m3u *.html *.htm *.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            urls = read_links_from_file(path)
        except Exception as e:
            messagebox.showerror("Import", f"Could not read the file:\n{e}", parent=win)
            return
        if not urls:
            messagebox.showinfo("Import", "No links were found in that file.", parent=win)
            return
        box.insert(tk.END, ("\n" if box.get("1.0", "end").strip() else "") + "\n".join(urls))
        win.lift()

    def submit():
        raw = box.get("1.0", "end").strip()
        if not raw:
            return
        links = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        valid, invalid_count = [], 0
        for ln in links:
            if not is_valid_url(ln):
                invalid_count += 1
                continue
            try:
                valid.extend(expand_patterns(ln))
            except ValueError as e:
                messagebox.showwarning("Pattern too large", str(e), parent=win)
                return
        if not valid:
            messagebox.showwarning("Invalid Link", "No valid URL found.", parent=win)
            return
        playlists = [v for v in valid if is_playlist_page(v)]
        valid = [v for v in valid if not is_playlist_page(v)]
        if len(valid) > 30 and not messagebox.askyesno("Add many downloads", f"Add {len(valid)} downloads to the queue?", parent=win):
            return
        win.destroy()
        for pl in playlists:
            show_playlist_picker(pl, gui.quality_var.get(), preselect="all")
        _batch["on"] = True
        try:
            for link in valid:
                start_single_download(link, gui.quality_var.get())
        finally:
            _batch["on"] = False
            save_history()
            filter_tasks(gui.current_filter)
        if invalid_count:
            messagebox.showinfo("Notice", f"Ignored {invalid_count} invalid lines.")

    def open_playlist():
        first = next((ln.strip() for ln in box.get("1.0", "end").splitlines() if is_valid_url(ln.strip())), "")
        if not first:
            messagebox.showinfo("Playlist", "Paste a playlist link first.", parent=win)
            return
        win.destroy()
        show_playlist_picker(playlist_url_of(first), gui.quality_var.get(), preselect="pick")

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(pady=12)
    ctk.CTkButton(row, text="📂 Import from file…", font=("Arial", 12), width=150, fg_color="gray40", command=import_file).pack(side=tk.LEFT, padx=5)
    ctk.CTkButton(row, text="📚 Playlist…", font=("Arial", 12), width=120, fg_color="gray40", command=open_playlist).pack(side=tk.LEFT, padx=5)
    ctk.CTkButton(row, text="⬇️ Download All", font=("Arial", 13, "bold"), width=160, fg_color="#2cc985", hover_color="#21a06a", command=submit).pack(side=tk.LEFT, padx=5)
    win.after(150, lambda: box.focus_set())



def choose_directory():
    d = filedialog.askdirectory()
    if d:
        gui.download_path_var.set(d)
        save_settings("save_path", d)


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.engine import start_single_download  # noqa: E402
from aerograb.tasks import _batch, save_history  # noqa: E402
from aerograb.views.grabber import _link_kind  # noqa: E402
from aerograb.views.icons import icon_ctk  # noqa: E402
from aerograb.views.mainwin import filter_tasks, read_links_from_file  # noqa: E402
from aerograb.views.thumbs import GREEN, GREEN_H, _font, _round_corners, make_type_icon  # noqa: E402
