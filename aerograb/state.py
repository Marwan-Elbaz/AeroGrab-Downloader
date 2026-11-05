# -*- coding: utf-8 -*-
import threading
import queue


# ----------------------------------------------------------------------------- Global state
show_gui_event = threading.Event()

gui_lock = threading.Lock()

ext_info = {"t": 0.0, "v": ""}      # آخر مرة الإضافة كلمت البرنامج + نسختها

pending_urls = []          # طلبات وصلت قبل ما الواجهة تفتح

pending_batches = []       # دفعات روابط (Link Grabber) وصلت قبل ما الواجهة تفتح

tasks = {}

tasks_lock = threading.Lock()


ACTIVE_STATUSES = ("queued", "starting", "downloading", "merging")

ROW_TAGS = ("completed", "paused", "canceled", "error", "deleted")


# ---- طابور تحديث الواجهة: أي thread يقدر يحط شغل، والـ main thread هو اللي ينفّذ (Tkinter مش thread-safe)
_ui_queue = queue.Queue()



def ui(fn, *a, **kw):
    _ui_queue.put((fn, a, kw))


# ----------------------------------------------------------------------------- Task model
class Run:
    """كل محاولة تحميل ليها أعلامها الخاصة، عشان Pause→Resume السريع ميعملش workerين على نفس الملف."""
    def __init__(self):
        self.stop = threading.Event()
        self.cancel = threading.Event()



class TaskAbort(Exception):
    def __init__(self, kind):
        super().__init__("USER_CANCELED" if kind == "cancel" else "USER_PAUSED")
        self.kind = kind
