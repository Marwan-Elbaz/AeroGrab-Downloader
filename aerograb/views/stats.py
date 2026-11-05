# -*- coding: utf-8 -*-
import customtkinter as ctk
from aerograb import usage
from aerograb.common import get_setting, log_error
from aerograb.fmt import fmt_bytes, fmt_eta, fmt_speed
from aerograb.limits import fmt_limit, schedule_allows, speed_limit_kbps
from aerograb.state import ACTIVE_STATUSES, tasks, tasks_lock
from aerograb.uistate import gui


class _SearchBox:
    """بديل بسيط لـ StringVar: customtkinter مش بيعرض placeholder لو فيه textvariable."""
    entry = None

    def get(self):
        try:
            return self.entry.get() if self.entry is not None else ""
        except Exception:
            return ""



def _shorten(text, n=90):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1] + "…"



_overall_key = {"k": None}

_bar_note = {"t": ""}



def _fit_text(text, maxw):
    """بيقصّر نص الشريط عشان يتحط جوه عرضه من غير ما يتقص من الجنبين: بيشيل الأجزاء الأخيرة الأول، وبعدين يقطع بـ …"""
    f = gui.overall_font
    try:
        if f.measure(text) <= maxw:
            return text
        parts = text.split("   |   ")
        while len(parts) > 1 and f.measure("   |   ".join(parts)) > maxw:
            parts.pop()
        t = "   |   ".join(parts)
        if f.measure(t) <= maxw:
            return t
        while len(t) > 1 and f.measure(t + "…") > maxw:
            t = t[:-1]
        return t.rstrip() + "…"
    except Exception:
        return text



def _draw_overall(frac, text):
    cv = gui.overall_cv
    w, h = cv.winfo_width(), cv.winfo_height()
    P = _pal()
    key = (round(frac, 3), text, ctk.get_appearance_mode(), w, h)
    if w < 20 or _overall_key["k"] == key:
        return
    _overall_key["k"] = key
    cv.delete("all")
    cv.configure(bg=P["bar_bg"])
    pad = 2
    r = (h - 2 * pad) / 2.0
    lw = h - 2 * pad
    cv.create_line(pad + r, h / 2, w - pad - r, h / 2, width=lw, capstyle="round", fill=P["bar_trough"])
    if frac > 0:
        x1 = pad + r + (w - 2 * pad - 2 * r) * min(1.0, frac)
        cv.create_line(pad + r, h / 2, max(x1, pad + r + 1), h / 2, width=lw, capstyle="round", fill=GREEN)
    cv.create_text(w / 2, h / 2, text=_fit_text(text, w - 2 * pad - 2 * r - 8), font=gui.overall_font, fill=P["bar_text"])



def update_average_progress(*_):
    """
    التقدم الكلي لكل اللي ظاهر في Active downloads (شغّال / في الانتظار / فاشل / مكتمل لسه ظاهر) ما عدا الموقوف مؤقتاً.
    ملاحظة: الفاشل بيتحسب كشغل ناقص، فالشريط مش بيقول "كله خلص" وفي كارت فاشل.
    """
    try:
        total_b = done_b = bps = pct_sum = 0.0
        n_cnt = n_unf = n_fail = n_done_all = 0
        with tasks_lock:
            for t in tasks.values():
                st = t["status"]
                if st == "completed":
                    n_done_all += 1
                shown = not t.get("dismissed") and st != "paused" and (st in ACTIVE_STATUSES or st in ("error", "completed"))
                if not shown:
                    continue
                n_cnt += 1
                pct = 100.0 if st == "completed" else max(0.0, min(100.0, float(t["pct"] or 0)))
                pct_sum += pct
                sz = _parse_size(t["size"])
                if sz:
                    total_b += sz
                    done_b += sz * pct / 100.0
                if st == "error":
                    n_fail += 1
                elif st != "completed":
                    n_unf += 1
                if st == "downloading":
                    bps += t.get("bps") or 0
        if not (n_unf or n_fail):
            frac = 1.0 if n_done_all else 0.0
            text = "All downloads completed ✔" if n_done_all else "No active downloads"
        else:
            frac = (done_b / total_b) if total_b else pct_sum / (100.0 * n_cnt)
            parts = [f"Overall Progress: {frac * 100:.0f}%", f"⚡ {fmt_speed(bps) if bps else '-'}"]
            if total_b:
                parts.append(f"{fmt_bytes(done_b)} of {fmt_bytes(total_b)}")
                if bps and n_unf:
                    parts.append(f"{fmt_eta(max(0.0, total_b - done_b) / bps)} remaining")
            if n_fail:
                parts.append(f"⚠ {n_fail} failed")
            text = "   |   ".join(parts)
        if _bar_note["t"]:
            text += "   |   " + _bar_note["t"]
        _draw_overall(frac, text)
        if gui.cards is not None:
            gui.cards.tick()
    except Exception as e:
        log_error("update_average_progress", e)



_tab_text_cache = {}



_chip = {"text": None, "color": None}

def update_usage_chip():
    """عدّاد الاستهلاك في الشريط السفلي: بيتلوّن برتقالي من 80% وأحمر لما الحد يخلص."""
    btn = getattr(gui, "usage_btn", None)
    if btn is None:
        return
    snap = usage.snapshot()
    if snap["enabled"]:
        text = f"Usage: {fmt_bytes(snap['used'])} / {fmt_bytes(snap['limit'])}"
        if snap["exceeded"] and not snap["overridden"]:
            color = ("#d6393f", "#ff6b6b")
        elif snap["frac"] >= 0.8:
            color = ("#c77700", "#FF9800")
        else:
            color = ("#666666", "#9a9a9a")
    else:
        text = f"Usage: {fmt_bytes(snap['today'])}"
        color = ("#666666", "#9a9a9a")
    if text != _chip["text"]:
        _chip["text"] = text
        btn.configure(text=text)
    if color != _chip["color"]:
        _chip["color"] = color
        btn.configure(text_color=color)


def update_stats():
    try:
        counts = {k: 0 for k, _ in FILTERS}
        n_act = n_queue = n_done = n_fail = 0
        with tasks_lock:
            for t in tasks.values():
                for k, _l in FILTERS:
                    if _matches(t, k):
                        counts[k] += 1
                st = t["status"]
                if st in ("starting", "downloading", "merging"):
                    n_act += 1
                elif st == "queued":
                    n_queue += 1
                elif st == "completed":
                    n_done += 1
                elif st == "error":
                    n_fail += 1
        for k, label in FILTERS:
            txt = f"{label} ({counts[k]})"
            if _tab_text_cache.get(k) != txt and k in tab_buttons:
                tab_buttons[k].configure(text=txt)
                _tab_text_cache[k] = txt
        with tasks_lock:
            n_vis = sum(1 for t in tasks.values() if not t.get("dismissed"))
        txt = f"Active downloads ({n_vis})"
        if _tab_text_cache.get("strip") != txt:
            gui.strip_title.configure(text=txt)
            _tab_text_cache["strip"] = txt
        for key, val in (("act", n_act), ("queue", n_queue), ("done", n_done), ("fail", n_fail)):
            txt = f"{val} {STAT_META[key][1]}"
            if _tab_text_cache.get("s_" + key) != txt and key in gui.stat_lbls:
                gui.stat_lbls[key].configure(text=txt)
                _tab_text_cache["s_" + key] = txt
        update_usage_chip()
        notes = []
        if speed_limit_kbps():
            notes.append(f"Limit: {fmt_limit(speed_limit_kbps())}")
        if get_setting("schedule_enabled", False) and not schedule_allows():
            notes.append(f"⏰ Waiting for schedule ({get_setting('schedule_start', '')})")
        if not usage.allows():
            notes.append("📊 Data limit reached")
        _bar_note["t"] = "   |   ".join(notes)
    except Exception as e:
        log_error("update_stats", e)


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.views.icons import STAT_META, _pal, _parse_size  # noqa: E402
from aerograb.views.mainwin import FILTERS, _matches, tab_buttons  # noqa: E402
from aerograb.views.thumbs import GREEN  # noqa: E402
