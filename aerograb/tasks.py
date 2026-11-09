# -*- coding: utf-8 -*-
import os
import uuid
import urllib.request, urllib.parse, urllib.error
import re
import itertools
from datetime import datetime
from aerograb import clipwork, partsdir
from aerograb.common import _atomic_write_json, _load_json
from aerograb.config import HISTORY_FILE, HOME
from aerograb.fmt import EXT_KIND, fmt_pct
from aerograb.i18n import tr
from aerograb.state import ROW_TAGS, tasks, tasks_lock, ui
from aerograb.uistate import gui


_prio_counter = itertools.count(1)

_batch = {"on": False}      # لما بنضيف عدد كبير مرة واحدة منحفظش التاريخ مع كل ملف



def new_task(url, quality, save_path, is_repeat, referer="", **extra):
    t = {
        "prio": next(_prio_counter), "cookie": "", "ua": "",
        "url": url, "quality": quality, "status": "queued", "status_text": "Queued...",
        "title": "Fetching data...", "date": datetime.now().strftime("%Y-%m-%d"),
        "size": "-", "speed": "-", "eta": "-", "progress": fmt_pct(0), "pct": 0.0,
        "file_path": None, "save_path": save_path, "is_repeat": bool(is_repeat),
        "referer": referer or "", "run": None, "_ui_pending": False, "bps": 0.0, "dismissed": False,
        "thumb": youtube_thumb_url(url),
    }
    t.update(extra)
    if not t.get("part_key"):
        t["part_key"] = uuid.uuid4().hex[:12]          # مفتاح ثابت لمجلد الأجزاء المؤقتة (حتى بعد إعادة تشغيل البرنامج)
    if (t.get("clip_start") is not None or t.get("clip_end") is not None) and not t.get("clip_key"):
        t["clip_key"] = uuid.uuid4().hex[:12]          # مفتاح ثابت لاستكمال تحميل الجزء (حتى بعد إعادة تشغيل البرنامج)
    return t



STATUS_ICONS = {"queued": "⏳", "starting": "🔌", "downloading": "⬇", "merging": "⚙", "paused": "⏸",
                "completed": "✔", "canceled": "✖", "error": "⚠", "deleted": "🗑"}



def progress_bar_text(pct, status):
    if pct <= 0 and status in ("queued", "starting", "paused", "error", "canceled", "deleted"):
        return "—"
    filled = int(round(max(0.0, min(100.0, pct)) / 10))
    return "█" * filled + "░" * (10 - filled) + f"  {pct:.0f}%"



KIND_LABEL = {"video": "Video", "audio": "Audio", "archive": "Archive", "app": "Program", "doc": "Document", "file": "Other"}



def task_kind_c(t):
    """نفس task_kind بس بيحفظ النتيجة في المهمة (عشان الفلترة والعدّ كل نص ثانية يفضلوا خفاف)."""
    key = (t.get("file_path"), bool(t.get("thumb")), t.get("quality"))
    c = t.get("_kc")
    if c and c[0] == key:
        return c[1]
    r = task_kind(t)
    t["_kc"] = (key, r)
    return r



def pct_text(t):
    st, pct = t["status"], float(t.get("pct") or 0)
    if st == "completed":
        return "100%"
    if st == "deleted":
        return "—"
    return f"{max(0.0, min(100.0, pct)):.0f}%"



def task_values(t):
    text = re.sub(r"^[^\w(\"“]+", "", tr(t["status_text"] or ""))      # الأيقونة بقت صورة في أول عمود، فنشيل رمز الإيموجي من النص
    fp = t.get("file_path")
    folder = os.path.dirname(str(fp)) if fp else (t.get("save_path") or "")
    return (t["title"], tr(KIND_LABEL.get(task_kind_c(t)[0], "Other")), tr(str(t["size"])), pct_text(t), t["speed"], t["eta"],
            text, t["date"], folder)



def update_task(item_id, **fields):
    """تحديث آمن من أي thread."""
    if fields.get("status") in ("canceled", "deleted"):
        fields = dict(fields, dismissed=True)          # الملغي/المحذوف مالوش لازمة في صف التحميلات الشغالة
    with tasks_lock:
        t = tasks.get(item_id)
        if t is None:
            return False
        t.update(fields)
        if t.get("_ui_pending"):
            return True
        t["_ui_pending"] = True
    ui(refresh_row, item_id)
    return True



def refresh_row(item_id):  # main thread
    with tasks_lock:
        t = tasks.get(item_id)
        if t is None:
            return
        t["_ui_pending"] = False
        vals = task_values(t)
        tag = t["status"] if t["status"] in ROW_TAGS else ""
    if gui.tree.exists(item_id):
        from aerograb.views.statusicons import tree_image
        gui.tree.item(item_id, values=vals, tags=(tag,) if tag else (), image=tree_image(t["status"]))
    if gui.cards is not None:
        gui.cards.refresh(item_id)



def save_history():
    with tasks_lock:
        data = [{
            "url": t["url"], "quality": t["quality"], "status": t["status"], "status_text": t["status_text"],
            "title": t["title"], "date": t["date"], "size": t["size"], "progress": t["progress"],
            "file_path": t["file_path"], "save_path": t["save_path"], "is_repeat": t["is_repeat"],
            "referer": t["referer"], "direct": t.get("direct", False), "thumb": t.get("thumb"), "prio": t.get("prio", 0),
            "dismissed": bool(t.get("dismissed")), "clip_start": t.get("clip_start"), "clip_end": t.get("clip_end"),
            "clip_precise": t.get("clip_precise", True), "name_prefix": t.get("name_prefix", ""), "clip_key": t.get("clip_key"),
            "resumable": t.get("resumable"), "conns": t.get("conns", 0), "fmt_desc": t.get("fmt_desc", ""),
            "part_key": t.get("part_key"),
        } for t in tasks.values()]
    _atomic_write_json(HISTORY_FILE, data)



def load_history():
    raw = _load_json(HISTORY_FILE, [])
    if not isinstance(raw, list):
        return
    stale = {"starting", "downloading", "merging", "queued"}
    default_dir = os.path.join(HOME, "Downloads")
    for data in raw[-1000:]:
        if not isinstance(data, dict) or not data.get("url"):
            continue
        status = data.get("status", "")
        legacy = list(data.get("values", ()))          # تنسيق قديم
        legacy = (legacy + ["-"] * 7)[:7] if legacy else None
        t = new_task(data["url"], data.get("quality", "1080p"),
                     data.get("save_path") or (gui.download_path_var.get() or default_dir),
                     data.get("is_repeat", False), data.get("referer", ""), direct=bool(data.get("direct")),
                     **{k: data[k] for k in ("clip_start", "clip_end", "clip_precise", "name_prefix", "clip_key", "part_key") if data.get(k) is not None})
        if data.get("thumb"):
            t["thumb"] = data["thumb"]
        for k in ("resumable", "conns", "fmt_desc"):
            if data.get(k) not in (None, ""):
                t[k] = data[k]
        if isinstance(data.get("prio"), (int, float)):
            t["prio"] = data["prio"]
        t["title"] = data.get("title") or (legacy[0] if legacy else "-")
        t["date"] = data.get("date") or (legacy[1] if legacy else "-")
        t["size"] = data.get("size") or (legacy[2] if legacy else "-")
        t["progress"] = data.get("progress") or (legacy[5] if legacy else fmt_pct(0))
        t["status_text"] = data.get("status_text") or (str(legacy[6]) if legacy else "-")
        try:
            t["pct"] = float(re.search(r"(\d+(\.\d+)?)", str(t["progress"])).group(1))
        except Exception:
            t["pct"] = 0.0
        t["file_path"] = data.get("file_path")
        if status in stale:
            status = "paused"
            t["status_text"] = "Paused (App closed previously)"
            t["speed"] = t["eta"] = "-"
        t["status"] = status
        # الرئيسية بتبدأ فاضية: اللي كان لسه شغال/متوقف يفضل ظاهر، والباقي بيروح للـ History
        t["dismissed"] = bool(data["dismissed"]) if "dismissed" in data else status != "paused"
        tag = status if status in ROW_TAGS else ""
        from aerograb.views.statusicons import tree_image
        item_id = gui.tree.insert("", "end", values=task_values(t), tags=(tag,) if tag else (), image=tree_image(status))
        tasks[item_id] = t
    global _prio_counter
    _prio_counter = itertools.count(int(max([t.get("prio", 0) for t in tasks.values()] or [0])) + 1)
    clipwork.sweep({t["clip_key"] for t in tasks.values() if t.get("clip_key") and t["status"] != "completed"})
    partsdir.sweep({t["part_key"] for t in tasks.values() if t.get("part_key") and t["status"] not in ("completed", "canceled", "deleted")})



def youtube_thumb_url(url):
    try:
        u = urllib.parse.urlparse(url)
        host = (u.hostname or "").lower()
        vid = None
        if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
            if u.path == "/watch":
                vid = (urllib.parse.parse_qs(u.query).get("v") or [None])[0]
            else:
                m = re.match(r"^/(?:shorts|embed|live)/([\w-]{6,})", u.path)
                vid = m.group(1) if m else None
        elif host == "youtu.be":
            vid = u.path.strip("/").split("/")[0]
        if vid and re.fullmatch(r"[\w-]{6,}", vid):
            return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    except Exception:
        pass
    return None



def task_kind(t):
    """(نوع الملف, الامتداد) عشان نرسم أيقونة مناسبة لو مفيش صورة."""
    path = str(t.get("file_path") or "")
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if not ext:
        try:
            ext = os.path.splitext(urllib.parse.unquote(urllib.parse.urlparse(t["url"]).path))[1].lstrip(".").lower()
        except Exception:
            ext = ""
    kind = EXT_KIND.get(ext)
    if not kind:
        if t.get("quality") == "Audio Only" and ("youtube" in t["url"] or "youtu.be" in t["url"]):
            return "audio", "M4A"
        if "youtube" in t["url"] or "youtu.be" in t["url"] or t.get("thumb"):
            return "video", (ext or "mp4").upper()[:5]
        return "file", ext.upper()[:5]
    return kind, ext.upper()[:5]
