# -*- coding: utf-8 -*-
"""Tooltips خفيفة: لما تقف بالماوس على زرار أو عنصر يظهر شرح بسيط لفايدته.
نافذة واحدة بس بتتعاد استخدامها لكل التلميحات (مفيش تقل على الواجهة)."""
import tkinter as tk
import customtkinter as ctk
from aerograb.uistate import gui

DELAY_MS = 450          # الانتظار قبل ما يظهر التلميح
HIDE_MS = 7000          # بيختفي لوحده بعد المدة دي


class _TipManager:
    def __init__(self):
        self.win = None
        self.label = None
        self.job = None
        self.hide_job = None
        self.owner = None

    # ---- داخلي
    def _root(self):
        return gui.root

    def _cancel(self):
        r = self._root()
        for attr in ("job", "hide_job"):
            j = getattr(self, attr)
            if j is not None and r is not None:
                try:
                    r.after_cancel(j)
                except Exception:
                    pass
            setattr(self, attr, None)

    def _colors(self):
        dark = ctk.get_appearance_mode() == "Dark"
        return ("#2b3038", "#e8eaed", "#4a515c") if dark else ("#fffdf3", "#222222", "#c9c2a0")

    def _show(self, text, x, y):
        self.job = None
        r = self._root()
        if r is None or not text:
            return
        bg, fg, bd = self._colors()
        try:
            if self.win is None or not self.win.winfo_exists():
                self.win = tk.Toplevel(r)
                self.win.withdraw()
                self.win.overrideredirect(True)
                try:
                    self.win.attributes("-topmost", True)
                except Exception:
                    pass
                self.label = tk.Label(self.win, justify="left", padx=8, pady=4, borderwidth=1, relief="solid",
                                      font=("Segoe UI", 9))
                self.label.pack()
            self.label.configure(text=text, bg=bg, fg=fg, highlightbackground=bd)
            self.win.update_idletasks()
            w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            px = max(0, min(x + 14, sw - w - 4))
            py = y + 20 if y + 20 + h < sh - 4 else y - h - 10
            self.win.geometry(f"+{px}+{py}")
            self.win.deiconify()
            self.hide_job = r.after(HIDE_MS, self.hide)
        except Exception:
            self.win = None

    # ---- واجهة
    def schedule(self, owner, text, x, y):
        """owner: أي معرّف للعنصر (عشان منكررش نفس التلميح)."""
        r = self._root()
        if r is None:
            return
        if self.owner == owner and (self.job is not None or (self.win is not None and self.win.winfo_ismapped())):
            return
        self.hide()
        self.owner = owner
        text = text() if callable(text) else text
        if text:
            self.job = r.after(DELAY_MS, lambda: self._show(text, x, y))

    def flash(self, text, x, y, ms=1600):
        """رسالة قصيرة جنب الماوس (مثلاً "تم نسخ الرابط") بتختفي لوحدها."""
        r = self._root()
        if r is None:
            return
        self.hide()
        self._show(text, x - 10, y - 30)
        if self.hide_job is not None:
            try:
                r.after_cancel(self.hide_job)
            except Exception:
                pass
        self.hide_job = r.after(ms, self.hide)

    def hide(self, *_):
        self._cancel()
        self.owner = None
        try:
            if self.win is not None and self.win.winfo_exists():
                self.win.withdraw()
        except Exception:
            self.win = None


tips = _TipManager()


def attach(widget, text):
    """بيربط تلميح بأي ويدجت (CTk أو tk). text نص أو دالة بترجّع نص."""
    if widget is None:
        return widget
    key = id(widget)

    def enter(e):
        tips.schedule(key, text, e.x_root, e.y_root)

    try:
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", tips.hide, add="+")
        widget.bind("<ButtonPress>", tips.hide, add="+")
    except Exception:
        pass
    return widget
