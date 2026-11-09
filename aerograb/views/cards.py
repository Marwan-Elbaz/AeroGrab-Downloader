# -*- coding: utf-8 -*-
import os
import re
from PIL import Image
from PIL import ImageDraw
from PIL import ImageOps
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from aerograb.config import UI_FONT
from aerograb.i18n import Raw, tr
from aerograb.state import ACTIVE_STATUSES, tasks, tasks_lock
from aerograb.uistate import gui
from aerograb.views.tooltip import tips


def dismiss_task(iid):
    """بيشيل الكارت من الرئيسية (بيفضل في الـ History)."""
    update_task(iid, dismissed=True)
    save_history()
    apply_layout()



def prioritize_task(iid):
    """يخلّي تحميل معين يخلص الأول: بيتحط في أول الطابور وباقي التحميلات بتتوقف لحد ما يخلص."""
    with tasks_lock:
        t = tasks.get(iid)
        if not t or t["status"] in ("completed", "deleted"):
            return
    if _prio["iid"] == iid:                       # ضغطة تانية = إلغاء الأولوية
        release_priority()
        return
    release_priority()
    move_tasks([iid], "top")
    held = {}
    for other in list(tasks):
        if other != iid and tasks[other]["status"] in ("queued", "starting", "downloading"):
            held[other] = 0
            pause_task(other)
    _prio["iid"], _prio["held"] = iid, held        # التحميلات الموقوفة بترجع لما الأولوية تخلص
    resume_task(iid, include_canceled=True)
    if gui.cards is not None:
        gui.cards.refresh(iid, force=True)



def release_priority():
    old = _prio["iid"]
    _prio["iid"] = None
    _prio["pending"] = dict(_prio.get("held") or {})
    _prio["held"] = {}
    if old and gui.cards is not None:
        gui.cards.refresh(old, force=True)



def prio_tick():
    iid = _prio["iid"]
    if iid:
        with tasks_lock:
            t = tasks.get(iid)
            st = t["status"] if t else None
        if st not in ACTIVE_STATUSES:
            release_priority()
    for h in list(_prio["pending"]):
        with tasks_lock:
            t = tasks.get(h)
            st = t["status"] if t else None
        if st == "paused":
            resume_task(h)
            _prio["pending"].pop(h, None)
        else:
            _prio["pending"][h] += 1
            if st is None or _prio["pending"][h] > 24:
                _prio["pending"].pop(h, None)



def card_action(iid, key):
    """أزرار الكارت."""
    with tasks_lock:
        t = tasks.get(iid)
        t = dict(t) if t else None
    if not t:
        return
    st = t["status"]
    if key == "toggle":
        if st in ACTIVE_STATUSES:
            pause_task(iid)
        elif st in ("paused", "error", "canceled"):
            resume_task(iid, include_canceled=True)
    elif key == "prio":
        prioritize_task(iid)
    elif key == "remove":
        remove_tasks([iid])
    elif key == "folder":
        reveal_in_folder(t.get("file_path"), t.get("save_path"))
    elif key == "open":
        fp = t.get("file_path")
        if fp and os.path.exists(fp):
            open_path(fp)
            dismiss_task(iid)
        else:
            messagebox.showinfo("Not available", "The file was moved or deleted.")
    elif key == "done":
        dismiss_task(iid)



class CardGrid:
    """شبكة كروت التحميلات. بترسم الكروت اللي على الشاشة بس، فمهما كان العدد كبير بتفضل خفيفة."""

    def __init__(self, parent, scale, on_action, on_open, on_menu):
        import tkinter.font as tkfont
        from PIL import ImageTk
        self._ImageTk = ImageTk
        self.s = scale
        self.on_action, self.on_open, self.on_menu = on_action, on_open, on_menu
        k = self.k
        self.GAP, self.CH, self.MINW = k(CARD_GAP), k(CARD_H), k(CARD_MIN_W)
        self.TW, self.TH = k(96), k(72)
        self.BW, self.BH = k(30), k(24)
        self.cv = tk.Canvas(parent, highlightthickness=0, bd=0, xscrollincrement=k(40), takefocus=1,
                            height=self.CH + 2 * self.GAP)
        self.sb = ttk.Scrollbar(parent, orient="horizontal", style="IDM.Horizontal.TScrollbar", command=self._xview)
        self.cv.configure(xscrollcommand=self.sb.set)
        self.cv.pack(side=tk.TOP, fill=tk.X)          # الشريط الأفقي (self.sb) بيظهر بس لما الكروت أكتر من العرض
        mk = lambda px, bold=False, fam=UI_FONT: tkfont.Font(family=fam, size=-k(px), weight="bold" if bold else "normal")
        self.f_title, self.f_meta = mk(15, True), mk(12)
        self.f_pct, self.f_chip, self.f_ico = mk(12, True), mk(12, True), mk(14, False, EMOJI_FONT)
        self.f_empty_t, self.f_empty_s = mk(16, True), mk(12)
        self.pal, self.theme = _pal(), ctk.get_appearance_mode()
        self._img = {}
        self.ids, self.index = [], {}
        self.sel, self.selset = [], set()
        self.drawn = {}
        self._hv = (None, None)
        self.cw, self._total = self.MINW + self.k(10), 0
        self.on_activate = None
        self.want_see = None
        self.empty = ("", "")
        self._cfg_job = None
        cv = self.cv
        cv.bind("<Configure>", self._on_configure)
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Leave>", lambda e: self._set_hover(None, None))
        cv.bind("<Button-1>", self._on_click)
        cv.bind("<Double-1>", self._on_double)
        cv.bind("<Button-3>", self._on_right)
        cv.bind("<Enter>", self._bind_wheel)
        cv.bind("<Leave>", self._unbind_wheel, add="+")

    def k(self, v):
        return int(round(v * self.s))

    # ---------- تمرير
    def _bind_wheel(self, _e=None):
        self.cv.bind_all("<MouseWheel>", self._wheel)
        self.cv.bind_all("<Button-4>", lambda e: self._scroll(-3))
        self.cv.bind_all("<Button-5>", lambda e: self._scroll(3))

    def _unbind_wheel(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cv.unbind_all(seq)

    def _wheel(self, e):
        self._scroll(-3 if e.delta > 0 else 3)

    def _scroll(self, units):
        self.cv.xview_scroll(units, "units")
        self.render()

    def _xview(self, *a):
        self.cv.xview(*a)
        self.render()

    # ---------- بيانات
    def set_items(self, ids):
        ids = list(ids)
        if ids == self.ids:
            return
        self.ids = ids
        self.index = {iid: n for n, iid in enumerate(ids)}
        self.sel = [i for i in self.sel if i in self.index]
        self.selset = set(self.sel)
        self.relayout()
        if self.want_see in self.index:
            self.see(self.want_see)
        self.want_see = None

    def set_empty(self, title, sub):
        if self.empty != (title, sub):
            self.empty = (title, sub)
            if not self.ids:
                self.render(full=True)

    def selected(self):
        return [i for i in self.sel if i in self.index]

    def select(self, ids):
        new = [i for i in ids if i in self.index]
        old = self.selset
        self.sel, self.selset = new, set(new)
        for iid in old ^ self.selset:
            self._apply_bg(iid)

    def apply_theme(self):
        self.pal, self.theme = _pal(), ctk.get_appearance_mode()
        self._img.clear()
        self.cv.configure(bg=self.pal["canvas"])
        self.relayout()

    # ---------- تخطيط
    def _on_configure(self, _e=None):
        if self._cfg_job:
            self.cv.after_cancel(self._cfg_job)
        self._cfg_job = self.cv.after(60, self.relayout)

    def relayout(self):
        self._cfg_job = None
        W = max(self.cv.winfo_width(), 50)
        n = len(self.ids)
        self._total = self.GAP + n * (self.cw + self.GAP) if n else 0
        self.cv.configure(scrollregion=(0, 0, max(self._total, W), self.CH + 2 * self.GAP))
        if self._total <= W:
            self.cv.xview_moveto(0)
        if self.cv.winfo_width() > 1:                  # الشريط يظهر بس لو الكروت مش كلها داخلة في العرض
            need = self._total > W
            shown = bool(self.sb.winfo_manager())
            if need and not shown:
                self.sb.pack(side=tk.TOP, fill=tk.X)
            elif not need and shown:
                self.sb.pack_forget()
        self.render(full=True)

    def _pos(self, i):
        return self.GAP + i * (self.cw + self.GAP), self.GAP

    def see(self, iid):
        i = self.index.get(iid)
        if i is None or not self._total:
            return
        x = self._pos(i)[0]
        left, W = self.cv.canvasx(0), self.cv.winfo_width()
        if x < left or x + self.cw > left + W:
            self.cv.xview_moveto(max(0.0, min(1.0, (x - self.GAP) / self._total)))
            self.render()

    def render(self, full=False):
        c = self.cv
        if full:
            c.delete("all")
            self.drawn.clear()
            self._hv = (None, None)
            if len(self._img) > 300:
                self._img = {k: v for k, v in self._img.items() if k[0] != "th"}
        n = len(self.ids)
        if not n:
            if full:
                W, H = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
                c.create_text(W / 2, H / 2 - self.k(10), text=self.empty[0], font=self.f_empty_t, fill=self.pal["title"], tags="empty")
                c.create_text(W / 2, H / 2 + self.k(18), text=self.empty[1], font=self.f_empty_s, fill=self.pal["muted"], tags="empty")
            return
        W = c.winfo_width()
        x0 = c.canvasx(0)
        step = self.cw + self.GAP
        lo = max(0, int((x0 - self.GAP) // step))
        hi = min(n, int((x0 + W) // step) + 2)
        want = set(self.ids[lo:hi])
        for iid in [i for i in self.drawn if i not in want]:
            c.delete("k_" + iid)
            del self.drawn[iid]
        for i in range(lo, hi):
            if self.ids[i] not in self.drawn:
                self._draw(self.ids[i], i)

    # ---------- صور مخزّنة
    def _photo(self, key, make):
        im = self._img.get(key)
        if im is None:
            im = self._img[key] = self._ImageTk.PhotoImage(make())
        return im

    def _bg(self, state, mode):
        st = self.pal["states"][state]
        border, bw = st["border"], 1
        if mode == "h":
            border = _mix(border, st["acc"], 0.55)
        elif mode == "s":
            border, bw = st["acc"], 2
        w, h = self.cw, self.CH
        return self._photo(("bg", state, mode, w, h), lambda: _aa_round(w, h, self.k(14), st["fill"], border, self.k(bw)))

    def _btn(self, w, color):
        return self._photo(("btn", w, color), lambda: _aa_round(w, self.BH, self.k(7), color))

    def _chip_img(self, w, color):
        return self._photo(("chip", w, color), lambda: _aa_round(w, self.BH, self.BH // 2, color))

    def _thumb(self, t):
        kind, ext = task_kind_c(t)
        url = t.get("thumb")
        if url and url not in _thumb_mem:
            _load_thumb_async(url)
        loaded = bool(url and _thumb_mem.get(url))
        TW, TH = self.TW, self.TH

        def make():
            base = _thumb_mem[url] if loaded else make_type_icon(kind, ext)
            pil = _aa_corners(ImageOps.fit(base.convert("RGBA"), (TW, TH)), self.k(9))
            if loaded:
                ov = Image.new("RGBA", pil.size, (0, 0, 0, 0))
                od = ImageDraw.Draw(ov)
                if kind in ("video", "audio"):
                    cx, cy, r = TW // 2, TH // 2 - self.k(4), self.k(13)
                    od.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 125))
                    od.polygon([(cx - r // 3, cy - r // 2), (cx - r // 3, cy + r // 2), (cx + r // 2, cy)], fill=(255, 255, 255, 235))
                if ext:
                    f = _font(self.k(10))
                    tw = int(od.textlength(ext, font=f))
                    bx1, by1 = TW - self.k(5), TH - self.k(5)
                    od.rounded_rectangle((bx1 - tw - self.k(10), by1 - self.k(15), bx1, by1), radius=self.k(5), fill=(14, 16, 20, 215))
                    od.text((bx1 - tw / 2 - self.k(5), by1 - self.k(7.5)), ext, font=f, fill="white", anchor="mm")
                pil = Image.alpha_composite(pil, ov)
            return pil
        return self._photo(("th", kind, ext, url, loaded, TW, TH), make)

    # ---------- نصوص الكارت
    def _icon(self, name, px, dim=False):
        return self._photo(("ic", name, px, dim, self.theme), lambda: icon_pil(name, px, dark=(self.theme == "Dark"), dim=dim))

    @staticmethod
    def _chip_info(t):
        """(اسم الأيقونة, النص) للحالة."""
        txt = t.get("status_text") or ""
        st = t["status"]
        if st in ACTIVE_STATUSES and txt.startswith("Pausing"):
            return "pause", "Pausing…"
        if txt.startswith("Canceling"):
            return "remove", "Canceling…"
        return CHIP_ICON.get(st), CHIP_TEXT.get(st, st)

    @staticmethod
    def _meta_parts(t):
        return (("icon", "drive"), ("text", str(t["size"])), ("text", "     •     " + str(t["date"])))

    @staticmethod
    def _detail_parts(t):
        st, txt = t["status"], re.sub(r"^[^\w]+", "", t.get("status_text") or "")
        if st == "downloading":
            return (("icon", "speed"), ("text", str(t["speed"])), ("text", "     "), ("icon", "hourglass"), ("text", f"ETA {t['eta']}"))
        if st == "starting":
            return (("icon", "plug"), ("text", txt or "Connecting…"))
        if st == "queued":
            return (("icon", "hourglass"), ("text", "Waiting in the queue…"))
        if st == "completed":
            return (("icon", "folder"), ("text", os.path.basename(str(t.get("save_path") or "").rstrip("/\\")) or "Downloads"))
        if st == "paused":
            return (("icon", "pause"), ("text", f"Paused at {t['pct']:.0f}%"))
        if st == "merging":
            return (("icon", "bolt"), ("text", txt or "Merging…"))
        return (("text", txt or "-"),)

    @staticmethod
    def _info_parts(t):
        """سطر معلومات التنزيل: دعم الاستكمال · عدد الاتصالات / الصيغة · الجودة · الموقع."""
        from urllib.parse import urlparse
        parts = []
        res = t.get("resumable")
        if res is True:
            parts += [("icon", "retry"), ("text", "Resumable")]
        elif res is False:
            parts += [("icon", "remove"), ("text", "Not resumable")]
        elif t["status"] in ("queued", "starting"):
            parts += [("icon", "info"), ("text", "Checking the link…")]
        conns = int(t.get("conns") or 0)
        if conns > 1:
            parts += [("text", "     "), ("icon", "bolt"), ("text", f"{conns} connections")]
        desc = re.sub(r"\s*·\s*(H\.264|HEVC|AV1|VP9|VP8)\b", "", t.get("fmt_desc") or "")       # تحميلات قديمة محفوظة بالكودك: نشيله
        if desc:
            parts += [("text", "     "), ("icon", "video"), ("text", desc)]
        elif t.get("direct") is False and t.get("quality") and not conns:
            parts += [("text", "     "), ("icon", "video"), ("text", str(t["quality"]))]
        try:
            host = (urlparse(t.get("url") or "").hostname or "").replace("www.", "")
        except Exception:
            host = ""
        if host:
            parts += [("text", "     "), ("icon", "link"), ("text", host)]
        return tuple(parts)

    def _sig(self, t, iid=None):
        url = t.get("thumb")
        return (t["status"], t["title"], self._meta_parts(t), self._chip_info(t), self._detail_parts(t), self._info_parts(t),
                int(t["pct"] * 2), bool(url and _thumb_mem.get(url)), self.cw, self.theme, _prio["iid"] == iid)

    def _specs(self, t, iid):
        """الأزرار (من الشمال لليمين) حسب حالة التحميل."""
        P, st, k = self.pal, t["status"], self.k
        acc = P["states"][STATE_OF.get(st, "queue")]["acc"]

        def icon(key, name, dim=False):
            return dict(key=key, icon=name, dim=dim, w=self.BW, kind="icon", fill=P["btn"], fill_h=P["btn_h"])

        def text(key, label, primary):
            w = self.f_chip.measure(label) + k(22)
            if primary:
                return dict(key=key, glyph=label, color="#ffffff", w=w, kind="text", fill=acc, fill_h=_mix(acc, "#ffffff", 0.22))
            return dict(key=key, glyph=label, color=P["title"], w=w, kind="text", fill=P["btn"], fill_h=P["btn_h"])

        if st == "completed":
            return [icon("folder", "folder"), icon("open", "file"), text("done", "Done", False)]
        res = []
        if st in ACTIVE_STATUSES:
            res.append(icon("toggle", "pause"))
        elif st == "paused":
            res.append(icon("toggle", "play"))
        elif st in ("error", "canceled"):
            res.append(icon("toggle", "retry"))
        if st in ACTIVE_STATUSES or st == "paused":
            res.append(icon("prio", "star", dim=(_prio["iid"] != iid)))
        return res + [icon("remove", "remove"), icon("folder", "folder")]

    # ---------- رسم كارت واحد
    def _line(self, x, y, parts, maxx, font, fill, tags):
        """سطر فيه أيقونات ونصوص ورا بعض."""
        c, k = self.cv, self.k
        ip = k(14)
        cx = x
        for kind, val in parts:
            if kind == "icon":
                if cx + ip > maxx:
                    break
                c.create_image(cx, y + k(1), anchor="nw", image=self._icon(val, ip), tags=tags)
                cx += ip + k(5)
            else:
                val = tr(val)                       # بنترجم قبل القص عشان العرض يتحسب صح
                txt = _ellipsize(font, val, maxx - cx)
                if txt:
                    c.create_text(cx, y, anchor="nw", text=txt, font=font, fill=fill, tags=tags)
                cx += font.measure(txt)
                if txt != val:
                    break

    def _draw(self, iid, i):
        with tasks_lock:
            t0 = tasks.get(iid)
            t = dict(t0) if t0 else None
        if not t:
            return
        c, k, P = self.cv, self.k, self.pal
        x, y = self._pos(i)
        w = self.cw
        state = STATE_OF.get(t["status"], "queue")
        st = P["states"][state]
        tags = ("card", "k_" + iid)
        mode = "s" if iid in self.selset else ("h" if self._hv[0] == iid else "n")
        bg = c.create_image(x, y, anchor="nw", image=self._bg(state, mode), tags=tags)
        c.create_image(x + k(12), y + k(12), anchor="nw", image=self._thumb(t), tags=tags)
        tx = x + k(12) + self.TW + k(12)
        maxx = x + w - k(12)
        c.create_text(tx, y + k(12), anchor="nw", text=Raw(_ellipsize(self.f_title, t["title"], maxx - tx)),
                      font=self.f_title, fill=P["title"], tags=tags)
        self._line(tx, y + k(38), self._meta_parts(t), maxx, self.f_meta, P["muted"], tags)
        self._line(tx, y + k(58), self._detail_parts(t), maxx, self.f_meta, P["muted"], tags)
        self._line(x + k(12), y + k(88), self._info_parts(t), x + w - k(12), self.f_meta, P["muted"], tags)
        pct = max(0.0, min(100.0, float(t["pct"] or 0)))
        if t["status"] == "completed":
            pct = 100.0
        c.create_text(x + w - k(12), y + k(118), anchor="se", text=f"{pct:.0f}%", font=self.f_pct, fill=P["muted"], tags=tags)
        bx0, bx1, by = x + k(12), x + w - k(12), y + k(125)
        c.create_line(bx0, by, bx1, by, width=k(6), capstyle="round", fill=P["trough"], tags=tags)
        if pct > 0:
            c.create_line(bx0, by, max(bx0 + 1, bx0 + (bx1 - bx0) * pct / 100.0), by, width=k(6), capstyle="round",
                          fill=st["acc"], tags=tags)
        ry = y + k(134)
        specs = self._specs(t, iid)
        total = sum(s["w"] for s in specs) + k(6) * max(0, len(specs) - 1)
        space = w - k(24) - total - k(10)
        icon_name, chip_txt = self._chip_info(t)
        ipx = k(14)
        extra_w = (ipx + k(5)) if icon_name else 0
        chip = _ellipsize(self.f_chip, chip_txt, space - k(20) - extra_w)
        cwid = self.f_chip.measure(chip) + k(20) + extra_w
        c.create_image(bx0, ry, anchor="nw", image=self._chip_img(cwid, st["chip"]), tags=tags)
        ix = bx0 + k(10)
        if icon_name:
            c.create_image(ix, ry + (self.BH - ipx) // 2, anchor="nw", image=self._icon(icon_name, ipx), tags=tags)
        c.create_text(ix + extra_w, ry + self.BH / 2, anchor="w", text=chip, font=self.f_chip, fill=st["chip_t"], tags=tags)
        gx = x + w - k(12) - total
        for s in specs:
            s["x0"] = gx - x
            s["img"] = c.create_image(gx, ry, anchor="nw", image=self._btn(s["w"], s["fill"]), tags=tags)
            if s["kind"] == "icon":
                c.create_image(gx + s["w"] / 2, ry + self.BH / 2, anchor="center", image=self._icon(s["icon"], k(16), s.get("dim", False)), tags=tags)
            else:
                c.create_text(gx + s["w"] / 2, ry + self.BH / 2, text=s["glyph"], tags=tags, fill=s["color"], font=self.f_chip)
            gx += s["w"] + k(6)
        self.drawn[iid] = {"bg": bg, "specs": specs, "state": state, "sig": self._sig(t, iid)}

    # ---------- تحديث
    def refresh(self, iid, force=False):
        rec = self.drawn.get(iid)
        if rec is None:
            return
        with tasks_lock:
            t = tasks.get(iid)
            sig = self._sig(t, iid) if t else None
        i = self.index.get(iid)
        if t is None or i is None or (not force and sig == rec["sig"]):
            return
        self.cv.delete("k_" + iid)
        del self.drawn[iid]
        self._draw(iid, i)

    def tick(self):
        for iid in list(self.drawn):
            self.refresh(iid)

    def _apply_bg(self, iid):
        rec = self.drawn.get(iid)
        if rec:
            mode = "s" if iid in self.selset else ("h" if self._hv[0] == iid else "n")
            self.cv.itemconfigure(rec["bg"], image=self._bg(rec["state"], mode))

    # ---------- ماوس
    def _hit(self, ex, ey):
        cx, cy = self.cv.canvasx(ex), self.cv.canvasy(ey)
        gap, w = self.GAP, self.cw
        if cx < gap or cy < gap:
            return None, None
        col, rx = divmod(cx - gap, w + gap)
        i = int(col)
        if rx > w or cy > gap + self.CH or i >= len(self.ids):
            return None, None
        iid = self.ids[i]
        btn = None
        rec = self.drawn.get(iid)
        ry = cy - gap
        top = self.k(134)
        if rec and top <= ry <= top + self.BH:
            for n, s in enumerate(rec["specs"]):
                if s["x0"] <= rx <= s["x0"] + s["w"]:
                    btn = n
        return iid, btn

    def _set_hover(self, iid, btn):
        new = (iid, btn)
        if new == self._hv:
            return
        old_iid, old_btn = self._hv
        self._hv = new
        if old_iid in self.drawn:
            if old_btn is not None:
                s = self.drawn[old_iid]["specs"][old_btn]
                self.cv.itemconfigure(s["img"], image=self._btn(s["w"], s["fill"]))
            if old_iid != iid:
                self._apply_bg(old_iid)
        if iid in self.drawn:
            if btn is not None:
                s = self.drawn[iid]["specs"][btn]
                self.cv.itemconfigure(s["img"], image=self._btn(s["w"], s["fill_h"]))
            self._apply_bg(iid)
        self.cv.configure(cursor="hand2" if btn is not None else "")
        self._update_tip(iid, btn)

    _TIP_TEXT = {"folder": "Open the folder containing the file", "open": "Open the downloaded file",
                 "done": "Dismiss this card from Active downloads (the file stays in the list)",
                 "prio": "Download this first", "remove": "Remove from list"}
    _TOGGLE_TEXT = {"pause": "Pause download", "play": "Resume download", "retry": "Retry download"}

    def _update_tip(self, iid, btn):
        """تلميح الزرار اللي الماوس واقف عليه."""
        try:
            if iid is None or btn is None or iid not in self.drawn:
                tips.hide()
                return
            s = self.drawn[iid]["specs"][btn]
            txt = self._TOGGLE_TEXT.get(s.get("icon")) if s["key"] == "toggle" else self._TIP_TEXT.get(s["key"])
            tips.schedule((iid, btn), txt, self.cv.winfo_pointerx(), self.cv.winfo_pointery())
        except Exception:
            pass

    def _on_motion(self, e):
        self._set_hover(*self._hit(e.x, e.y))

    def _on_click(self, e):
        tips.hide()
        self.cv.focus_set()
        if self.on_activate:
            self.on_activate()
        iid, btn = self._hit(e.x, e.y)
        if iid is None:
            self.select([])
            return
        if btn is not None:
            self.on_action(iid, self.drawn[iid]["specs"][btn]["key"])
            return
        if e.state & 0x4:                                  # Ctrl
            cur = list(self.sel)
            cur.remove(iid) if iid in self.selset else cur.append(iid)
            self.select(cur)
        elif e.state & 0x1 and self.sel:                   # Shift
            a, b = sorted((self.index.get(self.sel[-1], 0), self.index[iid]))
            self.select(self.ids[a:b + 1])
        else:
            self.select([iid])

    def _on_double(self, e):
        iid, btn = self._hit(e.x, e.y)
        if iid and btn is None:
            self.on_open(iid)

    def _on_right(self, e):
        iid, _ = self._hit(e.x, e.y)
        if iid:
            if iid not in self.selset:
                self.select([iid])
            self.on_menu(e, iid)


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.engine import pause_task, remove_tasks, resume_task  # noqa: E402
from aerograb.tasks import save_history, task_kind_c, update_task  # noqa: E402
from aerograb.views.icons import (
    CARD_GAP,
    CARD_H,
    CARD_MIN_W,
    CHIP_ICON,
    CHIP_TEXT,
    EMOJI_FONT,
    STATE_OF,
    _aa_corners,
    _aa_round,
    _ellipsize,
    _mix,
    _pal,
    _prio,
    icon_pil,
)  # noqa: E402
from aerograb.views.mainwin import apply_layout, move_tasks  # noqa: E402
from aerograb.views.thumbs import _font, _load_thumb_async, _thumb_mem, make_type_icon  # noqa: E402
from aerograb.views.winutil import open_path, reveal_in_folder  # noqa: E402
